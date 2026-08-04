import os
import json
import threading
from datetime import datetime
from logger import log


class MemoryManager:
    """
    对话记忆管理类（代理模式）
    作为 MessageStore 的代理，提供兼容的 API 接口。
    所有存储操作委托给 MessageStore，间接获得 Redis 支持。
    """

    def __init__(self, message_store):
        """
        初始化记忆管理器（代理模式）

        :param message_store: MessageStore 实例，所有存储操作委托给它
        """
        self.message_store = message_store
        self._locks = {}

    def _get_lock(self, chat_name):
        """获取指定会话的锁，确保线程安全"""
        if chat_name not in self._locks:
            self._locks[chat_name] = threading.Lock()
        return self._locks[chat_name]

    def get_messages(self, chat_name, count):
        """
        获取最近 count 条记忆，返回 AI 兼容格式的消息历史

        :param chat_name: 会话名称
        :param count: 返回消息数量
        :return: 消息历史列表，格式：[{"time": "xxx", "type": "xxx", "attr": "xxx", "sender": "xxx", "content": "xxx"}]
        """
        if not self.message_store:
            return []
        try:
            return self.message_store.get_history(chat_name, count)
        except Exception as e:
            log(level="WARNING", message=f"MemoryManager 获取消息失败: {e}")
            return []

    def save_message(self, chat_name, sender, content, msg_type, msg_attr, max_count, message_time=None):
        """
        保存一条消息到记忆存储（委托给 MessageStore）

        :param chat_name: 会话名称
        :param sender: 发送者
        :param content: 消息内容
        :param msg_type: 消息类型（text/image/unknown）
        :param msg_attr: 消息属性（friend/group/self/system）
        :param max_count: 最大存储消息数（已由 MessageStore 内部管理，此处保留兼容）
        :param message_time: 消息时间（可选，默认当前时间）
        """
        if not self.message_store:
            return
        try:
            self.message_store.save_message(
                chat_name=chat_name,
                sender=sender,
                content=content,
                msg_type=msg_type,
                msg_attr=msg_attr,
                seq=0,
                message_time=message_time
            )
        except Exception as e:
            log(level="WARNING", message=f"MemoryManager 保存消息失败: {e}")

    def clear_messages(self, chat_name):
        """
        清空指定会话的对话记忆（委托给 MessageStore）

        :param chat_name: 会话名称
        """
        if not self.message_store:
            return
        try:
            if hasattr(self.message_store, 'clear_messages'):
                self.message_store.clear_messages(chat_name)
            else:
                log(level="WARNING", message="MessageStore 未实现 clear_messages 方法")
        except Exception as e:
            log(level="WARNING", message=f"MemoryManager 清空消息失败: {e}")

    def clear_all_messages(self):
        """
        清空所有会话的对话记忆（委托给 MessageStore）

        :return: 清除的会话数
        """
        if not self.message_store:
            return 0
        try:
            if hasattr(self.message_store, 'clear_all_messages'):
                return self.message_store.clear_all_messages()
            else:
                log(level="WARNING", message="MessageStore 未实现 clear_all_messages 方法")
                return 0
        except Exception as e:
            log(level="WARNING", message=f"MemoryManager 清空所有消息失败: {e}")
            return 0


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
            status = str(result.get("status", "")).strip()
            if status in ("成功", "success", "ok", "true", "已完成"):
                return True
            if status in ("失败", "错误", "error", "fail", "failed", "false"):
                return False
            if result.get("code") == 0:
                return True
            if result.get("success") is True:
                return True
            if result.get("success") is False:
                return False
        return bool(result)