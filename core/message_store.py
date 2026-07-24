import os
import sys
import json
import uuid
import hashlib
import threading
from datetime import datetime
import re
from logger import log


class MessageRecord:
    """消息记录对象，用于存储和标注消息信息"""

    def __init__(self):
        self.id = str(uuid.uuid4())        # 唯一标识
        self.chat_name = ""                # 会话名称（备注名）
        self.sender = ""                   # 发送者
        self.content = ""                  # 消息内容
        self.msg_type = ""                 # 消息类型（text/image/unknown）
        self.msg_attr = ""                 # 消息属性（friend/group/self/system）
        self.seq = 0                       # Chatlog 消息序号
        self.receive_time = ""             # 接收时间
        self.status = "pending"            # 状态：pending/processed/replied/confirmed/rejected
        self.reply_id = None               # 关联的回复 ID（回复对应关系）
        self.reply_content = ""            # 回复内容
        self.reply_time = ""               # 回复时间
        self.needs_confirm = False         # 是否需要确认
        self.confirm_status = "pending"    # 确认状态：pending/confirmed/rejected
        self.unread = False                # 是否未读

    def to_dict(self):
        """将消息记录转换为字典，用于持久化存储"""
        return {
            "id": self.id,
            "chat_name": self.chat_name,
            "sender": self.sender,
            "content": self.content,
            "msg_type": self.msg_type,
            "msg_attr": self.msg_attr,
            "seq": self.seq,
            "receive_time": self.receive_time,
            "status": self.status,
            "reply_id": self.reply_id,
            "reply_content": self.reply_content,
            "reply_time": self.reply_time,
            "needs_confirm": self.needs_confirm,
            "confirm_status": self.confirm_status,
            "unread": self.unread,
        }

    @classmethod
    def from_dict(cls, data):
        """从字典创建消息记录对象"""
        record = cls()
        record.id = data.get("id", str(uuid.uuid4()))
        record.chat_name = data.get("chat_name", "")
        record.sender = data.get("sender", "")
        record.content = data.get("content", "")
        record.msg_type = data.get("msg_type", "")
        record.msg_attr = data.get("msg_attr", "")
        record.seq = data.get("seq", 0)
        record.receive_time = data.get("receive_time", "")
        record.status = data.get("status", "pending")
        record.reply_id = data.get("reply_id")
        record.reply_content = data.get("reply_content", "")
        record.reply_time = data.get("reply_time", "")
        record.needs_confirm = data.get("needs_confirm", False)
        record.confirm_status = data.get("confirm_status", "pending")
        record.unread = data.get("unread", False)
        return record


class MessageStore:
    """
    消息存储管理类
    负责消息记录的存储、查询、更新和持久化
    存储路径：{base_path}/{wx_id}/{chat_name}_messages.json
    """

    WINDOWS_RESERVED_NAMES = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

    def __init__(self, wx_id, base_path=None):
        self.wx_id = wx_id
        self.base_path = base_path or os.path.join(
            os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.abspath("."),
            'config', 'message_store'
        )
        self._locks = {}         # chat_name -> threading.Lock()
        self._pending_confirm = []  # 待确认消息列表（内存缓存）
        self._pending_lock = threading.RLock()

    def _get_lock(self, chat_name):
        """获取指定会话的线程锁"""
        if chat_name not in self._locks:
            self._locks[chat_name] = threading.Lock()
        return self._locks[chat_name]

    @classmethod
    def _is_windows_reserved_name(cls, name):
        """判断名称是否为 Windows 保留名称"""
        stem = name.split('.', 1)[0].upper()
        return stem in cls.WINDOWS_RESERVED_NAMES

    @staticmethod
    def _hash_storage_name(name):
        """生成名称的哈希值作为存储文件名"""
        raw_name = str(name)
        return "hash" + hashlib.sha256(raw_name.encode('utf-8')).hexdigest()

    @classmethod
    def _resolve_storage_name(cls, chat_name):
        """
        将微信窗口名转换为 Windows 可用的目录/文件名前缀
        非法符号直接剔除；剔除后为空或仍不适合作为 Windows 名称时使用 hash 前缀兜底
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
        """写入原始名称记录文件"""
        name_path = os.path.join(dir_path, 'name.json')
        try:
            with open(name_path, 'w', encoding='utf-8') as f:
                json.dump({"name": str(chat_name)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(level="WARNING", message=f"写入消息存储原始名称记录失败: {e}")

    def _get_message_path(self, chat_name):
        """返回消息存储文件路径，并确保目录存在"""
        storage_name, should_write_name = self._resolve_storage_name(chat_name)
        dir_path = os.path.join(self.base_path, self.wx_id, storage_name)
        os.makedirs(dir_path, exist_ok=True)
        if should_write_name:
            self._write_original_name(dir_path, chat_name)
        return os.path.join(dir_path, f"{storage_name}_messages.json")

    def _normalize_message_time(self, message_time=None):
        """将时间统一转成存储使用的字符串格式"""
        if isinstance(message_time, datetime):
            return message_time.strftime("%Y/%m/%d %H:%M:%S")
        if isinstance(message_time, str):
            message_time = message_time.strip()
            if message_time:
                return message_time
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    def save_message(self, chat_name, sender, content, msg_type, msg_attr, seq=0, message_time=None):
        """
        保存一条消息到存储层

        :param chat_name: 会话名称
        :param sender: 发送者
        :param content: 消息内容
        :param msg_type: 消息类型
        :param msg_attr: 消息属性
        :param seq: Chatlog 消息序号
        :param message_time: 接收时间
        :return: MessageRecord 对象
        """
        record = MessageRecord()
        record.chat_name = chat_name
        record.sender = sender
        record.content = content
        record.msg_type = msg_type
        record.msg_attr = msg_attr
        record.seq = seq
        record.receive_time = self._normalize_message_time(message_time)

        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            messages.append(record.to_dict())
            if len(messages) > self._get_max_count():
                messages = messages[-self._get_max_count():]
            self._save_messages(path, messages)

        log(message=f"消息已保存: {chat_name} - {sender}: {content[:50]}")
        return record

    def _load_messages(self, path):
        """从文件加载消息列表"""
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                messages = json.load(f)
            if isinstance(messages, list):
                return messages
        except Exception as e:
            log(level="WARNING", message=f"加载消息存储文件失败: {e}")
        return []

    def _save_messages(self, path, messages):
        """将消息列表保存到文件（事务性写入）"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            log(level="ERROR", message=f"保存消息存储文件失败: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _get_max_count(self):
        """获取单会话最大存储消息数（从配置中读取，默认1000）"""
        try:
            from core.config_manager import WXBotConfig
            config = WXBotConfig()
            return config.message_store_max_count
        except Exception:
            return 1000

    def get_message(self, chat_name, message_id):
        """
        根据消息 ID 获取消息记录

        :param chat_name: 会话名称
        :param message_id: 消息 ID
        :return: MessageRecord 对象或 None
        """
        path = self._get_message_path(chat_name)
        messages = self._load_messages(path)
        for msg_data in messages:
            if msg_data.get("id") == message_id:
                return MessageRecord.from_dict(msg_data)
        return None

    def get_all_messages(self, chat_name, count=None):
        """
        获取指定会话的所有消息

        :param chat_name: 会话名称
        :param count: 返回消息数量（None 返回全部）
        :return: MessageRecord 对象列表
        """
        path = self._get_message_path(chat_name)
        messages = self._load_messages(path)
        if count is not None:
            messages = messages[-count:]
        return [MessageRecord.from_dict(m) for m in messages]

    def get_pending_messages(self, chat_name=None):
        """
        获取待处理消息列表

        :param chat_name: 会话名称（None 返回所有会话的待处理消息）
        :return: MessageRecord 对象列表
        """
        if chat_name:
            messages = self.get_all_messages(chat_name)
            return [m for m in messages if m.status == "pending"]
        else:
            all_pending = []
            try:
                base_dir = os.path.join(self.base_path, self.wx_id)
                if os.path.exists(base_dir):
                    for storage_dir in os.listdir(base_dir):
                        storage_path = os.path.join(base_dir, storage_dir)
                        if os.path.isdir(storage_path):
                            msg_file = os.path.join(storage_path, f"{storage_dir}_messages.json")
                            if os.path.exists(msg_file):
                                messages = self._load_messages(msg_file)
                                for msg_data in messages:
                                    record = MessageRecord.from_dict(msg_data)
                                    if record.status == "pending":
                                        all_pending.append(record)
            except Exception as e:
                log(level="ERROR", message=f"获取待处理消息失败: {e}")
            return all_pending

    def get_unread_messages(self, chat_name=None):
        """
        获取未读消息列表

        :param chat_name: 会话名称（None 返回所有会话的未读消息）
        :return: MessageRecord 对象列表
        """
        if chat_name:
            messages = self.get_all_messages(chat_name)
            return [m for m in messages if m.unread]
        else:
            all_unread = []
            try:
                base_dir = os.path.join(self.base_path, self.wx_id)
                if os.path.exists(base_dir):
                    for storage_dir in os.listdir(base_dir):
                        storage_path = os.path.join(base_dir, storage_dir)
                        if os.path.isdir(storage_path):
                            msg_file = os.path.join(storage_path, f"{storage_dir}_messages.json")
                            if os.path.exists(msg_file):
                                messages = self._load_messages(msg_file)
                                for msg_data in messages:
                                    record = MessageRecord.from_dict(msg_data)
                                    if record.unread:
                                        all_unread.append(record)
            except Exception as e:
                log(level="ERROR", message=f"获取未读消息失败: {e}")
            return all_unread

    def set_message_status(self, chat_name, message_id, status):
        """
        设置消息状态

        :param chat_name: 会话名称
        :param message_id: 消息 ID
        :param status: 状态值（pending/processed/replied/confirmed/rejected）
        :return: 是否更新成功
        """
        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            for i, msg_data in enumerate(messages):
                if msg_data.get("id") == message_id:
                    messages[i]["status"] = status
                    self._save_messages(path, messages)
                    log(message=f"消息状态已更新: {message_id} -> {status}")
                    return True
        return False

    def set_unread(self, chat_name, message_id, unread=True):
        """
        设置消息未读状态

        :param chat_name: 会话名称
        :param message_id: 消息 ID
        :param unread: 是否未读
        :return: 是否更新成功
        """
        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            for i, msg_data in enumerate(messages):
                if msg_data.get("id") == message_id:
                    messages[i]["unread"] = unread
                    self._save_messages(path, messages)
                    log(message=f"消息未读状态已更新: {message_id} -> {unread}")
                    return True
        return False

    def add_pending_confirm(self, record):
        """
        添加待确认消息到队列

        :param record: MessageRecord 对象
        :return: 是否添加成功
        """
        with self._pending_lock:
            record.needs_confirm = True
            record.confirm_status = "pending"
            record.status = "pending"

            path = self._get_message_path(record.chat_name)
            with self._get_lock(record.chat_name):
                messages = self._load_messages(path)
                for i, msg_data in enumerate(messages):
                    if msg_data.get("id") == record.id:
                        messages[i]["needs_confirm"] = True
                        messages[i]["confirm_status"] = "pending"
                        messages[i]["status"] = "pending"
                        self._save_messages(path, messages)
                        break

            if record not in self._pending_confirm:
                self._pending_confirm.append(record)

        log(message=f"消息已加入待确认队列: {record.id}")
        return True

    def get_pending_confirm(self):
        """
        获取待确认消息队列

        :return: MessageRecord 对象列表
        """
        with self._pending_lock:
            return list(self._pending_confirm)

    def confirm_message(self, chat_name, message_id):
        """
        确认消息（同意回复）

        :param chat_name: 会话名称
        :param message_id: 消息 ID
        :return: MessageRecord 对象或 None
        """
        record = self.get_message(chat_name, message_id)
        if not record:
            return None

        with self._pending_lock:
            record.confirm_status = "confirmed"
            record.status = "confirmed"

            path = self._get_message_path(chat_name)
            with self._get_lock(chat_name):
                messages = self._load_messages(path)
                for i, msg_data in enumerate(messages):
                    if msg_data.get("id") == message_id:
                        messages[i]["confirm_status"] = "confirmed"
                        messages[i]["status"] = "confirmed"
                        self._save_messages(path, messages)
                        break

            if record in self._pending_confirm:
                self._pending_confirm.remove(record)

        log(message=f"消息已确认: {message_id}")
        return record

    def reject_message(self, chat_name, message_id):
        """
        拒绝消息（不回复）

        :param chat_name: 会话名称
        :param message_id: 消息 ID
        :return: MessageRecord 对象或 None
        """
        record = self.get_message(chat_name, message_id)
        if not record:
            return None

        with self._pending_lock:
            record.confirm_status = "rejected"
            record.status = "rejected"

            path = self._get_message_path(chat_name)
            with self._get_lock(chat_name):
                messages = self._load_messages(path)
                for i, msg_data in enumerate(messages):
                    if msg_data.get("id") == message_id:
                        messages[i]["confirm_status"] = "rejected"
                        messages[i]["status"] = "rejected"
                        self._save_messages(path, messages)
                        break

            if record in self._pending_confirm:
                self._pending_confirm.remove(record)

        log(message=f"消息已拒绝: {message_id}")
        return record

    def bind_reply(self, chat_name, message_id, reply_content, reply_time=None):
        """
        绑定消息与回复的对应关系

        :param chat_name: 会话名称
        :param message_id: 消息 ID
        :param reply_content: 回复内容
        :param reply_time: 回复时间
        :return: 是否绑定成功
        """
        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            for i, msg_data in enumerate(messages):
                if msg_data.get("id") == message_id:
                    messages[i]["reply_content"] = reply_content
                    messages[i]["reply_time"] = self._normalize_message_time(reply_time)
                    messages[i]["reply_id"] = str(uuid.uuid4())
                    messages[i]["status"] = "replied"
                    messages[i]["unread"] = False
                    self._save_messages(path, messages)
                    log(message=f"消息回复已绑定: {message_id}")
                    return True
        return False

    def get_replied_messages(self, chat_name=None):
        """
        获取已回复消息列表

        :param chat_name: 会话名称（None 返回所有会话的已回复消息）
        :return: MessageRecord 对象列表
        """
        if chat_name:
            messages = self.get_all_messages(chat_name)
            return [m for m in messages if m.status == "replied"]
        else:
            all_replied = []
            try:
                base_dir = os.path.join(self.base_path, self.wx_id)
                if os.path.exists(base_dir):
                    for storage_dir in os.listdir(base_dir):
                        storage_path = os.path.join(base_dir, storage_dir)
                        if os.path.isdir(storage_path):
                            msg_file = os.path.join(storage_path, f"{storage_dir}_messages.json")
                            if os.path.exists(msg_file):
                                messages = self._load_messages(msg_file)
                                for msg_data in messages:
                                    record = MessageRecord.from_dict(msg_data)
                                    if record.status == "replied":
                                        all_replied.append(record)
            except Exception as e:
                log(level="ERROR", message=f"获取已回复消息失败: {e}")
            return all_replied

    def search_messages(self, keyword, chat_name=None):
        """
        搜索包含关键词的消息

        :param keyword: 搜索关键词
        :param chat_name: 会话名称（None 搜索所有会话）
        :return: MessageRecord 对象列表
        """
        if chat_name:
            messages = self.get_all_messages(chat_name)
            return [m for m in messages if keyword in m.content]
        else:
            results = []
            try:
                base_dir = os.path.join(self.base_path, self.wx_id)
                if os.path.exists(base_dir):
                    for storage_dir in os.listdir(base_dir):
                        storage_path = os.path.join(base_dir, storage_dir)
                        if os.path.isdir(storage_path):
                            msg_file = os.path.join(storage_path, f"{storage_dir}_messages.json")
                            if os.path.exists(msg_file):
                                messages = self._load_messages(msg_file)
                                for msg_data in messages:
                                    record = MessageRecord.from_dict(msg_data)
                                    if keyword in record.content:
                                        results.append(record)
            except Exception as e:
                log(level="ERROR", message=f"搜索消息失败: {e}")
            return results
