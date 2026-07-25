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
    支持 Redis 存储后端，Redis 不可用时自动降级到本地 JSON 文件存储

    Redis Key 格式：
    - 消息列表：wxbot:{wx_id}:messages:{chat_name}（List）
    - 消息状态：wxbot:{wx_id}:msg_status:{message_id}（String）
    - 待确认队列：wxbot:{wx_id}:pending_confirm（List）
    - 待确认详情：wxbot:{wx_id}:pending_confirm:{message_id}（Hash）
    """

    WINDOWS_RESERVED_NAMES = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

    def __init__(self, wx_id, config=None, base_path=None):
        """
        初始化消息存储管理器

        :param wx_id: 微信 ID
        :param config: 配置对象，包含 Redis 配置和最大消息数
        :param base_path: 本地存储基础路径（降级时使用）
        """
        self.wx_id = wx_id
        self.config = config

        self.base_path = base_path or os.path.join(
            os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.abspath("."),
            'config', 'message_store'
        )
        self._locks = {}
        self._pending_lock = threading.RLock()

        self._redis_manager = None
        self._init_redis()

    def _init_redis(self):
        """初始化 Redis 连接"""
        if self.config and getattr(self.config, 'redis_enabled', False):
            try:
                from core.redis_manager import RedisManager
                redis_config = {
                    'host': getattr(self.config, 'redis_host', 'localhost'),
                    'port': getattr(self.config, 'redis_port', 6379),
                    'db': getattr(self.config, 'redis_db', 0),
                    'password': getattr(self.config, 'redis_password', None),
                    'timeout': getattr(self.config, 'redis_timeout', 5),
                    'retry_count': getattr(self.config, 'redis_retry_count', 3),
                    'fallback': getattr(self.config, 'redis_fallback', True),
                    'fallback_path': os.path.join(
                        os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.abspath("."),
                        'config', 'redis_fallback.json'
                    )
                }
                self._redis_manager = RedisManager(redis_config)
                log(message=f"Redis 存储初始化完成: {self.config.redis_host}:{self.config.redis_port}/db{self.config.redis_db}")
            except Exception as e:
                log(level="ERROR", message=f"Redis 初始化失败，将使用本地文件存储: {e}")

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

    def _get_max_count(self):
        """获取单会话最大存储消息数"""
        if self.config:
            return getattr(self.config, 'message_store_max_count', 1000)
        try:
            from core.config_manager import WXBotConfig
            config = WXBotConfig()
            return config.message_store_max_count
        except Exception:
            return 1000

    def _is_redis_available(self):
        """检查 Redis 是否可用"""
        return self._redis_manager is not None and self._redis_manager.is_available()

    def _get_messages_key(self, chat_name):
        """生成消息列表的 Redis Key"""
        safe_chat_name = self.INVALID_FILENAME_CHARS_RE.sub('_', str(chat_name))
        return f"wxbot:{self.wx_id}:messages:{safe_chat_name}"

    def _get_msg_status_key(self, message_id):
        """生成消息状态的 Redis Key"""
        return f"wxbot:{self.wx_id}:msg_status:{message_id}"

    def _get_pending_confirm_key(self):
        """生成待确认队列的 Redis Key"""
        return f"wxbot:{self.wx_id}:pending_confirm"

    def _get_pending_confirm_detail_key(self, message_id):
        """生成待确认详情的 Redis Key"""
        return f"wxbot:{self.wx_id}:pending_confirm:{message_id}"

    def _redis_save_message(self, chat_name, record_dict):
        """使用 Redis 保存消息"""
        if not self._redis_manager:
            return False
        try:
            key = self._get_messages_key(chat_name)
            max_count = self._get_max_count()

            self._redis_manager.lpush(key, record_dict)

            current_len = self._redis_manager._client.llen(key) if hasattr(self._redis_manager, '_client') and self._redis_manager._client else None
            if current_len is not None and current_len > max_count:
                self._redis_manager._client.ltrim(key, 0, max_count - 1)

            status_key = self._get_msg_status_key(record_dict['id'])
            self._redis_manager.set(status_key, record_dict['status'])

            return True
        except Exception as e:
            log(level="WARNING", message=f"Redis 保存消息失败: {e}")
            return False

    def _redis_get_messages(self, chat_name, count=None):
        """从 Redis 获取消息列表"""
        if not self._redis_manager:
            return None
        try:
            key = self._get_messages_key(chat_name)
            messages = []

            client = self._redis_manager._client if hasattr(self._redis_manager, '_client') else None
            if not client:
                return None

            length = client.llen(key)
            if length == 0:
                return []

            start = 0
            end = -1 if count is None else min(count - 1, length - 1)
            raw_messages = client.lrange(key, start, end)

            for raw_msg in raw_messages:
                try:
                    if isinstance(raw_msg, bytes):
                        raw_msg = raw_msg.decode('utf-8')
                    msg_data = json.loads(raw_msg)
                    messages.append(msg_data)
                except (json.JSONDecodeError, ValueError):
                    continue

            return messages
        except Exception as e:
            log(level="WARNING", message=f"Redis 获取消息失败: {e}")
            return None

    def _redis_update_message(self, chat_name, message_id, updates):
        """更新 Redis 中的消息"""
        if not self._redis_manager:
            return False
        try:
            key = self._get_messages_key(chat_name)
            client = self._redis_manager._client if hasattr(self._redis_manager, '_client') else None
            if not client:
                return False

            length = client.llen(key)
            for i in range(length):
                raw_msg = client.lindex(key, i)
                if raw_msg:
                    try:
                        if isinstance(raw_msg, bytes):
                            raw_msg = raw_msg.decode('utf-8')
                        msg_data = json.loads(raw_msg)
                        if msg_data.get('id') == message_id:
                            msg_data.update(updates)
                            client.lset(key, i, json.dumps(msg_data))

                            if 'status' in updates:
                                status_key = self._get_msg_status_key(message_id)
                                self._redis_manager.set(status_key, updates['status'])

                            return True
                    except (json.JSONDecodeError, ValueError):
                        continue
            return False
        except Exception as e:
            log(level="WARNING", message=f"Redis 更新消息失败: {e}")
            return False

    def _redis_add_pending_confirm(self, record):
        """将消息添加到 Redis 待确认队列"""
        if not self._redis_manager:
            return False
        try:
            queue_key = self._get_pending_confirm_key()
            detail_key = self._get_pending_confirm_detail_key(record.id)

            self._redis_manager.lpush(queue_key, record.id)

            record_dict = record.to_dict()
            for k, v in record_dict.items():
                value = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                self._redis_manager.hset(detail_key, k, value)

            return True
        except Exception as e:
            log(level="WARNING", message=f"Redis 添加待确认消息失败: {e}")
            return False

    def _redis_get_pending_confirm(self):
        """从 Redis 获取待确认消息列表"""
        if not self._redis_manager:
            return None
        try:
            queue_key = self._get_pending_confirm_key()
            client = self._redis_manager._client if hasattr(self._redis_manager, '_client') else None
            if not client:
                return None

            message_ids = client.lrange(queue_key, 0, -1)
            records = []

            for msg_id in message_ids:
                if isinstance(msg_id, bytes):
                    msg_id = msg_id.decode('utf-8')

                detail_key = self._get_pending_confirm_detail_key(msg_id)
                raw_data = self._redis_manager._client.hgetall(detail_key) if client else {}
                if raw_data:
                    record_dict = {}
                    for k, v in raw_data.items():
                        if isinstance(k, bytes):
                            k = k.decode('utf-8')
                        if isinstance(v, bytes):
                            v = v.decode('utf-8')
                        try:
                            record_dict[k] = json.loads(v)
                        except json.JSONDecodeError:
                            record_dict[k] = v
                    records.append(MessageRecord.from_dict(record_dict))

            return records
        except Exception as e:
            log(level="WARNING", message=f"Redis 获取待确认消息失败: {e}")
            return None

    def _redis_remove_pending_confirm(self, message_id):
        """从 Redis 待确认队列中移除消息"""
        if not self._redis_manager:
            return False
        try:
            queue_key = self._get_pending_confirm_key()
            detail_key = self._get_pending_confirm_detail_key(message_id)

            client = self._redis_manager._client if hasattr(self._redis_manager, '_client') else None
            if client:
                client.lrem(queue_key, 0, message_id)

            self._redis_manager.delete(detail_key)

            return True
        except Exception as e:
            log(level="WARNING", message=f"Redis 移除待确认消息失败: {e}")
            return False

    def _load_messages(self, path):
        """从文件加载消息列表（降级时使用）"""
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
        """将消息列表保存到文件（事务性写入，降级时使用）"""
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

        record_dict = record.to_dict()

        if self._is_redis_available():
            if self._redis_save_message(chat_name, record_dict):
                log(message=f"消息已保存(Redis): {chat_name} - {sender}: {content[:50]}")
                return record

        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            messages.append(record_dict)
            if len(messages) > self._get_max_count():
                messages = messages[-self._get_max_count():]
            self._save_messages(path, messages)

        log(message=f"消息已保存(File): {chat_name} - {sender}: {content[:50]}")
        return record

    def get_message(self, chat_name, message_id):
        """
        根据消息 ID 获取消息记录

        :param chat_name: 会话名称
        :param message_id: 消息 ID
        :return: MessageRecord 对象或 None
        """
        if self._is_redis_available():
            messages = self._redis_get_messages(chat_name)
            if messages is not None:
                for msg_data in messages:
                    if msg_data.get("id") == message_id:
                        return MessageRecord.from_dict(msg_data)

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
        messages = None
        
        if self._is_redis_available():
            messages = self._redis_get_messages(chat_name, count)
        
        if messages is None or len(messages) == 0:
            path = self._get_message_path(chat_name)
            messages = self._load_messages(path)
            if count is not None:
                messages = messages[-count:]
        
        return [MessageRecord.from_dict(m) for m in messages]

    def _get_all_possible_keys(self, chat_name, wxid=None):
        """
        获取所有可能的消息存储键名，支持通过备注名、wxid 等多种方式查找

        :param chat_name: 会话名称（备注名）
        :param wxid: 微信号（可选）
        :return: 可能的键名列表
        """
        keys = []
        if chat_name:
            keys.append(self._get_messages_key(chat_name))
        if wxid and wxid != chat_name:
            keys.append(self._get_messages_key(wxid))
        
        if hasattr(self, '_bot') and self._bot and hasattr(self._bot, 'chatlog_contact_map'):
            contact_map = self._bot.chatlog_contact_map
            for key in [chat_name, wxid]:
                if key and key in contact_map:
                    contact = contact_map[key]
                    if contact.get('remark'):
                        keys.append(self._get_messages_key(contact['remark']))
                    if contact.get('userName') and contact['userName'] not in [chat_name, wxid]:
                        keys.append(self._get_messages_key(contact['userName']))
        
        return list(set(keys))

    def get_all_messages_with_fallback(self, chat_name, wxid=None, count=None):
        """
        获取指定会话的所有消息，支持多种键名回退查找

        :param chat_name: 会话名称（备注名）
        :param wxid: 微信号（可选，用于补充查找）
        :param count: 返回消息数量（None 返回全部）
        :return: MessageRecord 对象列表
        """
        log("DEBUG", f"[MessageStore] get_all_messages_with_fallback 开始，chat_name={chat_name}, wxid={wxid}, count={count}")
        all_keys = self._get_all_possible_keys(chat_name, wxid)
        log("DEBUG", f"[MessageStore] 生成的查找键列表: {all_keys}")
        
        for key in all_keys:
            if self._is_redis_available():
                try:
                    safe_chat_name = key.split(':')[-1]
                    log("DEBUG", f"[MessageStore] 尝试从Redis获取消息，key={key}, safe_chat_name={safe_chat_name}")
                    messages = self._redis_get_messages(safe_chat_name, count)
                    if messages and len(messages) > 0:
                        log("DEBUG", f"[MessageStore] Redis查找成功，找到 {len(messages)} 条消息")
                        return [MessageRecord.from_dict(m) for m in messages]
                    else:
                        log("DEBUG", f"[MessageStore] Redis查找为空，继续尝试下一个键")
                except Exception as e:
                    log("DEBUG", f"[MessageStore] Redis查找异常: {e}，继续尝试下一个键")
                    continue
            else:
                log("DEBUG", f"[MessageStore] Redis不可用，跳过Redis查找")
        
        log("DEBUG", f"[MessageStore] Redis未找到消息，回退到本地文件查找")
        path = self._get_message_path(chat_name)
        log("DEBUG", f"[MessageStore] 本地文件路径: {path}")
        messages = self._load_messages(path)
        log("DEBUG", f"[MessageStore] 本地文件加载到 {len(messages)} 条消息")
        if count is not None:
            messages = messages[-count:]
            log("DEBUG", f"[MessageStore] 按count={count}截取后剩余 {len(messages)} 条消息")
        
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
        if self._is_redis_available():
            if self._redis_update_message(chat_name, message_id, {"status": status}):
                log(message=f"消息状态已更新(Redis): {message_id} -> {status}")
                return True

        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            for i, msg_data in enumerate(messages):
                if msg_data.get("id") == message_id:
                    messages[i]["status"] = status
                    self._save_messages(path, messages)
                    log(message=f"消息状态已更新(File): {message_id} -> {status}")
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
        if self._is_redis_available():
            if self._redis_update_message(chat_name, message_id, {"unread": unread}):
                log(message=f"消息未读状态已更新(Redis): {message_id} -> {unread}")
                return True

        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            for i, msg_data in enumerate(messages):
                if msg_data.get("id") == message_id:
                    messages[i]["unread"] = unread
                    self._save_messages(path, messages)
                    log(message=f"消息未读状态已更新(File): {message_id} -> {unread}")
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

            if self._is_redis_available():
                if self._redis_add_pending_confirm(record):
                    log(message=f"消息已加入待确认队列(Redis): {record.id}")
                    return True

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

            if record not in getattr(self, '_pending_confirm', []):
                if not hasattr(self, '_pending_confirm'):
                    self._pending_confirm = []
                self._pending_confirm.append(record)

        log(message=f"消息已加入待确认队列(File): {record.id}")
        return True

    def get_pending_confirm(self):
        """
        获取待确认消息队列

        :return: MessageRecord 对象列表
        """
        if self._is_redis_available():
            records = self._redis_get_pending_confirm()
            if records is not None:
                return records

        with self._pending_lock:
            return list(getattr(self, '_pending_confirm', []))

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

            if self._is_redis_available():
                self._redis_update_message(chat_name, message_id, {
                    "confirm_status": "confirmed",
                    "status": "confirmed"
                })
                self._redis_remove_pending_confirm(message_id)
            else:
                path = self._get_message_path(chat_name)
                with self._get_lock(chat_name):
                    messages = self._load_messages(path)
                    for i, msg_data in enumerate(messages):
                        if msg_data.get("id") == message_id:
                            messages[i]["confirm_status"] = "confirmed"
                            messages[i]["status"] = "confirmed"
                            self._save_messages(path, messages)
                            break

                if hasattr(self, '_pending_confirm') and record in self._pending_confirm:
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

            if self._is_redis_available():
                self._redis_update_message(chat_name, message_id, {
                    "confirm_status": "rejected",
                    "status": "rejected"
                })
                self._redis_remove_pending_confirm(message_id)
            else:
                path = self._get_message_path(chat_name)
                with self._get_lock(chat_name):
                    messages = self._load_messages(path)
                    for i, msg_data in enumerate(messages):
                        if msg_data.get("id") == message_id:
                            messages[i]["confirm_status"] = "rejected"
                            messages[i]["status"] = "rejected"
                            self._save_messages(path, messages)
                            break

                if hasattr(self, '_pending_confirm') and record in self._pending_confirm:
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
        updates = {
            "reply_content": reply_content,
            "reply_time": self._normalize_message_time(reply_time),
            "reply_id": str(uuid.uuid4()),
            "status": "replied",
            "unread": False
        }

        if self._is_redis_available():
            if self._redis_update_message(chat_name, message_id, updates):
                log(message=f"消息回复已绑定(Redis): {message_id}")
                return True

        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            messages = self._load_messages(path)
            for i, msg_data in enumerate(messages):
                if msg_data.get("id") == message_id:
                    messages[i].update(updates)
                    self._save_messages(path, messages)
                    log(message=f"消息回复已绑定(File): {message_id}")
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

    def get_history(self, chat_name, count=None, wxid=None):
        """
        获取 AI 兼容格式的历史消息

        :param chat_name: 会话名称
        :param count: 返回消息数量（None 返回全部）
        :param wxid: 微信号（可选，用于补充查找）
        :return: 历史消息列表，格式：[{"time": "xxx", "type": "xxx", "attr": "friend/group/self", "sender": "xxx", "content": "xxx"}]
        """
        if wxid:
            messages = self.get_all_messages_with_fallback(chat_name, wxid, count)
        else:
            messages = self.get_all_messages(chat_name, count)
        history = []

        for msg in messages:
            msg_type = str(msg.msg_type)

            attr = str(msg.msg_attr)

            history.append({
                "time": msg.receive_time,
                "type": msg_type,
                "attr": attr,
                "sender": msg.sender,
                "content": msg.content
            })

            if msg.reply_content:
                history.append({
                    "time": msg.reply_time or msg.receive_time,
                    "type": "text",
                    "attr": "self",
                    "sender": "self",
                    "content": msg.reply_content
                })

        return history

    def get_stats(self):
        """
        获取消息统计信息

        :return: 统计字典，包含 pending_confirm, processed, replied, total
        """
        stats = {
            'pending_confirm': 0,
            'processed': 0,
            'replied': 0,
            'total': 0
        }

        if self._is_redis_available():
            try:
                base_key = f"wxbot:{self.wx_id}:messages:"
                all_keys = self._redis_manager.keys(f"{base_key}*")
                for key in all_keys:
                    messages_data = self._redis_manager.get(key)
                    if messages_data:
                        try:
                            messages = json.loads(messages_data)
                            for msg in messages:
                                stats['total'] += 1
                                status = msg.get('status', '')
                                if status == 'processed':
                                    stats['processed'] += 1
                                elif status == 'replied':
                                    stats['replied'] += 1
                        except (json.JSONDecodeError, TypeError):
                            pass
                
                pending_key = f"wxbot:{self.wx_id}:messages:pending_confirm"
                pending_data = self._redis_manager.get(pending_key)
                if pending_data:
                    try:
                        pending_list = json.loads(pending_data)
                        stats['pending_confirm'] = len(pending_list)
                    except (json.JSONDecodeError, TypeError):
                        pass
            except Exception as e:
                log(level="WARNING", message=f"Redis 获取消息统计失败: {e}")
                pass

        else:
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
                                    stats['total'] += 1
                                    status = msg_data.get('status', '')
                                    if status == 'processed':
                                        stats['processed'] += 1
                                    elif status == 'replied':
                                        stats['replied'] += 1
                
                if hasattr(self, '_pending_confirm'):
                    stats['pending_confirm'] = len(self._pending_confirm)
            except Exception as e:
                log(level="WARNING", message=f"文件获取消息统计失败: {e}")
                pass

        return stats

    def clear_messages(self, chat_name):
        """
        清空指定会话的消息记录

        :param chat_name: 会话名称
        """
        if self._is_redis_available():
            try:
                key = self._get_messages_key(chat_name)
                self._redis_manager.delete(key)
                log(message=f"消息已清空(Redis): {chat_name}")
                return
            except Exception as e:
                log(level="WARNING", message=f"Redis 清空消息失败: {e}")

        path = self._get_message_path(chat_name)
        with self._get_lock(chat_name):
            self._save_messages(path, [])
            log(message=f"消息已清空(File): {chat_name}")

    def clear_all_messages(self):
        """
        清空所有会话的消息记录

        :return: 清除的会话数
        """
        count = 0
        if self._is_redis_available():
            try:
                pattern = f"wxbot:{self.wx_id}:messages:*"
                keys = self._redis_manager._client.keys(pattern) if hasattr(self._redis_manager, '_client') else []
                for key in keys:
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    self._redis_manager.delete(key)
                    count += 1
                log(message=f"所有消息已清空(Redis): {count} 个会话")
                return count
            except Exception as e:
                log(level="WARNING", message=f"Redis 清空所有消息失败: {e}")

        base = os.path.join(self.base_path, self.wx_id)
        if not os.path.exists(base):
            return count
        for chat_dir in os.listdir(base):
            msg_file = os.path.join(base, chat_dir, f"{chat_dir}_messages.json")
            if os.path.exists(msg_file):
                try:
                    with self._get_lock(chat_dir):
                        self._save_messages(msg_file, [])
                    count += 1
                except Exception:
                    pass
        log(message=f"所有消息已清空(File): {count} 个会话")
        return count