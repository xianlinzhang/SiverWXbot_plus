from datetime import datetime, timedelta
import types
import traceback
import re
import time

from chatlog_client import ChatlogClient, ChatlogError
from logger import log


class ChatlogManager:
    """
    Chatlog 模块管理
    负责通过 Chatlog API 轮询监听消息、处理消息、增强上下文等功能。
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.message_store = bot.message_store if hasattr(bot, 'message_store') else None
        self.wx_lock = bot.wx_lock if hasattr(bot, 'wx_lock') else None

    def _init_chatlog_client(self):
        """初始化 Chatlog 客户端（若配置开启）"""
        if not self.config.chatlog_listen_switch:
            return
        
        try:
            self.bot.chatlog_client = ChatlogClient(
                base_url=self.config.chatlog_url,
                timeout=self.config.chatlog_request_timeout
            )
            self.bot.chatlog_contact_map = {}
            self.bot.chatlog_last_seq = {}
            self.refresh_chatlog_contacts()
            log(message="Chatlog 客户端初始化成功")
        except ImportError:
            log(level="ERROR", message="未安装 chatlog_client 模块，请安装后再开启 Chatlog 监听模式")
            self.config.chatlog_listen_switch = False
        except Exception as e:
            log(level="ERROR", message=f"Chatlog 客户端初始化失败: {e}")
            self.config.chatlog_listen_switch = False

    def refresh_chatlog_contacts(self):
        """
        刷新 Chatlog 联系人缓存。

        调用 Chatlog API 获取所有联系人，构建 userName、nickName、alias、remark 的双向映射，
        用于在关键词匹配失败时扩展匹配范围。

        映射逻辑：
        - 将每个联系人的 wxid、nickName、alias、remark 四种标识互相映射
        - 例如：wxid_xxx -> 昵称, 昵称 -> wxid_xxx, 备注 -> 昵称 等
        - 这样当用户使用昵称搜索但系统存储的是 wxid 时，也能通过映射找到对应联系人
        """
        # 检查 Chatlog 客户端是否已初始化，未初始化则直接返回
        if not self.bot.chatlog_client:
            return

        try:
            # 调用 Chatlog API 搜索所有联系人
            contacts = self.bot.chatlog_client.search_contact(is_friend=1)

            # 没有获取到联系人数据则直接返回
            if not contacts:
                return

            # 初始化新的联系人映射字典
            new_map = {}

            contacts_items = contacts.get('items', [])

            # 遍历所有联系人项
            for contact in contacts_items:
                # 提取联系人的四种标识信息
                wxid = contact.get('userName', '')  # 微信内部 ID
                nickname = contact.get('nickName', '')  # 昵称
                alias = contact.get('alias', '')  # 微信号（自定义 ID）
                remark = contact.get('remark', '')  # 备注名

                # 将四种标识放入列表，便于后续构建双向映射
                # identifiers = [wxid, nickname, alias, remark]

                new_map[wxid] = contact

                if not remark:
                    new_map[remark] = contact

            # 更新联系人映射缓存，替换旧数据
            self.bot.chatlog_contact_map = new_map

            # 记录日志，显示更新的记录数量
            log(message=f"Chatlog 联系人缓存已更新，共 {len(contacts_items)} 条记录")

        except ChatlogError as e:
            # Chatlog API 调用失败，记录错误日志
            log(level="ERROR", message=f"刷新 Chatlog 联系人失败: {e}")
        except Exception as e:
            # 处理过程中发生其他异常，记录错误日志
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
                                self.bot.msg_replied_count += 1
                                time.sleep(1)
                            finally:
                                if self.wx_lock:
                                    self.wx_lock.release(holder=f"chatlog_group_keyword_{chat_name}")
                            return result
            
            if (self.config.AtMe in msg.content and self.config.group_reply_at) or not self.config.group_reply_at:
                if self.config.group_listen_only:
                    log(message=f"群组 {chat_name} 已启用只监听不AI回复，跳过 AI 调用")
                    return result
                
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
                                image_path=msg.content
                            )
                        elif '+引用的图片:' in content_without_at:
                            text_part, img_path = content_without_at.split('+引用的图片:', 1)
                            rec_api = self.bot._init_api_by_index(self.config.group_image_recognition_api)
                            reply = rec_api.chat(
                                f"{msg.sender}: {text_part.strip()}" if text_part.strip() else f"{msg.sender}: [这是 {msg.sender} 单独发送的一条图片消息，请根据上下文语境分析这张图片和发送者发送的意图进行回复]",
                                prompt=_effective_group_prompt,
                                history=history,
                                image_path=img_path.strip()
                            )
                        else:
                            group_api = self.bot._get_group_api(chat_name)
                            reply = group_api.chat(content_with_sender, prompt=_effective_group_prompt, history=history)
                    else:
                        group_api = self.bot._get_group_api(chat_name)
                        reply = group_api.chat(content_with_sender, prompt=_effective_group_prompt, history=history)
                except Exception as e:
                    print(traceback.format_exc())
                    log(level="ERROR", message=str(e) + "\n群组中调用AI回复错误！！")
                    reply = self.config.api_error_reply
                
                if reply == "API返回错误，请稍后再试":
                    reply = self.config.api_error_reply
                else:
                    reply = self.bot._clean_reply_for_send(reply)
                
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
                            result = self.bot.wx.SendMsg(msg=part, who=chat_name, at=msg.sender)
                        else:
                            result = self.bot.wx.SendMsg(msg=part, who=chat_name)
                finally:
                    if self.wx_lock:
                        self.wx_lock.release(holder=f"chatlog_group_send_{chat_name}")
                
                self.bot.msg_replied_count += 1
                return result
            
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
                    
                    # 获取该会话上次处理到的最大 seq，用于过滤新消息
                    last_seq = self.bot.chatlog_last_seq.get(chat_name, 0)
                    
                    # 按 seq 升序排序，确保消息顺序正确
                    msgs.sort(key=lambda m: m.get('seq', 0))
                    
                    # 过滤出 isSelf=False 且 seq > last_seq 的消息（他人发送的新消息），取最新的 UnreadCount 项
                    new_messages = [m for m in msgs if not m.get('isSelf', False) and m.get('seq', 0) > last_seq][-UnreadCount:]
                    
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
