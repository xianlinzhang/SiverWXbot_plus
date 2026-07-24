import os
import json
import hashlib
import threading
from datetime import datetime
import re
from logger import log


class MemoryManager:
    """
    对话记忆管理类
    按窗口分文件存储收发消息，并在 AI 请求时提供历史上下文。
    存储路径：{base_path}/{wx_id}/{storage_name}/{storage_name}_memory.json
    """

    WINDOWS_RESERVED_NAMES = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

    def __init__(self, wx_id, base_path):
        self.wx_id     = wx_id
        self.base_path = base_path  # 根目录：{base_dir}/memory/
        self._locks    = {}         # chat_name -> threading.Lock()

    def _get_lock(self, chat_name):
        if chat_name not in self._locks:
            self._locks[chat_name] = threading.Lock()
        return self._locks[chat_name]

    @classmethod
    def _is_windows_reserved_name(cls, name):
        stem = name.split('.', 1)[0].upper()
        return stem in cls.WINDOWS_RESERVED_NAMES

    @staticmethod
    def _hash_storage_name(name):
        raw_name = str(name)
        return "hash" + hashlib.sha256(raw_name.encode('utf-8')).hexdigest()

    @classmethod
    def _resolve_storage_name(cls, chat_name):
        """
        将微信窗口名转换为 Windows 可用的目录/文件名前缀。
        非法符号直接剔除；剔除后为空或仍不适合作为 Windows 名称时使用 hash 前缀兜底。
        """
        raw_name = str(chat_name)
        storage_name = cls.INVALID_FILENAME_CHARS_RE.sub('', raw_name)
        storage_name = storage_name.strip().rstrip('. ')
        if (
            not storage_name
            or storage_name in ('.', '..')
            or cls._is_windows_reserved_name(storage_name)
            or len(storage_name) > 120
        ):
            return cls._hash_storage_name(raw_name), True
        return storage_name, storage_name != raw_name

    @staticmethod
    def _write_original_name(dir_path, chat_name):
        name_path = os.path.join(dir_path, 'name.json')
        try:
            with open(name_path, 'w', encoding='utf-8') as f:
                json.dump({"name": str(chat_name)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(level="WARNING", message=f"写入记忆原始名称记录失败: {e}")

    def _get_memory_path(self, chat_name):
        """返回记忆文件路径，并确保目录存在"""
        storage_name, should_write_name = self._resolve_storage_name(chat_name)
        dir_path = os.path.join(self.base_path, self.wx_id, storage_name)
        os.makedirs(dir_path, exist_ok=True)
        if should_write_name:
            self._write_original_name(dir_path, chat_name)
        return os.path.join(dir_path, f"{storage_name}_memory.json")

    @staticmethod
    def _normalize_message_time(message_time=None):
        """将外部传入的时间统一转成记忆文件使用的字符串格式。"""
        if isinstance(message_time, datetime):
            return message_time.strftime("%Y/%m/%d %H:%M:%S")
        if isinstance(message_time, str):
            message_time = message_time.strip()
            if message_time:
                return message_time
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    @staticmethod
    def _parse_message_time(message_time):
        """解析记忆时间字符串；解析失败时返回 None，避免影响主流程。"""
        if not message_time:
            return None
        try:
            return datetime.strptime(str(message_time), "%Y/%m/%d %H:%M:%S")
        except Exception:
            return None

    def _append_message_in_order(self, messages, entry, recent_count=5):
        """在最近 recent_count 条范围内按时间插入，修正回调并发导致的乱序写入。"""
        current_dt = self._parse_message_time(entry.get("time"))
        if current_dt is None or not messages:
            messages.append(entry)
            return messages

        recent_start = max(0, len(messages) - recent_count)
        recent_messages = messages[recent_start:]
        has_later_recent = False
        for item in recent_messages:
            item_dt = self._parse_message_time(item.get("time"))
            if item_dt and item_dt > current_dt:
                has_later_recent = True
                break

        if not has_later_recent:
            messages.append(entry)
            return messages

        # 只重排尾部最近几条，既能修正本次乱序，也避免每次写入都全量排序。
        sortable_recent = []
        for idx, item in enumerate(recent_messages):
            item_dt = self._parse_message_time(item.get("time")) or datetime.max
            sortable_recent.append((item_dt, idx, item))
        sortable_recent.append((current_dt, len(recent_messages), entry))
        sortable_recent.sort(key=lambda x: (x[0], x[1]))
        messages[recent_start:] = [item for _, _, item in sortable_recent]
        return messages

    def save_message(self, chat_name, sender, content, msg_type, msg_attr, max_count, message_time=None):
        """写入一条消息到记忆文件，超出 max_count 时删除最旧的"""
        path  = self._get_memory_path(chat_name)
        entry_time = self._normalize_message_time(message_time)
        entry = {
            "time":    entry_time,
            "type":    str(msg_type),
            "attr":    str(msg_attr),
            "sender":  str(sender),
            "content": str(content),
        }
        with self._get_lock(chat_name):
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        messages = json.load(f)
                    if not isinstance(messages, list):
                        messages = []
                except Exception:
                    messages = []
            else:
                messages = []
            messages = self._append_message_in_order(messages, entry, recent_count=5)
            if len(messages) > max_count:
                messages = messages[-max_count:]
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)

    def get_messages(self, chat_name, count):
        """读取最近 count 条记忆，返回 list"""
        path = self._get_memory_path(chat_name)
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                messages = json.load(f)
            if isinstance(messages, list):
                return messages[-count:]
        except Exception:
            pass
        return []

    def clear_messages(self, chat_name):
        """清空指定会话的对话记忆"""
        path = self._get_memory_path(chat_name)
        with self._get_lock(chat_name):
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False)
            except Exception:
                pass

    def clear_all_messages(self):
        """清空所有会话的对话记忆，返回清除的会话数"""
        count = 0
        base = os.path.join(self.base_path, self.wx_id)
        if not os.path.exists(base):
            return count
        for chat_dir in os.listdir(base):
            memory_file = os.path.join(base, chat_dir, f"{chat_dir}_memory.json")
            if os.path.exists(memory_file):
                try:
                    with open(memory_file, 'w', encoding='utf-8') as f:
                        json.dump([], f, ensure_ascii=False)
                    count += 1
                except Exception:
                    pass
        return count


class ReplyCountStore:
    """
    私聊回复计数器管理类。
    负责持久化每个用户的 AI 回复次数、超限通知状态和 API 错误通知状态。
    """

    DEFAULT_DATA = {"meta": {"last_reset_date": ""}, "users": {}}

    def __init__(self, file_path):
        self.file_path = file_path
        self._lock = threading.RLock()
        self.data = self._load()

    @classmethod
    def _empty_data(cls):
        return {"meta": {"last_reset_date": ""}, "users": {}}

    @classmethod
    def _normalize_user_data(cls, user_data):
        if not isinstance(user_data, dict):
            user_data = {}
        try:
            ai_count = int(user_data.get("ai_count", 0))
        except Exception:
            ai_count = 0
        return {
            "ai_count": max(0, ai_count),
            "api_err_notified": bool(user_data.get("api_err_notified", False)),
            "limit_notified": bool(user_data.get("limit_notified", False)),
        }

    @classmethod
    def _normalize_data(cls, raw_data):
        if not isinstance(raw_data, dict):
            return cls._empty_data()
        meta = raw_data.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        users = raw_data.get("users", {})
        if not isinstance(users, dict):
            users = {}
        normalized_users = {}
        for user, user_data in users.items():
            user = str(user).strip()
            if user:
                normalized_users[user] = cls._normalize_user_data(user_data)
        return {
            "meta": {"last_reset_date": str(meta.get("last_reset_date", "") or "")},
            "users": normalized_users,
        }

    def _load(self):
        if not os.path.exists(self.file_path):
            return self._empty_data()
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return self._normalize_data(json.load(f))
        except Exception as e:
            log(level="WARNING", message=f"加载 reply_count.json 失败: {e}")
            return self._empty_data()

    def _save_locked(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        tmp_path = self.file_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, self.file_path)

    def save(self):
        with self._lock:
            self._save_locked()

    def get_user(self, user_key):
        user_key = str(user_key).strip()
        with self._lock:
            users = self.data.setdefault("users", {})
            if user_key not in users:
                users[user_key] = self._normalize_user_data({})
            else:
                users[user_key] = self._normalize_user_data(users[user_key])
            return users[user_key]

    def maybe_reset(self, reset_days, now=None):
        try:
            reset_days = int(reset_days)
        except Exception:
            reset_days = 0
        if reset_days <= 0:
            return False
        now = now or datetime.now()
        today = now.strftime("%Y-%m-%d")
        with self._lock:
            meta = self.data.setdefault("meta", {})
            last = str(meta.get("last_reset_date", "") or "")
            if not last:
                meta["last_reset_date"] = today
                self._save_locked()
                return False
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%d")
            except Exception:
                meta["last_reset_date"] = today
                self._save_locked()
                return False
            delta = (now - last_dt).days
            if delta >= reset_days:
                self.data["users"] = {}
                meta["last_reset_date"] = today
                self._save_locked()
                log(message=f"回复计数器已重置（周期 {reset_days} 天）")
                return True
        return False

    def increment_ai_count(self, user_key):
        with self._lock:
            user_data = self.get_user(user_key)
            user_data["ai_count"] = user_data.get("ai_count", 0) + 1
            self._save_locked()
            return user_data["ai_count"]

    def mark_limit_notified(self, user_key):
        with self._lock:
            user_data = self.get_user(user_key)
            if user_data.get("limit_notified"):
                return False
            user_data["limit_notified"] = True
            self._save_locked()
            return True

    def mark_api_err_notified(self, user_key):
        with self._lock:
            user_data = self.get_user(user_key)
            if user_data.get("api_err_notified"):
                return False
            user_data["api_err_notified"] = True
            self._save_locked()
            return True

    def clear_user(self, user_key):
        user_key = str(user_key).strip()
        with self._lock:
            users = self.data.setdefault("users", {})
            if user_key not in users:
                return False
            del users[user_key]
            self._save_locked()
            return True

    @staticmethod
    def was_send_success(result):
        if result is True:
            return True
        if result is False or result is None:
            return False
        if isinstance(result, dict):
            status = str(result.get("status", "")).lower()
            if status in ("success", "ok", "true"):
                return True
            if status in ("error", "fail", "failed", "false"):
                return False
            if result.get("code") == 0:
                return True
            if result.get("success") is True:
                return True
            if result.get("success") is False:
                return False
        return bool(result)
