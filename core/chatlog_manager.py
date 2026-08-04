from datetime import datetime, timedelta
import types
import traceback
import re
import time
import json
from typing import Optional

from chatlog_client import ChatlogClient, ChatlogError
from core.message_store import MessageStore
from logger import log


class ChatlogManager:
    """
    Chatlog 模块管理
    负责通过 Chatlog API 轮询监听消息、处理消息、增强上下文等功能。
    支持 Redis 缓存联系人数据，Redis 不可用时自动降级到内存缓存。
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.message_store: Optional[MessageStore] = bot.message_store if hasattr(bot, 'message_store') else None
        self.wx_lock = bot.wx_lock if hasattr(bot, 'wx_lock') else None

    def _get_wx_id(self):
        """获取当前微信账号的唯一标识，用于构建 Redis Key"""
        if hasattr(self.bot, 'message_store') and self.bot.message_store:
            return self.bot.message_store.wx_id
        return self.bot.wx.nickname if hasattr(self.bot, 'wx') and self.bot.wx else 'default'

    def _get_contacts_key(self):
        """生成联系人映射的 Redis Key，格式：wxbot:{wx_id}:contacts"""
        return f"wxbot:{self._get_wx_id()}:contacts"

    def _get_contacts_list_key(self):
        """生成联系人列表的 Redis Key，格式：wxbot:{wx_id}:contacts:list"""
        return f"wxbot:{self._get_wx_id()}:contacts:list"

    def _is_redis_available(self):
        """检查 Redis 是否可用"""
        return hasattr(self.bot, 'redis_manager') and self.bot.redis_manager and self.bot.redis_manager.is_available()

    def _init_chatlog_client(self):
        """
        初始化 Chatlog 客户端（若配置开启）。
        
        启动时优先从 Redis 加载联系人缓存，若 Redis 中存在缓存则直接使用，
        无需调用 Chatlog API。若 Redis 不可用或缓存不存在，则调用 refresh_chatlog_contacts
        从 Chatlog API 获取联系人数据。
        """
        if not self.config.chatlog_listen_switch:
            return
        
        try:
            self.bot.chatlog_client = ChatlogClient(
                base_url=self.config.chatlog_url,
                timeout=self.config.chatlog_request_timeout
            )
            self.bot.chatlog_contact_map = {}
            self.bot.chatlog_last_seq = {}

            if self._is_redis_available():
                contacts_map = self._load_contacts_from_redis()
                if contacts_map:
                    self.bot.chatlog_contact_map = contacts_map
                    log(message=f"Chatlog 客户端初始化成功，从 Redis 加载 {len(contacts_map)} 条联系人数据")
                    return

            self.refresh_chatlog_contacts()
            log(message="Chatlog 客户端初始化成功")
        except ImportError:
            log(level="ERROR", message="未安装 chatlog_client 模块，请安装后再开启 Chatlog 监听模式")
            self.config.chatlog_listen_switch = False
        except Exception as e:
            log(level="ERROR", message=f"Chatlog 客户端初始化失败: {e}")
            self.config.chatlog_listen_switch = False

    def _load_contacts_from_redis(self):
        """
        从 Redis 加载联系人缓存数据。
        
        Returns:
            dict: 联系人映射字典，key 为 wxid/remark，value 为联系人完整信息；
                  若 Redis 不可用或无缓存数据则返回 None
        """
        try:
            contacts_key = self._get_contacts_key()
            contacts_list_key = self._get_contacts_list_key()

            contacts_map = self.bot.redis_manager.hgetall(contacts_key)
            if not contacts_map:
                return None

            log(message=f"成功从 Redis 加载 {len(contacts_map)} 条联系人数据")
            return contacts_map
        except Exception as e:
            log(level="WARNING", message=f"从 Redis 加载联系人数据失败: {e}")
            return None

    def _save_contacts_to_redis(self, contacts_map):
        """
        将联系人数据保存到 Redis。
        
        Args:
            contacts_map (dict): 联系人映射字典
            
        Returns:
            bool: 是否保存成功
        """
        try:
            if not self._is_redis_available():
                return False

            contacts_key = self._get_contacts_key()
            contacts_list_key = self._get_contacts_list_key()

            self.bot.redis_manager.delete(contacts_key, contacts_list_key)

            for key, contact in contacts_map.items():
                self.bot.redis_manager.hset(contacts_key, key, contact)

            log(message=f"成功将 {len(contacts_map)} 条联系人数据保存到 Redis")
            return True
        except Exception as e:
            log(level="WARNING", message=f"保存联系人数据到 Redis 失败: {e}")
            return False

    def refresh_chatlog_contacts(self):
        """
        刷新 Chatlog 联系人缓存。
        
        调用 Chatlog API 获取所有联系人，构建 userName、remark 的映射，
        用于在关键词匹配失败时扩展匹配范围。
        
        刷新流程：
        1. 调用 Chatlog API 获取联系人数据
        2. 构建联系人映射字典
        3. 优先更新 Redis 缓存（若 Redis 可用）
        4. 更新内存中的 chatlog_contact_map
        5. Redis 不可用时仅更新内存缓存，功能不受影响
        
        映射逻辑：
        - 将每个联系人的 wxid、remark 映射到完整联系人信息
        - 例如：wxid_xxx -> contact, remark -> contact
        - 这样当用户使用备注名搜索但系统存储的是 wxid 时，也能通过映射找到对应联系人
        """
        if not self.bot.chatlog_client:
            return

        try:
            contacts = self.bot.chatlog_client.search_contact(is_friend=1)

            if not contacts:
                return

            new_map = {}

            contacts_items = contacts.get('items', [])

            for contact in contacts_items:
                wxid = contact.get('userName', '')
                nickname = contact.get('nickName', '')
                alias = contact.get('alias', '')
                remark = contact.get('remark', '')

                new_map[wxid] = contact

                if remark:
                    new_map[remark] = contact

            if self._is_redis_available():
                self._save_contacts_to_redis(new_map)

            self.bot.chatlog_contact_map = new_map

            log(message=f"Chatlog 联系人缓存已更新，共 {len(contacts_items)} 条记录")

        except ChatlogError as e:
            log(level="ERROR", message=f"刷新 Chatlog 联系人失败: {e}")
        except Exception as e:
            log(level="ERROR", message=f"刷新 Chatlog 联系人异常: {e}")

    def _enrich_context_with_chatlog(self, chat_name, base_history=None):
        """
        合并 Chatlog 历史消息与 MemoryManager 短期记忆，增强 AI 回复上下文。
        
        :param chat_name:   聊天对象名称
        :param base_history: MemoryManager 获取的基础历史消息列表
        :return:            合并后的历史消息列表
        """
        if not self.config.chatlog_context_switch or not self.bot.chatlog_client:
            return base_history or []
        
        try:
            chatlog_msgs = self.bot.chatlog_client.get_chatlog(
                talker=chat_name, 
                limit=self.config.chatlog_context_count
            )
            
            if not chatlog_msgs:
                return base_history or []
            
            chatlog_history = []
            for msg in chatlog_msgs:
                if msg.get('isSelf', False):
                    role = 'assistant'
                else:
                    role = 'user'
                
                content = msg.get('content', '')
                if content:
                    chatlog_history.append({"role": role, "content": content})
            
            base_history = base_history or []
            
            merged_history = base_history + chatlog_history
            
            total_limit = self.config.memory_context_count + self.config.chatlog_context_count
            if len(merged_history) > total_limit:
                merged_history = merged_history[-total_limit:]
            
            log(message=f"Chatlog 上下文增强：{chat_name} 合并后历史消息数 {len(merged_history)}")
            
            return merged_history
        
        except Exception as e:
            log(level="WARNING", message=f"Chatlog 上下文增强失败 [{chat_name}]: {e}")
            return base_history or []

    def _convert_chatlog_msg(self, msg_dict):
        """
        将 Chatlog 返回的消息字典转换为与 wxautox4 兼容的轻量消息对象。
        
        :param msg_dict: Chatlog 返回的消息字典
        :return: types.SimpleNamespace，包含 type、attr、sender、content、id 字段
        """
        msg = types.SimpleNamespace()
        
        msg_type = msg_dict.get('type', 0)
        if msg_type == 1:
            msg.type = 'text'
        elif msg_type == 3:
            msg.type = 'image'
        else:
            msg.type = 'unknown'
        
        if msg_dict.get('isSelf', False):
            msg.attr = 'self'
        elif msg_dict.get('isChatRoom', False):
            msg.attr = 'group'
        else:
            msg.attr = 'friend'
        
        msg.sender = msg_dict.get('senderName', '') or msg_dict.get('sender', '')
        msg.content = msg_dict.get('content', '')
        
        if msg.type == 'image' and msg_dict.get('contents'):
            msg.content = msg_dict['contents'].get('md5', '')
        
        msg.id = msg_dict.get('seq', 0)
        msg.seq = msg_dict.get('seq', 0)
        msg.time = msg_dict.get('time', '')
        
        return msg

    def chatlog_process_message(self, chat_name, msg_dict):
        """
        Chatlog 模式下直接处理消息并发送回复，无需获取子窗口对象。
        
        :param chat_name: 会话名称（备注名）
        :param msg_dict: Chatlog API 返回的消息字典
        :return: 发送结果
        """
        result = True
        msg = self._convert_chatlog_msg(msg_dict)
        log(message=f"chatlog_process_message 处理 {chat_name} 消息：{msg.content}")
        
        is_monitored = (
            (self.config.AllListen_switch and chat_name not in self.config.listen_list)
            or (not self.config.AllListen_switch and chat_name in self.config.listen_list)
            or (chat_name in self.config.group and self.config.group_switch)
            or (chat_name == self.config.cmd)
        )
        if not is_monitored:
            return True

        if self.message_store:
            msg_time = msg_dict.get('time', '') if isinstance(msg_dict, dict) else ''
            self.message_store.save_message(
                chat_name=chat_name,
                sender=msg.sender,
                content=msg.content,
                msg_type=msg.type,
                msg_attr=msg.attr,
                seq=msg.id,
                message_time=msg_time,
            )
        
        if chat_name in self.config.group:
            if not self.config.group_switch:
                return True
            
            if self.config.group_keyword_switch:
                _kw_at_pass = (not self.config.group_keyword_at_only) or (self.config.AtMe in msg.content)
                if _kw_at_pass:
                    for keyword in self.config.keyword_dict:
                        if keyword in msg.content:
                            log(message=f"群组 {chat_name} 关键字消息：" + msg.content)
                            try:
                                if self.wx_lock:
                                    self.wx_lock.acquire(holder=f"chatlog_group_keyword_{chat_name}")
                                self.config.human_delay()
                                result = self.bot.wx.SendMsg(msg=self.config.keyword_dict[keyword], who=chat_name)
                                self.bot._incr_replied()
                                time.sleep(1)
                            finally:
                                if self.wx_lock:
                                    self.wx_lock.release(holder=f"chatlog_group_keyword_{chat_name}")
                            return result
            
            if (self.config.AtMe in msg.content and self.config.group_reply_at) or not self.config.group_reply_at:
                if self.config.group_listen_only:
                    log(message=f"群组 {chat_name} 已启用只监听不AI回复，跳过 AI 调用")
                    return result

                # 群组 AI 生成 + 发送 → AIWorker，主线程不触碰 AI 网络调用
                self.bot.enqueue_ai(
                    lambda: self._chatlog_group_ai_and_send(chat_name, msg),
                    context=f"Chatlog_group:{chat_name}",
                )
                return True

            return result
        
        if chat_name == self.config.cmd:
            chat_proxy = types.SimpleNamespace()
            chat_proxy.who = chat_name
            chat_proxy.SendMsg = lambda m: self.bot.wx.SendMsg(msg=m, who=chat_name)
            chat_proxy.chat_type = 'chat'
            try:
                if self.wx_lock:
                    self.wx_lock.acquire(holder=f"chatlog_cmd_{chat_name}")
                result = self.bot.process_command(chat_proxy, msg)
            finally:
                if self.wx_lock:
                    self.wx_lock.release(holder=f"chatlog_cmd_{chat_name}")
            return result
        
        if (not self.config.AllListen_switch and
                chat_name not in self.config.listen_list and
                chat_name not in self.config.group and
                chat_name != self.config.cmd):
            return result
        if (self.config.AllListen_switch and chat_name in self.config.listen_list):
            return result
        
        result = self.bot._chatlog_send_ai(chat_name, msg)
        return result

    def _chatlog_group_ai_and_send(self, chat_name, msg):
        """
        在 AIWorker 线程内执行群组 AI 生成 + 发送。
        AI 生成与 wx UI 发送都不在监听主线程内执行。
        """
        content_without_at = re.sub(self.config.AtMe, "", msg.content).strip()
        log(message=f"群组 {chat_name} 消息：" + content_without_at)
        content_with_sender = f"{msg.sender}: {content_without_at}"

        reply = None
        try:
            history = []
            if self.config.memory_switch and self.bot.memory_manager:
                history = self.bot.memory_manager.get_messages(chat_name, self.config.memory_context_count)
            history = self._enrich_context_with_chatlog(chat_name, history)

            _base_group_prompt = self.bot._get_group_prompt(chat_name)
            if self.config.group_split_reply_switch:
                _effective_group_prompt = self.bot._build_split_prompt(
                    _base_group_prompt,
                    self.config.group_split_max_chars,
                    self.config.group_split_max_count
                )
            else:
                _effective_group_prompt = _base_group_prompt

            if self.config.group_image_recognition_switch:
                if msg.type == 'image':
                    rec_api = self.bot._init_api_by_index(self.config.group_image_recognition_api)
                    reply = rec_api.chat(
                        f"{msg.sender}: [这是 {msg.sender} 单独发送的一条图片消息，请根据上下文语境分析这张图片和发送者发送的意图进行回复]",
                        prompt=_effective_group_prompt,
                        history=history,
                        image_path=msg.content,
                        user_key=chat_name
                    )
                elif '+引用的图片:' in content_without_at:
                    text_part, img_path = content_without_at.split('+引用的图片:', 1)
                    rec_api = self.bot._init_api_by_index(self.config.group_image_recognition_api)
                    reply = rec_api.chat(
                        f"{msg.sender}: {text_part.strip()}" if text_part.strip() else f"{msg.sender}: [这是 {msg.sender} 单独发送的一条图片消息，请根据上下文语境分析这张图片和发送者发送的意图进行回复]",
                        prompt=_effective_group_prompt,
                        history=history,
                        image_path=img_path.strip(),
                        user_key=chat_name
                    )
                else:
                    group_api = self.bot._get_group_api(chat_name)
                    reply = group_api.chat(content_with_sender, prompt=_effective_group_prompt, history=history, user_key=chat_name)
            else:
                group_api = self.bot._get_group_api(chat_name)
                reply = group_api.chat(content_with_sender, prompt=_effective_group_prompt, history=history, user_key=chat_name)
        except Exception as e:
            log(level="ERROR", message=str(e) + "\n群组中调用AI回复错误！！")
            return

        reply = self.bot._clean_reply_for_send(reply)
        if not reply:
            return

        if self.config.group_split_reply_switch:
            parts = self.bot._parse_split_reply(reply, self.config.group_split_max_count)
        else:
            parts = [reply]

        try:
            if self.wx_lock:
                self.wx_lock.acquire(holder=f"chatlog_group_send_{chat_name}")

            for i, part in enumerate(parts):
                log(message=f"{chat_name} 回复第{i}次：{part}")
                self.config.human_delay()
                if i == 0 and self.config.group_reply_at_msg:
                    self.bot.wx.SendMsg(msg=part, who=chat_name, at=msg.sender)
                else:
                    self.bot.wx.SendMsg(msg=part, who=chat_name)
        finally:
            if self.wx_lock:
                self.wx_lock.release(holder=f"chatlog_group_send_{chat_name}")

        self.bot._incr_replied()

    def chatlog_listen_loop(self):
        """
        Chatlog 轮询监听模式主函数。
        
        通过 Chatlog API 轮询获取新消息并触发自动回复，作为 wxautox4 回调监听的替代方案。
        """
        if not self.bot.chatlog_client:
            return
        
        try:
            session_result = self.bot.chatlog_client.get_session(
                has_unread=1,
                ignore_usernames="brandsessionholder,gh_edac0ec6a0ba,newsapp,gh_b6f1d17d2ffc,gh_315e955abdf5,brandservicesessionholder,notifymessage,gh_dbc6691e1b64"
            )
            sessions = session_result.get('items', [])
            
            if not sessions:
                return
            
            for session in sessions:
                session_wxid = session.get('nickName', '') or session.get('userName', '')
                session_nTime = session.get('nTime', '')

                contact = self.bot.chatlog_contact_map.get(session_wxid)
                if not contact:
                    log(message=f"Chatlog 监听 {session_wxid} 不在用户列表里")
                    continue
                
                wxid = contact.get('userName', '')
                nickname = contact.get('nickName', '')
                alias = contact.get('alias', '')
                chat_name = contact.get('remark', '')

                UnreadCount = session.get('UnreadCount', 0)
                log(message=f"chatlog_listen_loop 监听 {chat_name} 有 {UnreadCount} 未读消息")

                reply_delay = self.config.chatlog_reply_delay
                if session_nTime and reply_delay > 0:
                    try:
                        msg_time = datetime.fromisoformat(session_nTime.replace('Z', '+00:00'))
                        now = datetime.now(msg_time.tzinfo) if msg_time.tzinfo else datetime.now()
                        time_diff = (now - msg_time).total_seconds()
                        if time_diff < reply_delay:
                            log(message=f"Chatlog 会话 [{session_wxid}] 最后消息时间 {session_nTime}，距当前仅 {time_diff:.1f} 秒，未达到回复延迟 {reply_delay} 秒，跳过")
                            continue
                    except Exception as e:
                        log(level="WARNING", message=f"Chatlog 解析会话时间失败 [{session_wxid}]: {e}")
                
                if not chat_name:
                    continue
                
                is_monitored = (
                    (self.config.AllListen_switch and chat_name not in self.config.listen_list)
                    or (not self.config.AllListen_switch and chat_name in self.config.listen_list)
                    or (chat_name in self.config.group and self.config.group_switch)
                    or (chat_name == self.config.cmd)
                )
                if not is_monitored:
                    continue
                
                try:
                    # 调用 Chatlog API 获取该会话最近30天的消息（最多500条作为安全上限）
                    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                    end_date = datetime.now().strftime('%Y-%m-%d')
                    msgs = self.bot.chatlog_client.get_chatlog(talker=chat_name, time=f"{start_date}~{end_date}", limit=500)
                    
                    # 没有获取到消息则跳过
                    if not msgs:
                        continue
                    
                    # 自动刷新：把本次拉取的全部消息去重写入存储层（含 self 与已读历史）
                    # 受 chatlog_message_auto_refresh 开关控制，失败不阻断主流程
                    if getattr(self.config, 'chatlog_message_auto_refresh', True) and self.message_store:
                        try:
                            total_fetched, new_saved = self.message_store.refresh_messages_from_chatlog(
                                chat_name, prefetched_msgs=msgs
                            )
                            log(message=f"自动刷新会话 [{chat_name}] 消息：拉取 {total_fetched} 条，新增 {new_saved} 条")
                        except Exception as e:
                            log(level="ERROR", message=f"自动刷新会话 [{chat_name}] 消息失败: {e}")
                    
                    # 获取该会话上次处理到的最大 seq，用于过滤新消息
                    last_seq = self.bot.chatlog_last_seq.get(chat_name, 0)
                    
                    # 按 seq 升序排序，确保消息顺序正确
                    msgs.sort(key=lambda m: m.get('seq', 0))
                    
                    # 过滤出 isSelf=False 且 seq > last_seq 的消息（他人发送的新消息），取最新的 UnreadCount 项
                    new_messages = [
                        m for m in msgs
                        if not m.get('isSelf', False) and m.get('seq', 0) > last_seq
                    ][-UnreadCount:]
                    
                    # 没有新消息则跳过
                    if not new_messages:
                        continue
                    
                    if not new_messages:
                        continue
                    
                    for msg in new_messages:
                        
                        try:
                            self.chatlog_process_message(chat_name, msg)
                        except Exception as e:
                            log(level="ERROR", message=f"处理 Chatlog 消息失败 [{chat_name}]: {e}")
                    
                    self.bot.chatlog_last_seq[chat_name] = max(msg.get('seq', 0) for msg in new_messages)
                
                except Exception as e:
                    log(level="ERROR", message=f"获取 Chatlog 消息失败 [{chat_name}]: {e}")
        
        except Exception as e:
            log(level="ERROR", message=f"Chatlog 监听循环异常: {e}")
