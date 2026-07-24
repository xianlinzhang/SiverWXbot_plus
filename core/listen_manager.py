import time
from logger import log
from wxautox4 import WeChat
from wxautox4.utils.useful import check_license


class ListenManager:
    """
    监听模式管理模块
    负责管理微信消息监听模式（白名单/黑名单/全局监听）及相关操作。
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    def listen_mode(self):
        """
        普通监听模式（白名单模式）：
        获取所有监听窗口的最新消息并逐一处理。
        """
        messages_dict = self.bot.wx.GetListenMessage()
        for chat in messages_dict:
            for message in messages_dict.get(chat, []):
                self.bot.process_message(chat, message)

    def ALLListen_mode(self, last_time, timeout=10):
        """
        全局监听模式主函数（黑名单模式）。
        包含三个内部子函数，分别处理：
        - 新消息获取（旧版 process_new_messages，已切换为 get_next_new_message）
        - 监听中会话的消息更新（process_listen_messages）
        - 超时会话的自动移除（remove_timeout_listen）

        :param last_time: 上次执行超时检测的时间戳
        :param timeout:   超时检测间隔（秒），默认 10 秒
        :return:          更新后的 last_time
        """
        if self.config.chatlog_listen_switch:
            return last_time

        def process_new_messages():
            """获取新消息并处理（仅处理非黑名单用户的消息）"""
            new_msg = self.bot.next_message_handle()
            for msg in new_msg:
                chat_name = msg[1]
                if chat_name == self.config.cmd:
                    self.bot.wx.SwitchChat(chat_name)
                    time.sleep(0.5)
                    new_msg_ = self.bot.next_message_handle()
                    for msg_ in new_msg_:
                        self.bot.process_message(self.bot.wx.GetChat(chat_name), msg_)
                elif chat_name in self.config.group and self.config.group_switch:
                    self.bot.wx.SwitchChat(chat_name)
                    time.sleep(0.5)
                    new_msg_ = self.bot.next_message_handle()
                    for msg_ in new_msg_:
                        self.bot.process_message(self.bot.wx.GetChat(chat_name), msg_)
                elif not self.config.AllListen_switch:
                    self.bot.wx.SwitchChat(chat_name)
                    time.sleep(0.5)
                    new_msg_ = self.bot.next_message_handle()
                    for msg_ in new_msg_:
                        self.bot.process_message(self.bot.wx.GetChat(chat_name), msg_)
                elif chat_name not in self.config.listen_list:
                    self.bot.wx.SwitchChat(chat_name)
                    time.sleep(0.5)
                    new_msg_ = self.bot.next_message_handle()
                    for msg_ in new_msg_:
                        self.bot.process_message(self.bot.wx.GetChat(chat_name), msg_)

        def process_listen_messages():
            """处理已在动态监听列表中的会话的消息"""
            for listen_chat in self.bot.all_Mode_listen_list:
                chat_name = listen_chat[0]
                self.bot.wx.SwitchChat(chat_name)
                time.sleep(0.5)
                new_msg = self.bot.next_message_handle()
                for msg in new_msg:
                    self.bot.process_message(self.bot.wx.GetChat(chat_name), msg)

        def remove_timeout_listen():
            """移除超时未更新的会话（超时时间由配置决定）"""
            current_time = time.time()
            timeout_seconds = self.config.all_listen_timeout * 60
            self.bot.all_Mode_listen_list = [
                chat for chat in self.bot.all_Mode_listen_list
                if (current_time - chat[1]) < timeout_seconds
            ]

        process_new_messages()
        process_listen_messages()

        current_time = time.time()
        if current_time - last_time > timeout:
            remove_timeout_listen()
            last_time = current_time

        return last_time

    def new_msg_get_plus(self, chat_records):
        """
        从聊天记录中过滤出"上一条自己发送消息之后"的新消息：
        1. 过滤掉 SYS 与 Recall 类型消息（保留 Time 消息）
        2. 若存在 Self 消息：定位最新 Self 消息，取其后的记录；
           若后续有 Time 消息，则取最新 Time 消息之后的对方消息。
        3. 若无 Self 消息：定位最新 Time 消息，取其后的对方消息；
           若也无 Time 消息，返回全部过滤后的消息。

        :param chat_records: wx.GetAllMessage() 返回的消息列表
        :return:             过滤后的新消息列表
        """
        filtered = [msg for msg in chat_records if msg[0] not in ("SYS", "Recall")]

        if any(msg[0] == "Self" for msg in filtered):
            latest_self_index = None
            for idx, msg in enumerate(filtered):
                if msg[0] == "Self":
                    latest_self_index = idx
            post_self = filtered[latest_self_index + 1:]

            latest_time_index = None
            for idx, msg in enumerate(post_self):
                if msg[0] == "Time":
                    latest_time_index = idx

            if latest_time_index is not None:
                post_time = post_self[latest_time_index + 1:]
                return [msg for msg in post_time if msg[0] not in ("Self", "Time")]
            else:
                return post_self
        else:
            latest_time_index = None
            for idx, msg in enumerate(filtered):
                if msg[0] == "Time":
                    latest_time_index = idx

            if latest_time_index is not None:
                post_time = filtered[latest_time_index + 1:]
                return [msg for msg in post_time if msg[0] not in ("Self", "Time")]
            else:
                return filtered

    def next_message_handle(self):
        """
        在全局监听模式中辅助获取新消息，防止消息遗漏。
        获取当前窗口全部消息后调用 new_msg_get_plus 过滤出真正的新消息。

        :return: 过滤后的新消息列表
        """
        if self.config.chatlog_listen_switch:
            return []
        
        AllMessage = self.bot.wx.GetAllMessage()
        new_msg = self.new_msg_get_plus(AllMessage)
        return new_msg

    def add_chat_to_listen(self, chat):
        """
        将指定会话加入全局动态监听列表，并向 wxautox 注册监听回调。
        在 Chatlog 模式下，仅获取子窗口用于发送消息，不添加到动态监听列表。

        :param chat: 会话昵称（字符串）
        :return:     校验成功的子窗口对象；失败返回 None
        """
        sub_chat = self._add_and_verify_subwindow(chat)
        if not sub_chat:
            return None

        if self.config.chatlog_listen_switch:
            return sub_chat

        if self.is_chat_listened(chat):
            return sub_chat

        log(message=chat + ' 已添加监听，正在加入动态监听列表')
        self.bot.all_Mode_listen_list.append([chat, time.time()])
        log(message='当前全局模式动态监听列表：' + str(self.bot.all_Mode_listen_list))
        return sub_chat

    def is_chat_listened(self, chat):
        """
        判断指定会话是否已在全局动态监听列表中。

        :param chat: 会话昵称（字符串）
        :return:     True 表示已监听，False 表示未监听
        """
        return any(listen_chat[0] == chat for listen_chat in self.bot.all_Mode_listen_list)

    def _add_listen_chat_once(self, nickname, label):
        """执行一次 AddListenChat，并记录基础结果。"""
        result = self.bot.wx.AddListenChat(nickname=nickname, callback=self.bot.message_handle_callback)
        if result:
            log(message=f"添加{label} {nickname} 监听完成")
        else:
            log(level="ERROR", message=f"添加{label} {nickname} 监听失败, {self.bot._listen_add_error(result)}")
        return result

    def _verify_initial_listeners(self, expected_chats, retry_count=3):
        """
        初始化监听完成后，用 GetAllSubWindow 校验所有应监听对象。
        未出现在子窗口列表中的对象最多重试 retry_count 次，仍失败则跳过实际监听。
        """
        expected = []
        seen = set()
        for nickname in expected_chats:
            if nickname and nickname not in seen:
                expected.append(nickname)
                seen.add(nickname)
        if not expected:
            return

        listened_names = self.bot._get_all_subwindow_names()
        missing = [nickname for nickname in expected if nickname not in listened_names]
        if not missing:
            log(message="初始化监听子窗口校验通过")
            return

        log(level="WARNING", message=f"初始化监听子窗口缺失，准备重试: {missing}")
        for attempt in range(1, retry_count + 1):
            for nickname in missing:
                time.sleep(0.5)
                self._add_listen_chat_once(nickname, "初始化重试")
            listened_names = self.bot._get_all_subwindow_names()
            missing = [nickname for nickname in missing if nickname not in listened_names]
            if not missing:
                log(message=f"初始化监听子窗口重试第 {attempt} 次后校验通过")
                return
            log(level="WARNING", message=f"初始化监听子窗口第 {attempt} 次重试后仍缺失: {missing}")

        log(level="ERROR", message=f"以下对象初始化监听重试失败，已跳过实际监听: {missing}")

    def _add_and_verify_subwindow(self, nickname, retry_count=3):
        """
        添加单个监听并用 GetSubWindow 校验，返回校验成功的子窗口对象。
        初次添加失败或未返回子窗口时再重试 retry_count 次。
        """
        total_attempts = retry_count + 1
        for attempt in range(1, total_attempts + 1):
            if attempt == 1:
                log(message=f"{nickname} 不在动态监听列表，正在添加监听")
            else:
                log(level="WARNING", message=f"{nickname} 动态监听校验失败，正在进行第 {attempt - 1} 次重试")
                time.sleep(0.5)

            self._add_listen_chat_once(nickname, "动态监听")
            sub_chat = self.bot._get_verified_subwindow(nickname)
            if sub_chat:
                return sub_chat

        log(level="ERROR", message=f"{nickname} 动态监听添加失败，重试 {retry_count} 次后仍未获取到子窗口，已跳过")
        return None

    def _remove_dynamic_listen_chat(self, chat):
        """从全局模式动态监听列表中移除指定会话。"""
        before_count = len(self.bot.all_Mode_listen_list)
        self.bot.all_Mode_listen_list = [
            listen_chat for listen_chat in self.bot.all_Mode_listen_list
            if listen_chat[0] != chat
        ]
        if len(self.bot.all_Mode_listen_list) != before_count:
            log(level="WARNING", message=f"{chat} 动态监听子窗口校验失败，已从动态监听列表移除")

    def _remove_listen_chat_verified(self, nickname):
        """移除监听后用 GetAllSubWindow 校验子窗口是否已消失。"""
        try:
            self.bot.wx.RemoveListenChat(nickname)
        except Exception as e:
            log(level="ERROR", message=f"{nickname} 删除监听失败: {e}")
            return False

        time.sleep(0.2)
        listened_names = self.bot._try_get_all_subwindow_names()
        if listened_names is None:
            log(level="ERROR", message=f"{nickname} 删除监听后无法校验，保留在动态监听列表")
            return False
        if nickname not in listened_names:
            log(message=f"{nickname} 删除监听校验通过")
            return True

        log(level="ERROR", message=f"{nickname} 删除监听校验失败，子窗口仍存在，保留在动态监听列表")
        return False

    def _is_contact_in_listen_list(self, chat_name, listen_list):
        """判断指定会话是否在监听列表中。"""
        return chat_name in listen_list

    def wxautox_activate_check(self):
        """
        校验 wxautox 授权状态。

        :return: True 表示已激活，False 表示未激活
        """
        if self.bot.wx is None:
            self.bot.wx = WeChat()
        try:
            result = check_license()
            if result:
                return True
            return False
        except Exception as e:
            log(level="ERROR", message=f"wxautox授权校验出错: {e}")
            return False

    def init_wx_listeners(self):
        """
        初始化微信监听器：
        - 创建 WeChat 客户端对象
        - 根据配置注册监听回调
        - 校验监听子窗口
        """
        if self.bot.wx is None:
            self.bot.wx = WeChat()

        if self.bot.memory_manager is None:
            from core.memory_manager import MemoryManager
            import os
            import sys
            _base = os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            base_path = os.path.join(_base, 'memory')
            wx_id = self.bot.wx.nickname if hasattr(self.bot.wx, 'nickname') else 'default'
            self.bot.memory_manager = MemoryManager(wx_id, base_path)

        expected_chats = []

        if not self.config.chatlog_listen_switch:
            if self.config.cmd:
                self._add_listen_chat_once(self.config.cmd, "管理员")
                expected_chats.append(self.config.cmd)

            for chat in self.config.listen_list:
                self._add_listen_chat_once(chat, "监听列表")
                expected_chats.append(chat)

            for group in self.config.group:
                if self.config.group_switch:
                    self._add_listen_chat_once(group, "群组")
                    expected_chats.append(group)

            self._verify_initial_listeners(expected_chats)

        if self.config.chatlog_listen_switch:
            self.bot._init_chatlog_client()

    def _listen_add_error(self, result):
        """
        将 AddListenChat 返回的错误码转换为可读消息。

        :param result: AddListenChat 返回的结果
        :return: 错误描述字符串
        """
        if isinstance(result, dict):
            msg = result.get('message', str(result))
            return msg
        return str(result)

    def _get_all_subwindow_names(self):
        """获取所有监听子窗口的名称列表。"""
        try:
            windows = self.bot.wx.GetAllSubWindow()
            return [win['nickname'] for win in windows] if windows else []
        except Exception:
            return []

    def _try_get_all_subwindow_names(self):
        """安全获取所有监听子窗口名称，失败返回 None。"""
        try:
            return self._get_all_subwindow_names()
        except Exception:
            return None

    def _get_verified_subwindow(self, nickname):
        """
        获取指定昵称的子窗口对象并校验。

        :param nickname: 会话昵称
        :return: 子窗口对象，失败返回 None
        """
        try:
            sub_chat = self.bot.wx.GetChat(nickname)
            if sub_chat and hasattr(sub_chat, 'who'):
                return sub_chat
            return None
        except Exception:
            return None

    def check_wechat_window(self):
        """
        检查微信窗口是否在线。

        :return: True 表示在线，False 表示离线
        """
        try:
            if self.wx and self.bot.wx.CheckWeChat():
                return True
            return False
        except Exception:
            return False
