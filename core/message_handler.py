import re
import time
import traceback
from datetime import datetime
from typing import Optional

from core.message_store import MessageStore
from logger import log
from core.utils import SPLIT_SEPARATOR, SPLIT_PROMPT_TEMPLATE, clean_ai_reply_text


class AIReplyError(Exception):
    """AI 接口调用失败异常。由任务队列捕获后进入重试 → 死信队列。"""


class MessageHandler:
    """
    消息处理模块
    负责处理微信消息的接收、分发、AI 回复等核心逻辑。
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.message_store: Optional[MessageStore] = bot.message_store if hasattr(bot, 'message_store') else None

    def _get_chat_api(self, user_name):
        """获取私聊用户对应的 AI 接口实例（白名单模式查 chat_api_map，否则用默认接口）"""
        if not self.config.AllListen_switch:
            idx = self.config.chat_api_map.get(user_name)
            if idx is not None:
                if idx not in self.bot.api_cache:
                    self.bot.api_cache[idx] = self.bot._init_api_by_index(idx)
                return self.bot.api_cache[idx]
        return self.bot.api

    def _get_group_api(self, group_name):
        """获取群组对应的 AI 接口实例"""
        idx = self.config.group_api_map.get(group_name)
        if idx is not None:
            if idx not in self.bot.api_cache:
                self.bot.api_cache[idx] = self.bot._init_api_by_index(idx)
            return self.bot.api_cache[idx]
        return self.bot.api

    def _get_chat_prompt(self, user_name):
        """获取私聊用户对应的 prompt 内容（白名单模式查 chat_prompt_map，全局模式用 default_prompt）"""
        if not self.config.AllListen_switch:
            name = self.config.chat_prompt_map.get(user_name) or self.config.default_prompt
        else:
            name = self.config.default_prompt
        return self.config.get_prompt_content(name)

    def _get_group_prompt(self, group_name):
        """获取群组对应的 prompt 内容（查 group_prompt_map，未配置则用 default_prompt）"""
        name = self.config.group_prompt_map.get(group_name) or self.config.default_prompt
        return self.config.get_prompt_content(name)

    def _build_split_prompt(self, base_prompt, max_chars, max_count):
        """将拆分格式要求注入到 prompt 前面，返回组合后的 prompt"""
        return SPLIT_PROMPT_TEMPLATE.format(
            max_chars=max_chars,
            max_count=max_count,
            base_prompt=base_prompt,
        )

    def _parse_split_reply(self, reply, max_count):
        """按 ||SPLIT|| 分隔符解析回复，过滤空白，截断到 max_count 条"""
        parts = [p.strip() for p in reply.split(SPLIT_SEPARATOR) if p.strip()]
        return parts[:max_count] if parts else [reply]

    def _clean_reply_for_send(self, reply):
        """按配置清洗即将发送给用户的 AI 回复。清洗后为空返回空字符串（不兜底固定回复）。"""
        if not self.config.clean_ai_reply_switch:
            return reply
        cleaned = clean_ai_reply_text(reply)
        if cleaned:
            return cleaned
        log(level="WARNING", message="AI 回复清洗后为空")
        return ""

    def _get_reply_count_key(self, chat, message=None):
        """获取回复计数器 key；当前 wxautox4 可用稳定字段有限，先集中使用 chat.who。"""
        return str(getattr(chat, 'who', '') or '').strip()

    def _get_chat_max_round(self, user_name):
        """获取私聊用户的回复轮数上限；白名单模式优先用户专属上限。"""
        if not self.config.AllListen_switch:
            custom_value = self.config.chat_max_round_map.get(user_name)
            if custom_value:
                return custom_value
        return self.config.chat_max_round_default

    def _check_chat_max_round_limit(self, chat, user_key):
        """检查并处理私聊回复轮数超限；返回 (是否已处理, 发送结果)。"""
        if not self.config.chat_max_round_switch or not user_key:
            return False, True
        self.bot.reply_count_store.maybe_reset(self.config.chat_max_round_reset_days)
        user_data = self.bot.reply_count_store.get_user(user_key)
        max_round = self._get_chat_max_round(user_key)
        if user_data.get("ai_count", 0) < max_round:
            return False, True

        if self.config.chat_max_round_reply_once and user_data.get("limit_notified"):
            return True, True
        if not self.config.chat_max_round_reply:
            return True, True

        result = chat.SendMsg(self.config.chat_max_round_reply)
        if self.bot.reply_count_store.was_send_success(result):
            self.bot._incr_replied()
            if self.config.chat_max_round_reply_once:
                self.bot.reply_count_store.mark_limit_notified(user_key)
        return True, result

    def _is_custom_forward_source(self, chat_who):
        """判断某个会话是否是任意自定义转发规则的监听来源"""
        for rule in self.config.custom_forward_list:
            if chat_who in rule.get('sources', []):
                return True
        return False

    def _handle_custom_forward(self, chat, message):
        """
        自定义规则转发执行器。
        遍历所有规则，找到 chat.who 匹配的来源，按规则类型判断是否转发，
        符合条件则逐目标转发（每次转发前延时 1 秒）。

        转发类型：
          keyword — 消息内容包含任意关键词时转发
          sender  — 消息发送人匹配时转发
          all     — 无差别转发，所有消息均转发
        """
        if not self.config.custom_forward_switch:
            return
        for rule in self.config.custom_forward_list:
            if not rule.get('all_sources', False) and chat.who not in rule.get('sources', []):
                continue
            rule_type = rule.get('type', 'all')
            should_forward = False
            if rule_type == 'all':
                should_forward = True
            elif rule_type == 'keyword':
                keywords = rule.get('keywords', [])
                should_forward = any(kw and kw in message.content for kw in keywords)
            elif rule_type == 'sender':
                senders = rule.get('senders', [])
                should_forward = bool(senders) and message.sender in senders
            if should_forward:
                forward_with_source = rule.get('forward_with_source', False)
                src_msg = f"来源窗口：{chat.who}，发送人：{message.sender}" if forward_with_source else None
                for target in rule.get('targets', []):
                    if target:
                        time.sleep(1)
                        if src_msg:
                            if message.type in ['image', 'video', 'file', 'location', 'link', 'emotion', 'merge', 'personal_card', 'note', 'miniapp']:
                                message.forward(target, message=src_msg)
                            else:
                                self.bot.wx.SendMsg(who=target, msg=message.content+"\n"+src_msg)
                        else:
                            if message.type in ['image', 'video', 'file', 'location', 'link', 'emotion', 'merge', 'personal_card', 'note', 'miniapp']:
                                message.forward(target)
                            else:
                                self.bot.wx.SendMsg(who=target, msg=message.content)
                        log(message=f"[自定义转发] {chat.who} → {target}（规则类型：{rule_type}，附带来源：{forward_with_source}）")

    def _chatlog_send_ai(self, chat_name, message, message_record=None):
        """
        Chatlog 模式下对私聊消息调用 AI 接口并发送回复。
        集成消息存储，发送操作通过任务队列异步执行。

        :param chat_name:      会话名称（备注名）
        :param message:        消息对象
        :param message_record: 已保存的消息记录（可选，避免重复保存）
        :return:               任务提交结果，True 表示成功提交，False 表示跳过
        """
        api_error_reply = False
        msg_id = None

        if self.message_store and not message_record:
            message_time = getattr(message, 'time', '')
            if message_time and hasattr(self.message_store, '_normalize_message_time'):
                message_time = self.message_store._normalize_message_time(message_time)
            message_record = self.message_store.save_message(
                chat_name=chat_name,
                sender=message.sender,
                content=message.content,
                msg_type=message.type,
                msg_attr=message.attr,
                seq=message.seq,
                message_time=message_time,
            )
            msg_id = message_record.id

        if self.config.chat_reply_confirm_switch and message_record:
            # 关键字命中 → 预生成关键字回复，放入待确认队列，不直接操作 UI
            _kw = self._match_keyword(message.content) if self.config.chat_keyword_switch else None
            if _kw:
                self.message_store.add_pending_confirm(
                    message_record,
                    pending_reply=_kw,
                    pending_source='keyword',
                )
                log(message=f"Chatlog 私聊 {chat_name} 关键字命中，回复已预生成，进入待确认队列")
                return True

            # 只监听不 AI 回复：直接标记完成，不进待确认
            if self.config.chat_listen_only:
                log(message=f"Chatlog 私聊 {chat_name} 已启用只监听不AI回复，跳过 AI 调用")
                if message_record.id:
                    self.message_store.set_message_status(chat_name, message_record.id, "processed")
                return True

            # 先入待确认队列，AI 预生成异步回填（任务队列，失败重试 → 死信）
            self.message_store.add_pending_confirm(message_record)
            log(message=f"Chatlog 私聊 {chat_name} 消息已加入待确认队列，AI 回复预生成中")
            return self.submit_ai_pregenerate_task(
                chat_name=chat_name,
                message=message,
                msg_id=message_record.id,
            )

        # 关键字应答：无需调 AI，派发线程（主线程）直接处理
        if self.config.chat_keyword_switch:
            _kw = self._match_keyword(message.content)
            if _kw:
                log(message=f"私聊 {chat_name} 关键字消息：" + message.content)
                self._send_reply_segments(
                    chat_name=chat_name,
                    reply=_kw,
                    msg_id=msg_id,
                    api_error_reply=False,
                    api_error_should_mark=False,
                    user_key=chat_name,
                )
                return True

        # 只监听不 AI 回复：派发线程直接标记完成
        if self.config.chat_listen_only:
            log(message=f"私聊 {chat_name} 已启用只监听不AI回复，跳过 AI 调用")
            if self.message_store and msg_id:
                self.message_store.set_message_status(chat_name, msg_id, "processed")
            return True

        # 真正需要调 AI 的生成部分 → 任务队列 ai_reply 任务（失败重试 → 死信）
        return self.submit_ai_reply_task(
            chat_name=chat_name,
            message=message,
            msg_id=msg_id,
            user_key=chat_name,
        )

    def _match_keyword(self, content):
        """在 keyword_dict 中匹配关键词，命中返回回复内容，否则返回 None"""
        if not self.config.chat_keyword_switch:
            return None
        for keyword in self.config.keyword_dict:
            if keyword in content:
                return self.config.keyword_dict[keyword]
        return None

    def _generate_ai_reply(self, chat_name, message):
        """
        生成 AI 回复（仅生成，不发送）。
        在 AIWorker 线程内执行。

        :param chat_name: 会话名称
        :param message: 消息对象
        :return: reply 字符串
        :raises AIReplyError: AI 接口调用失败（由任务队列重试 → 死信）
        """
        reply = None
        try:
            history = []
            if self.config.memory_switch and self.bot.memory_manager:
                history = self.bot.memory_manager.get_messages(
                    chat_name, self.config.memory_context_count
                )
            history = self.bot._enrich_context_with_chatlog(chat_name, history)

            _base_prompt = self._get_chat_prompt(chat_name)
            if self.config.chat_split_reply_switch:
                _effective_prompt = self._build_split_prompt(
                    _base_prompt,
                    self.config.chat_split_max_chars,
                    self.config.chat_split_max_count
                )
            else:
                _effective_prompt = _base_prompt

            if self.config.chat_image_recognition_switch:
                if message.type == 'image':
                    rec_api = self.bot._init_api_by_index(self.config.chat_image_recognition_api)
                    reply = rec_api.chat(
                        "[这是单独发送的一条图片消息，请根据上下文语境分析这张图片和发送者发送的意图进行回复]",
                        prompt=_effective_prompt,
                        history=history,
                        image_path=message.content,
                        user_key=chat_name
                    )
                elif '+引用的图片:' in message.content:
                    text_part, img_path = message.content.split('+引用的图片:', 1)
                    rec_api = self.bot._init_api_by_index(self.config.chat_image_recognition_api)
                    reply = rec_api.chat(
                        text_part.strip() or "[这是单独发送的一条图片消息，请根据上下文语境分析这张图片和发送者发送的意图进行回复]",
                        prompt=_effective_prompt,
                        history=history,
                        image_path=img_path.strip(),
                        user_key=chat_name
                    )
                else:
                    reply = self._get_chat_api(chat_name).chat(message.content, prompt=_effective_prompt, history=history, user_key=chat_name)
                    log(level="DEBUG", message=f"AI原始返回 [{chat_name}]: {reply[:300]}")
            else:
                reply = self._get_chat_api(chat_name).chat(message.content, prompt=_effective_prompt, history=history, user_key=chat_name)
                log(level="DEBUG", message=f"AI原始返回 [{chat_name}]: {reply[:300]}")
        except Exception as e:
            log(level="ERROR", message=str(e) + "\nAPI返回错误，请稍后再试")
            raise AIReplyError(f"AI 接口调用失败 [{chat_name}]: {e}") from e

        if not reply or reply == "API返回错误，请稍后再试":
            raise AIReplyError(f"AI 接口返回错误，无有效回复 [{chat_name}]")

        reply = self._clean_reply_for_send(reply)
        if not reply:
            raise AIReplyError(f"AI 回复清洗后为空 [{chat_name}]")

        return reply

    def _ai_generate_and_send(self, chat_name, message, msg_id, is_group=False, user_key=None, api_error_once=False, max_round_switch=False):
        """
        在任务队列 worker 内执行 AI 生成 + 分段发送（私聊路径）。
        AI 接口失败时抛 AIReplyError → 任务重试 → 死信队列，不再发固定回复。

        :raises AIReplyError: AI 接口调用失败
        """
        reply = self._generate_ai_reply(chat_name, message)
        self._send_reply_segments(
            chat_name=chat_name,
            reply=reply,
            msg_id=msg_id,
            api_error_reply=False,
            api_error_should_mark=False,
            user_key=user_key or chat_name,
            api_error_once=api_error_once,
            max_round_switch=max_round_switch,
        )

    @staticmethod
    def _message_to_params(chat_name, message, msg_id, user_key=None, api_error_once=False, max_round_switch=False):
        """将消息对象序列化为可提交任务的参数字典"""
        return {
            'chat_name': chat_name,
            'msg_id': msg_id,
            'user_key': user_key or chat_name,
            'api_error_once': bool(api_error_once),
            'max_round_switch': bool(max_round_switch),
            'message': {
                'content': getattr(message, 'content', ''),
                'type': getattr(message, 'type', 'text'),
                'attr': getattr(message, 'attr', 'friend'),
                'sender': getattr(message, 'sender', ''),
                'seq': getattr(message, 'seq', 0),
                'time': getattr(message, 'time', ''),
            },
        }

    def submit_ai_reply_task(self, chat_name, message, msg_id, user_key=None, api_error_once=False, max_round_switch=False) -> bool:
        """提交 AI 回复任务到任务队列（失败会重试 → 死信）。"""
        params = self._message_to_params(
            chat_name, message, msg_id, user_key,
            api_error_once=api_error_once, max_round_switch=max_round_switch,
        )
        self.bot.task_queue.submit(task_type='ai_reply', params=params)
        return True

    def ai_reply_task(self, params):
        """
        任务队列 ai_reply 任务的执行体（在 task_queue worker 线程内执行）。
        AI 接口失败时抛 AIReplyError → 任务重试 → 死信队列。
        """
        from types import SimpleNamespace
        chat_name = params.get('chat_name')
        msg_id = params.get('msg_id')
        message = SimpleNamespace(**params.get('message', {}))
        reply = self._generate_ai_reply(chat_name, message)
        self._send_reply_segments(
            chat_name=chat_name,
            reply=reply,
            msg_id=msg_id,
            api_error_reply=False,
            api_error_should_mark=False,
            user_key=params.get('user_key') or chat_name,
            api_error_once=params.get('api_error_once', False),
            max_round_switch=params.get('max_round_switch', False),
        )
        return True

    def submit_ai_pregenerate_task(self, chat_name, message, msg_id) -> bool:
        """提交 AI 预生成任务到任务队列（失败重试 → 死信）。"""
        params = self._message_to_params(
            chat_name, message, msg_id, user_key=chat_name,
        )
        self.bot.task_queue.submit(task_type='ai_pregenerate', params=params)
        return True

    def ai_pregenerate_task(self, params):
        """
        任务队列 ai_pregenerate 任务的执行体（在 task_queue worker 线程内执行）。
        只生成回复回写待确认记录，不发送；AI 失败抛 AIReplyError → 重试 → 死信队列。
        """
        from types import SimpleNamespace
        chat_name = params.get('chat_name')
        msg_id = params.get('msg_id')
        message = SimpleNamespace(**params.get('message', {}))
        try:
            reply = self._generate_ai_reply(chat_name, message)
            source = 'ai'
        except AIReplyError as e:
            log(level="ERROR", message=f"待确认消息 {msg_id} AI 预生成失败：{e}")
            raise
        if not self.message_store:
            log(level="WARNING", message=f"待确认预生成失败：message_store 不可用 [{chat_name}]")
            return False
        self.message_store.update_pending_confirm_reply(msg_id, reply, source)
        return True

    def confirm_and_send(self, chat_name, message_id, custom_reply=None):
        """
        确认待确认消息并发送回复。

        发送内容优先级：
        1. custom_reply（面板/命令手动修改后的内容，非空时优先）
        2. 待确认记录中已预生成的回复（keyword/ai 来源）
        3. 均无（如 AI 仍排队）→ 即时补生成

        :param chat_name:  会话名称
        :param message_id: 消息 ID
        :param custom_reply: 手动修改后的回复内容（可选）
        :return: MessageRecord 对象或 None
        """
        from types import SimpleNamespace
        if not self.message_store:
            return None
        record = self.message_store.get_message(chat_name, message_id)
        if not record:
            return None
        final_reply = (custom_reply or "").strip() if custom_reply else ""
        if final_reply and record.pending_reply != final_reply:
            self.message_store.update_pending_confirm_reply(
                message_id, final_reply, record.pending_source or 'manual'
            )
        record = self.message_store.confirm_message(chat_name, message_id)
        if not record:
            return None
        if final_reply:
            self._send_reply_segments(
                chat_name=chat_name,
                reply=final_reply,
                msg_id=record.id,
                api_error_reply=False,
                api_error_should_mark=False,
                user_key=chat_name,
                api_error_once=self.config.api_error_reply_once,
                max_round_switch=self.config.chat_max_round_switch,
            )
            log(message=f"已确认消息 {message_id}，发送手动修改后的回复")
            return record
        if record.pending_reply:
            self._send_reply_segments(
                chat_name=chat_name,
                reply=record.pending_reply,
                msg_id=record.id,
                api_error_reply=False,
                api_error_should_mark=False,
                user_key=chat_name,
                api_error_once=self.config.api_error_reply_once,
                max_round_switch=self.config.chat_max_round_switch,
            )
            log(message=f"已确认消息 {message_id}，发送预生成回复")
            return record
        proxy = SimpleNamespace(
            content=record.content,
            type=record.msg_type,
            sender=record.sender,
        )
        self.submit_ai_reply_task(
            chat_name=chat_name,
            message=proxy,
            msg_id=record.id,
            user_key=chat_name,
            api_error_once=self.config.api_error_reply_once,
            max_round_switch=self.config.chat_max_round_switch,
        )
        log(message=f"已确认消息 {message_id}，AI 回复已进入任务队列")
        return record

    def reject_and_ignore(self, chat_name, message_id):
        """拒绝待确认消息（不回复）。"""
        if not self.message_store:
            return None
        record = self.message_store.reject_message(chat_name, message_id)
        if record:
            log(message=f"已拒绝消息 {message_id}，不回复")
        return record

    def _send_reply_segments(self, chat_name, reply, msg_id, api_error_reply, api_error_should_mark, user_key, api_error_once=False, max_round_switch=False):
        """清洗、拆分、分片经 task_queue 发送（可在 AIWorker 线程内执行），并按需回写存储。"""
        if self.config.chat_split_reply_switch:
            parts = self._parse_split_reply(reply, self.config.chat_split_max_count)
        else:
            parts = [reply]

        all_segments = []
        for part in parts:
            if len(part) >= 2000:
                all_segments.extend(self.config.split_long_text(part))
            else:
                all_segments.append(part)

        if not all_segments:
            if self.message_store and msg_id:
                self.message_store.set_message_status(chat_name, msg_id, "processed")
            return

        final_reply = reply
        final_msg_id = msg_id
        final_chat_name = chat_name
        final_user_key = user_key
        final_api_error_should_mark = api_error_should_mark

        def _send_msg_callback(success, result, params):
            if success and final_api_error_should_mark:
                self.bot.reply_count_store.mark_api_err_notified(final_user_key)

            if success and max_round_switch and final_user_key and not api_error_reply:
                self.bot.reply_count_store.increment_ai_count(final_user_key)

            if self.message_store and final_msg_id and success:
                self.message_store.bind_reply(
                    final_chat_name,
                    final_msg_id,
                    final_reply,
                    datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                )
            elif self.message_store and final_msg_id:
                self.message_store.set_message_status(final_chat_name, final_msg_id, "processed")

            self.bot._incr_replied()

        def _submit_segment(index):
            if index >= len(all_segments):
                _send_msg_callback(True, None, {})
                return

            segment = all_segments[index]
            params = {
                'who': chat_name,
                'msg': segment,
                'msg_id': msg_id,
                'user_key': user_key or chat_name,
                'api_error_reply': api_error_reply,
            }

            def _segment_callback(success, result, segment_params):
                if success:
                    _submit_segment(index + 1)
                else:
                    _send_msg_callback(False, result, segment_params)

            self.bot.task_queue.submit(
                task_type='send_msg',
                params=params,
                callback=_segment_callback,
            )

        _submit_segment(0)

    def _cb_group_ai_and_send(self, chat, message):
        """
        在 AIWorker 线程内执行（非 Chatlog 回调路径的）群组 AI 生成 + 发送。
        AI 网络调用与发送都不在 wxautox 回调线程内执行。
        """
        if self.config.group_listen_only:
            return
        content_without_at = re.sub(self.config.AtMe, "", message.content).strip()
        log(message=f"群组 {chat.who} 消息：" + content_without_at)
        content_with_sender = f"{message.sender}: {content_without_at}"
        reply = None
        try:
            history = []
            if self.config.memory_switch and self.bot.memory_manager:
                history = self.bot.memory_manager.get_messages(
                    chat.who, self.config.memory_context_count
                )
            history = self.bot._enrich_context_with_chatlog(chat.who, history)

            _base_group_prompt = self._get_group_prompt(chat.who)
            if self.config.group_split_reply_switch:
                _effective_group_prompt = self._build_split_prompt(
                    _base_group_prompt,
                    self.config.group_split_max_chars,
                    self.config.group_split_max_count
                )
            else:
                _effective_group_prompt = _base_group_prompt
            if self.config.group_image_recognition_switch:
                if message.type == 'image':
                    rec_api = self.bot._init_api_by_index(self.config.group_image_recognition_api)
                    reply = rec_api.chat(
                        f"{message.sender}: [这是 {message.sender} 单独发送的一条图片消息，请根据上下文语境分析这张图片和发送者发送的意图进行回复]",
                        prompt=_effective_group_prompt,
                        history=history,
                        image_path=message.content,
                        user_key=chat.who
                    )
                elif '+引用的图片:' in content_without_at:
                    text_part, img_path = content_without_at.split('+引用的图片:', 1)
                    rec_api = self.bot._init_api_by_index(self.config.group_image_recognition_api)
                    reply = rec_api.chat(
                        f"{message.sender}: {text_part.strip()}" if text_part.strip() else f"{message.sender}: [这是 {message.sender} 单独发送的一条图片消息，请根据上下文语境分析这张图片和发送者发送的意图进行回复]",
                        prompt=_effective_group_prompt,
                        history=history,
                        image_path=img_path.strip(),
                        user_key=chat.who
                    )
                else:
                    group_api = self._get_group_api(chat.who)
                    reply = group_api.chat(content_with_sender, prompt=_effective_group_prompt, history=history, user_key=chat.who)
            else:
                group_api = self._get_group_api(chat.who)
                reply = group_api.chat(content_with_sender, prompt=_effective_group_prompt, history=history, user_key=chat.who)
        except Exception as e:
            log(level="ERROR", message=str(e) + "\n群组中调用AI回复错误！！")
            return

        reply = self._clean_reply_for_send(reply)
        if not reply:
            return

        if self.config.group_split_reply_switch:
            parts = self._parse_split_reply(reply, self.config.group_split_max_count)
        else:
            parts = [reply]

        _at_msg = self.config.group_reply_at_msg
        _quote = self.config.group_reply_quote
        for i, part in enumerate(parts):
            self.config.human_delay()
            if i == 0 and _quote and _at_msg:
                message.quote(part, at=message.sender)
            elif i == 0 and _quote:
                message.quote(part)
            elif _at_msg:
                chat.SendMsg(msg=part, at=message.sender if i == 0 else None)
            else:
                chat.SendMsg(msg=part)

        self.bot._incr_replied()

    def _extract_message_time_from_control(self, msg):
        """
        从消息控件中提取时间信息
        
        :param msg: 消息对象
        :return: 时间字符串，如果无法提取则返回 None
        """
        if hasattr(msg, 'control') and msg.control:
            try:
                children = msg.control.GetChildren()
                for child in children:
                    if child.ClassName and 'Time' in child.ClassName:
                        time_text = child.Name
                        if time_text and len(time_text) > 3:
                            return time_text
                    if child.Name and (':' in child.Name or '分' in child.Name):
                        name = child.Name.strip()
                        if len(name) >= 4 and len(name) <= 16:
                            try:
                                import re
                                if re.match(r'^\d{1,2}:\d{2}$', name):
                                    now = datetime.now()
                                    return f"{now.year}/{now.month}/{now.day} {name}"
                                if re.match(r'^\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}$', name):
                                    return name
                            except Exception:
                                pass
            except Exception:
                pass
        return None

    def message_handle_callback(self, msg, chat):
        """
        wxautox 监听器的消息回调函数。
        每当监听到新消息时由 wxautox 自动调用。
        集成消息存储和微信界面操作锁。

        :param msg:  消息对象（含 type、attr、sender、content 等属性）
        :param chat: 聊天窗口子对象（含 who 等属性）
        """
        if self.config.chatlog_listen_switch:
            return

        try:
            message_time = self._extract_message_time_from_control(msg)
            if not message_time:
                message_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                
            text = (
                message_time + " "
                + f'类型：{msg.type} 属性：{msg.attr} 窗口：{chat.who}'
                + f' 发送人：{msg.sender} - 消息：{msg.content}'
            )
            log(message=text)

            if self.message_store:
                self.message_store.save_message(
                    chat_name=chat.who,
                    sender=msg.sender,
                    content=msg.content,
                    msg_type=msg.type,
                    msg_attr=msg.attr,
                    message_time=message_time,
                )

            if msg.attr == "friend":
                _is_group = chat.who in self.config.group
                if _is_group:
                    _img_enabled = self.config.group_image_recognition_switch
                elif not self.config.AllListen_switch and chat.who in self.config.listen_list:
                    _img_enabled = self.config.chat_image_recognition_switch
                elif (self.config.AllListen_switch and chat.who not in self.config.listen_list and chat.chat_type != 'group'):
                    _img_enabled = self.config.chat_image_recognition_switch
                else:
                    _img_enabled = False
                try:
                    if _img_enabled:
                        if msg.type == 'image':
                            _down_path = msg.download()
                            if _down_path:
                                msg.content = str(_down_path)
                            else:
                                log("ERROR", f"{_down_path}")
                                log("ERROR", "message_handle_callback下载图片出错")
                        elif msg.type == 'quote':
                            _down_path = msg.download_quote_image()
                            if _down_path:
                                msg.content = msg.content+"+引用的图片:"+str(_down_path)
                            else:
                                log("INFO", "引用内容不是图片或视频")
                        elif msg.type == 'voice':
                            try:
                                _voice_content = msg.to_text()
                                if _voice_content:
                                    msg.content = str(_voice_content)
                                else:
                                    log("WARNING", "消息自动语音转文字失败")
                            except Exception as e:
                                log("WARNING", "消息自动语音转文字失败")
                except Exception as e:
                    log(level="ERROR", message=f"message_handle_callback下载图片出错,请尝试将windows设置屏幕缩放设置为100%后再尝试: {e}")
                self.bot._incr_received()
                self.bot.last_msg_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                self.bot.last_msg_sender = msg.sender

                if self.config.AllListen_switch:
                    for listen_chat in self.bot.all_Mode_listen_list:
                        if listen_chat[0] == chat.who:
                            log(message=chat.who + " 对话最新消息时间已更新")
                            listen_chat[1] = time.time()
                            break
                result = self.process_message(chat, msg)
                if self.config.custom_forward_switch:
                    try:
                        self._handle_custom_forward(chat, msg)
                    except Exception as _fwd_e:
                        log(level="ERROR", message=f"自定义转发处理出错: {_fwd_e}")
                if not result:
                    self.bot.is_err(
                        self.bot.wx.nickname + f" wxbot处理监听新消息失败！",
                        text + '\n' + result['message'],
                    )

            elif msg.attr == "system":
                if self.config.group_welcome and chat.who in self.config.group:
                    result = self.bot.send_group_welcome_msg(chat, msg)
                    if not result:
                        self.bot.is_err(
                            self.bot.wx.nickname + f" wxbot发送群新人欢迎语失败！",
                            text + '\n' + result['message'],
                        )

            elif msg.attr == "self":
                if chat.who == self.config.cmd:
                    self.bot._incr_received()
                    self.bot.last_msg_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    self.bot.last_msg_sender = msg.sender
                    result = self.bot.process_command(chat, msg)
                    if not result:
                        self.bot.is_err(
                            self.bot.wx.nickname + f" wxbot处理管理员指令失败！",
                            text + '\n' + result['message'],
                        )

            if self.config.memory_switch and self.bot.memory_manager:
                try:
                    self.bot.memory_manager.save_message(
                        chat_name=chat.who,
                        sender=msg.sender,
                        content=msg.content,
                        msg_type=msg.type,
                        msg_attr=msg.attr,
                        max_count=self.config.memory_max_count,
                        message_time=message_time,
                    )
                except Exception as e:
                    log(level="WARNING", message=f"写入记忆失败: {e}")
        except Exception as e:
            self.bot.callback_is_die = True
            self.bot.is_err(self.bot.wx.nickname + " wxbot回调函数处理出错！处理监听失败！！", e)

    def process_message(self, chat, message):
        """
        处理单条消息的核心分发逻辑：
        1. 黑/白名单过滤
        2. 群聊消息（含 @ 检测和关键词回复）
        3. 管理员命令解析
        4. 普通好友 AI 回复

        :param chat:    聊天窗口子对象
        :param message: 消息对象
        :return:        发送结果
        """
        log(message=f"处理 {chat.who} 窗口 {message.sender} 消息：{message.content}")
        result = True

        is_monitored = (
            (self.config.AllListen_switch and chat.who not in self.config.listen_list)
            or (not self.config.AllListen_switch and chat.who in self.config.listen_list)
            or (chat.who in self.config.group and self.config.group_switch)
            or (chat.who == self.config.cmd)
        )
        if not is_monitored:
            return True

        if chat.who in self.config.group and not self.config.group_switch:
            return True
        if chat.who in self.config.group:
            if self.config.group_keyword_switch:
                _kw_at_pass = (not self.config.group_keyword_at_only) or (self.config.AtMe in message.content)
                if _kw_at_pass:
                    for keyword in self.config.keyword_dict:
                        if keyword in message.content:
                            log(message=f"群组 {chat.who} 关键字消息：" + message.content)
                            self.config.human_delay()
                            result = chat.SendMsg(msg=self.config.keyword_dict[keyword])
                            self.bot._incr_replied()
                            time.sleep(1)
                            return result

            if (self.config.AtMe in message.content and self.config.group_reply_at) \
                    or not self.config.group_reply_at:
                if self.config.group_listen_only:
                    log(message=f"群组 {chat.who} 已启用只监听不AI回复，跳过 AI 调用")
                    return result
                # 群组 AI 生成 + 发送 → AIWorker，回调线程不触碰 AI 网络调用
                self.bot.enqueue_ai(
                    lambda: self._cb_group_ai_and_send(chat, message),
                    context=f"group:{chat.who}",
                )
                return result

            return result

        if chat.who == self.config.cmd:
            result = self.bot.process_command(chat, message)
            return result

        if (not self.config.AllListen_switch and
                chat.who not in self.config.listen_list and
                chat.who not in self.config.group and
                chat.who != self.config.cmd):
            return result
        if (self.config.AllListen_switch and chat.who in self.config.listen_list) or\
            (self.config.AllListen_switch and chat.chat_type == 'group'):
            return result
        result = self.wx_send_ai(chat, message)
        return result

    def wx_send_ai(self, chat, message, message_record=None):
        """
        对私聊消息调用 AI 接口并发送回复。
        支持关键词优先匹配，超过 2000 字时自动分段发送。
        集成消息存储，发送操作通过任务队列异步执行。

        :param chat:           聊天窗口子对象
        :param message:        消息对象
        :param message_record: 已保存的消息记录（可选，避免重复保存）
        :return:               任务提交结果，True 表示成功提交，False 表示跳过
        """
        user_key = self._get_reply_count_key(chat, message)
        msg_id = None

        if self.message_store and not message_record:
            message_record = self.message_store.save_message(
                chat_name=chat.who,
                sender=message.sender,
                content=message.content,
                msg_type=message.type,
                msg_attr=message.attr,
                message_time=datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            )
            msg_id = message_record.id

        if self.config.chat_reply_confirm_switch and message_record:
            # 关键字命中 → 预生成关键字回复，放入待确认队列，不直接操作 UI
            _kw = self._match_keyword(message.content) if self.config.chat_keyword_switch else None
            if _kw:
                self.message_store.add_pending_confirm(
                    message_record,
                    pending_reply=_kw,
                    pending_source='keyword',
                )
                log(message=f"私聊 {chat.who} 关键字命中，回复已预生成，进入待确认队列")
                return True

            # 只监听不 AI 回复：直接标记完成，不进待确认
            if self.config.chat_listen_only:
                log(message=f"私聊 {chat.who} 已启用只监听不AI回复，跳过 AI 调用")
                if message_record.id:
                    self.message_store.set_message_status(chat.who, message_record.id, "processed")
                return True

            # 先入待确认队列，AI 预生成异步回填（任务队列，失败重试 → 死信）
            self.message_store.add_pending_confirm(message_record)
            log(message=f"私聊 {chat.who} 消息已加入待确认队列，AI 回复预生成中")
            return self.submit_ai_pregenerate_task(
                chat_name=chat.who,
                message=message,
                msg_id=message_record.id,
            )

        api_error_should_mark = False

        # 关键字应答：无需调 AI，派发线程直接处理
        if self.config.chat_keyword_switch:
            _kw = self._match_keyword(message.content)
            if _kw:
                log(message=f"私聊 {chat.who} 关键字消息：" + message.content)
                self._send_reply_segments(
                    chat_name=chat.who,
                    reply=_kw,
                    msg_id=msg_id,
                    api_error_reply=False,
                    api_error_should_mark=False,
                    user_key=user_key,
                )
                return True

        # 只监听不 AI 回复 / 回复轮数超限：派发线程直接标记
        if self.config.chat_listen_only:
            log(message=f"私聊 {chat.who} 已启用只监听不AI回复，跳过 AI 调用")
            if self.message_store and msg_id:
                self.message_store.set_message_status(chat.who, msg_id, "processed")
            return True
        limit_handled, limit_result = self._check_chat_max_round_limit(chat, user_key)
        if limit_handled:
            if self.message_store and msg_id:
                self.message_store.set_message_status(chat.who, msg_id, "processed")
            return limit_result

        # 真正需要调 AI 的生成部分 → 任务队列 ai_reply 任务（失败重试 → 死信）
        return self.submit_ai_reply_task(
            chat_name=chat.who,
            message=message,
            msg_id=msg_id,
            user_key=user_key,
            api_error_once=self.config.api_error_reply_once,
            max_round_switch=self.config.chat_max_round_switch,
        )
