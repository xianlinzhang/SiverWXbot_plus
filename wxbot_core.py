#!/usr/bin/env python3
# Siver微信机器人 siver_wxbot - 面向对象版本 - wxautox4版本
# 作者：https://www.siver.top
from wxautox4.utils.useful import check_license

version = "V4.7.27"
version_log = "V4.7.27 - 优化远程访问、关闭SESSION_COOKIE_HTTPONLY方便内外网访问、优化面板接口测试"

import random
# ============================================================
# 标准库导入
# ============================================================
import sys
import time
import traceback
from datetime import datetime, timedelta

# ============================================================
# 第三方库导入
# ============================================================
import schedule  # 定时任务库

from wxautox4 import WxParam
# ============================================================
# wxautox 相关导入（Plus版，需向作者购买授权）
# 购买地址：https://www.siverking.online/static/img/siver_wx.jpg
# ============================================================
from wxautox4.msgs import *

# Coze 官方 Python 库

is_wxautox = True  # 标识当前使用的是 wxautox Plus 版本

# ============================================================
# 本地模块导入
# ============================================================
from logger import log
from core.config_manager import WXBotConfig
from core.memory_manager import ReplyCountStore
from core.ai_api import OpenAIAPI, DifyAPI, CozeAPI, DusAPI
from core.message_handler import MessageHandler
from core.command_handler import CommandHandler
from core.listen_manager import ListenManager
from core.chatlog_manager import ChatlogManager
from core.wx_utils import WXUtils
from core.message_store import MessageStore
from core.redis_manager import RedisManager
from core.task_queue import TaskQueue

# ============================================================
# wxautox 全局参数配置
# 说明：
#   MESSAGE_HASH         - 是否启用消息哈希辅助判断，开启后稍微影响性能，默认 False
#   FORCE_MESSAGE_XBIAS  - 是否每次启动都重新自动获取 X 偏移量，默认 False
# 其他可配置参数（供参考，未在此处修改）：
#   ENABLE_FILE_LOGGER        (bool) : 是否启用日志文件，默认 True
#   DEFAULT_SAVE_PATH         (str)  : 下载文件/图片默认保存路径
#   DEFAULT_MESSAGE_XBIAS     (int)  : 头像到消息 X 偏移量，默认 51
#   LISTEN_INTERVAL           (int)  : 监听消息时间间隔（秒），默认 1
#   LISTENER_EXCUTOR_WORKERS  (int)  : 监听执行器线程池大小，默认 4
#   SEARCH_CHAT_TIMEOUT       (int)  : 搜索聊天对象超时时间（秒），默认 5
# ============================================================
WxParam.MESSAGE_HASH = True         # 启用消息哈希，辅助消息去重判断
WxParam.FORCE_MESSAGE_XBIAS = True  # 每次启动强制重新获取 X 偏移量
WxParam.CHAT_WINDOW_SIZE = (1500, 6000)
WxParam.DEFAULT_MESSAGE_YBIAS = 40


# ============================================================
# 配置管理类已移至 core/config_manager.py
# ============================================================


# ============================================================
# 对话记忆管理类已移至 core/memory_manager.py
# ============================================================


# ============================================================
# AI 接口类已移至 core/ai_api.py
# ============================================================

# ============================================================
# 微信机器人主类
# ============================================================

class WXBot:
    """
    微信机器人主类
    整合配置管理、AI 接口、微信监听、消息处理、命令分发等核心功能。
    """

    def __init__(self):
        self.ver      = version
        self.ver_log  = version_log
        self.run_flag = True                    # 主循环运行标志
        self.config   = WXBotConfig()           # 加载配置

        # 根据配置中的 api_sdk 字段选择对应的 AI 接口
        self.api = self._init_api()
        self.api_cache = {}                     # 群组专属接口缓存 {api_index: api_instance}

        self.wx                  = None         # WeChat 客户端对象（延迟初始化）
        self._moments_like_next_time  = None    # 下次随机朋友圈点赞的触发时间（datetime 或 None）
        self._random_moments_state    = {}     # 随机定时朋友圈运行状态缓存 {task_id: state_dict}
        self._random_msg_state        = {}     # 随机定时消息运行状态缓存 {task_id: state_dict}
        self.memory_manager      = None         # 记忆管理器（init_wx_listeners 时创建）
        self.all_Mode_listen_list = []           # 全局模式下的动态监听列表，元素格式：[昵称, 最新消息时间戳]
        self.start_time          = datetime.now()
        self.callback_is_die     = False        # 回调函数是否发生致命错误的标志
        self.msgs_path           = './wx_msgs/' # 消息本地存储路径（当前未启用）

        # Chatlog 相关
        self.chatlog_client     = None          # Chatlog HTTP 客户端（延迟初始化）
        self.chatlog_contact_map = {}           # wxid 和 reamrk为key, value 存的是整个用户信息
        self.chatlog_last_seq   = {}            # 各监听对象的最后处理消息序号 {chat_name: seq}

        # 运行统计数据（供状态面板采集）
        self.msg_received_count  = 0            # 已接收消息数
        self.msg_replied_count   = 0            # 已回复消息数
        self.last_msg_time       = None         # 最近一条消息的时间字符串
        self.last_msg_sender     = None         # 最近一条消息的发送者

        # 私聊回复轮数计数器
        _base = os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
        self.reply_count_store = ReplyCountStore(os.path.join(_base, 'config', 'reply_count.json'))

        # Redis 管理器（基础模块，无 bot 依赖）
        self.redis_manager = RedisManager(self.config)

        # 消息存储模块（先使用临时 wx_id，init_wx_listeners 后会更新）
        self.message_store = MessageStore('wxbot_default', self.config, bot=self)

        # 微信辅助工具（只需要 bot.config）
        self.wx_utils = WXUtils(self)

        # 消息处理器（需要 bot.message_store）
        self.message_handler = MessageHandler(self)

        # 命令处理器（需要 bot.message_store）
        self.command_handler = CommandHandler(self)

        # 监听管理器（需要 bot.config，bot.wx_lock 可选）
        self.listen_manager = ListenManager(self)

        # Chatlog 管理器（需要 bot.message_store，bot.wx_lock）
        self.chatlog_manager = ChatlogManager(self)

        # 任务队列（需要 bot.redis_manager）
        self.task_queue = TaskQueue(self)

    def _init_api(self):
        """根据配置中的 api_sdk 字段实例化对应的 AI 接口对象（默认接口）"""
        sdk = self.config.api_sdk
        if sdk == "Dify":
            log(message="使用Dify API")
            return DifyAPI(self.config)
        elif sdk == "OpenAI SDK":
            log(message="使用OpenAI SDK")
            return OpenAIAPI(self.config)
        elif sdk == "Coze":
            log(message="使用Coze API")
            return CozeAPI(self.config)
        elif sdk == "DusAPI":
            log(message="使用DusAPI")
            return DusAPI(self.config)
        else:
            log(level="ERROR", message="未配置API SDK, 默认使用OpenAI SDK")
            return OpenAIAPI(self.config)

    def _init_api_by_index(self, idx):
        """
        根据指定接口索引实例化 AI 接口对象，用于群组专属接口。
        会创建一个只含接口相关字段的轻量代理配置对象，避免干扰主配置。
        """
        configs = self.config.api_configs
        if idx < 0 or idx >= len(configs):
            log(level="WARNING", message=f"群组接口索引 {idx} 超出范围，回退到默认接口")
            return self.api
        cfg = configs[idx]
        sdk = cfg.get('sdk', '')

        # 轻量代理配置：仅覆盖接口相关字段，其余不涉及
        class _ApiProxy:
            pass
        tmp = _ApiProxy()
        tmp.api_sdk  = sdk
        tmp.api_key  = cfg.get('key', '')
        tmp.base_url = cfg.get('url', '')
        tmp.model1   = cfg.get('model', '')
        tmp.prompt   = ''   # prompt 总是通过 chat() 调用时显式传入，此处置空

        log(message=f"初始化群组专属接口：索引{idx}  SDK:{sdk}  模型:{tmp.model1}")
        if sdk == "Dify":
            return DifyAPI(tmp)
        elif sdk == "OpenAI SDK":
            return OpenAIAPI(tmp)
        elif sdk == "Coze":
            return CozeAPI(tmp)
        elif sdk == "DusAPI":
            return DusAPI(tmp)
        else:
            return OpenAIAPI(tmp)

    def _init_chatlog_client(self):
        """初始化 Chatlog 客户端（委托给 ChatlogManager）"""
        return self.chatlog_manager._init_chatlog_client()

    def refresh_chatlog_contacts(self):
        """刷新 Chatlog 联系人（委托给 ChatlogManager）"""
        return self.chatlog_manager.refresh_chatlog_contacts()

    # ----------------------------------------------------------
    # AI 上下文增强（委托给 ChatlogManager）
    # ----------------------------------------------------------

    def _enrich_context_with_chatlog(self, chat_name, base_history=None):
        """合并 Chatlog 历史消息增强上下文（委托给 ChatlogManager）"""
        return self.chatlog_manager._enrich_context_with_chatlog(chat_name, base_history)

    # ----------------------------------------------------------
    # Chatlog 轮询监听模式（委托给 ChatlogManager）
    # ----------------------------------------------------------

    def _convert_chatlog_msg(self, msg_dict):
        """转换 Chatlog 消息格式（委托给 ChatlogManager）"""
        return self.chatlog_manager._convert_chatlog_msg(msg_dict)

    def chatlog_process_message(self, chat_name, msg_dict):
        """处理 Chatlog 消息（委托给 ChatlogManager）"""
        return self.chatlog_manager.chatlog_process_message(chat_name, msg_dict)

    def chatlog_listen_loop(self):
        """Chatlog 监听循环（委托给 ChatlogManager）"""
        return self.chatlog_manager.chatlog_listen_loop()



    def _get_reply_count_key(self, chat, message=None):
        """获取回复计数 key（委托给 MessageHandler）"""
        return self.message_handler._get_reply_count_key(chat, message)

    def _get_chat_max_round(self, user_name):
        """获取私聊回复轮数上限（委托给 MessageHandler）"""
        return self.message_handler._get_chat_max_round(user_name)

    def _check_chat_max_round_limit(self, chat, user_key):
        """检查私聊回复轮数限制（委托给 MessageHandler）"""
        return self.message_handler._check_chat_max_round_limit(chat, user_key)

    def _is_custom_forward_source(self, chat_who):
        """判断是否为自定义转发来源（委托给 MessageHandler）"""
        return self.message_handler._is_custom_forward_source(chat_who)

    def _handle_custom_forward(self, chat, message):
        """处理自定义转发（委托给 MessageHandler）"""
        return self.message_handler._handle_custom_forward(chat, message)

    # ----------------------------------------------------------
    # 管理员命令分发
    # ----------------------------------------------------------

    def process_command(self, chat, message):
        """命令处理核心逻辑（委托给 CommandHandler）"""
        return self.command_handler.process_command(chat, message)

    def _build_status_msg(self, chat, message):
        """构建状态消息（委托给 CommandHandler）"""
        return self.command_handler._build_status_msg(chat, message)

    def handle_add_user(self, chat, message):
        """添加用户（委托给 CommandHandler）"""
        return self.command_handler.handle_add_user(chat, message)

    def handle_remove_user(self, chat, message):
        """删除用户（委托给 CommandHandler）"""
        return self.command_handler.handle_remove_user(chat, message)

    def handle_group_switch_status(self, chat, message):
        """群机器人状态（委托给 CommandHandler）"""
        return self.command_handler.handle_group_switch_status(chat, message)

    def handle_add_group(self, chat, message):
        """添加群（委托给 CommandHandler）"""
        return self.command_handler.handle_add_group(chat, message)

    def handle_remove_group(self, chat, message):
        """删除群（委托给 CommandHandler）"""
        return self.command_handler.handle_remove_group(chat, message)

    def handle_enable_group_bot(self, chat, message):
        """开启群机器人（委托给 CommandHandler）"""
        return self.command_handler.handle_enable_group_bot(chat, message)

    def handle_disable_group_bot(self, chat, message):
        """关闭群机器人（委托给 CommandHandler）"""
        return self.command_handler.handle_disable_group_bot(chat, message)

    def handle_enable_welcome_msg(self, chat, message):
        """开启欢迎语（委托给 CommandHandler）"""
        return self.command_handler.handle_enable_welcome_msg(chat, message)

    def handle_disable_welcome_msg(self, chat, message):
        """关闭欢迎语（委托给 CommandHandler）"""
        return self.command_handler.handle_disable_welcome_msg(chat, message)

    def handle_welcome_msg_status(self, chat, message):
        """欢迎语状态（委托给 CommandHandler）"""
        return self.command_handler.handle_welcome_msg_status(chat, message)

    def handle_change_welcome_msg(self, chat, message):
        """更改欢迎语（委托给 CommandHandler）"""
        return self.command_handler.handle_change_welcome_msg(chat, message)

    def handle_list_api_configs(self, chat, message):
        """列出接口配置（委托给 CommandHandler）"""
        return self.command_handler.handle_list_api_configs(chat, message)

    def handle_select_api_config(self, chat, message):
        """选择接口（委托给 CommandHandler）"""
        return self.command_handler.handle_select_api_config(chat, message)

    def handle_change_prompt(self, chat, message):
        """更改AI设定（委托给 CommandHandler）"""
        return self.command_handler.handle_change_prompt(chat, message)

    def handle_list_prompts(self, chat, message):
        """列出Prompt（委托给 CommandHandler）"""
        return self.command_handler.handle_list_prompts(chat, message)

    def handle_switch_prompt(self, chat, message):
        """切换Prompt（委托给 CommandHandler）"""
        return self.command_handler.handle_switch_prompt(chat, message)

    def handle_clear_memory(self, chat, message):
        """清除记忆（委托给 CommandHandler）"""
        return self.command_handler.handle_clear_memory(chat, message)

    def handle_clear_user_memory(self, chat, message):
        """清除用户记忆（委托给 CommandHandler）"""
        return self.command_handler.handle_clear_user_memory(chat, message)

    def handle_clear_all_memory(self, chat, message):
        """清除全部记忆（委托给 CommandHandler）"""
        return self.command_handler.handle_clear_all_memory(chat, message)

    def handle_image_recognition_status(self, chat, message):
        """图片识别状态（委托给 CommandHandler）"""
        return self.command_handler.handle_image_recognition_status(chat, message)

    def handle_split_reply_status(self, chat, message):
        """拆分回复状态（委托给 CommandHandler）"""
        return self.command_handler.handle_split_reply_status(chat, message)

    def handle_new_friend_status(self, chat, message):
        """新好友状态（委托给 CommandHandler）"""
        return self.command_handler.handle_new_friend_status(chat, message)

    def send_command_list(self, chat):
        """发送命令列表（委托给 CommandHandler）"""
        return self.command_handler.send_command_list(chat)

    # ----------------------------------------------------------
    # 群组辅助功能（委托给 WXUtils）
    # ----------------------------------------------------------

    def find_new_group_friend(self, msg, flag):
        """解析新群成员昵称（委托给 WXUtils）"""
        return self.wx_utils.find_new_group_friend(msg, flag)

    def send_group_welcome_msg(self, chat, message):
        """发送群欢迎语（委托给 WXUtils）"""
        return self.wx_utils.send_group_welcome_msg(chat, message)

    # ----------------------------------------------------------
    # 新好友处理（委托给 WXUtils）
    # ----------------------------------------------------------

    def is_image_path(self, s: str) -> bool:
        """判断是否为图片路径（委托给 WXUtils）"""
        return self.wx_utils.is_image_path(s)

    def _remark_unit_len(self, text):
        """计算备注长度单位（委托给 WXUtils）"""
        return WXUtils._remark_unit_len(text)

    def _truncate_remark_units(self, text, max_units):
        """裁剪备注（委托给 WXUtils）"""
        return WXUtils._truncate_remark_units(text, max_units)

    def build_new_friend_remark(self, nickname):
        """生成新好友备注（委托给 WXUtils）"""
        return self.wx_utils.build_new_friend_remark(nickname)

    def Pass_New_Friends(self):
        """通过新好友请求（委托给 WXUtils）"""
        return self.wx_utils.Pass_New_Friends()

    # ----------------------------------------------------------
    # 定时消息发送（委托给 WXUtils）
    # ----------------------------------------------------------

    def send_scheduled_msg(self, targets, msgs, repeat_type, weekdays, dates, task_id):
        """发送定时消息（委托给 WXUtils）"""
        return self.wx_utils.send_scheduled_msg(targets, msgs, repeat_type, weekdays, dates, task_id)

    # ----------------------------------------------------------
    # 定时朋友圈发送（委托给 WXUtils）
    # ----------------------------------------------------------

    def send_scheduled_moments(self, text, images, privacy, tags, repeat_type, weekdays, dates, task_id):
        """发送定时朋友圈（委托给 WXUtils）"""
        return self.wx_utils.send_scheduled_moments(text, images, privacy, tags, repeat_type, weekdays, dates, task_id)

    # ----------------------------------------------------------
    # 随机功能（委托给 WXUtils）
    # ----------------------------------------------------------

    def _do_moments_like(self):
        """随机朋友圈点赞（委托给 WXUtils）"""
        return self.wx_utils._do_moments_like()

    def _check_random_moments(self):
        """检查随机朋友圈（委托给 WXUtils）"""
        return self.wx_utils._check_random_moments()

    def _check_random_msg(self):
        """检查随机消息（委托给 WXUtils）"""
        return self.wx_utils._check_random_msg()

    # ----------------------------------------------------------
    # 消息监听模式（委托给 ListenManager）
    # ----------------------------------------------------------

    def listen_mode(self):
        """普通监听模式（委托给 ListenManager）"""
        return self.listen_manager.listen_mode()

    def new_msg_get_plus(self, chat_records):
        """过滤新消息（委托给 ListenManager）"""
        return self.listen_manager.new_msg_get_plus(chat_records)

    def next_message_handle(self):
        """获取下一条消息（委托给 ListenManager）"""
        return self.listen_manager.next_message_handle()

    def add_chat_to_listen(self, chat):
        """添加会话监听（委托给 ListenManager）"""
        return self.listen_manager.add_chat_to_listen(chat)

    def is_chat_listened(self, chat):
        """判断是否已监听（委托给 ListenManager）"""
        return self.listen_manager.is_chat_listened(chat)

    def ALLListen_mode(self, last_time, timeout=10):
        """全局监听模式（委托给 ListenManager）"""
        return self.listen_manager.ALLListen_mode(last_time, timeout)

    def _is_contact_in_listen_list(self, chat_name, listen_list):
        """判断是否在监听列表中（委托给 ListenManager）"""
        return self.listen_manager._is_contact_in_listen_list(chat_name, listen_list)

    # ----------------------------------------------------------
    # 微信初始化与状态检查（委托给 ListenManager）
    # ----------------------------------------------------------

    def init_wx_listeners(self):
        """初始化微信监听器（委托给 ListenManager）"""
        return self.listen_manager.init_wx_listeners()

    def check_wechat_window(self):
        """检查微信窗口是否在线（委托给 ListenManager）"""
        return self.listen_manager.check_wechat_window()

    def _listen_add_error(self, result):
        """转换监听添加错误码（委托给 ListenManager）"""
        return self.listen_manager._listen_add_error(result)

    def _get_all_subwindow_names(self):
        """获取所有监听子窗口名称（委托给 ListenManager）"""
        return self.listen_manager._get_all_subwindow_names()

    def _try_get_all_subwindow_names(self):
        """安全获取所有监听子窗口名称（委托给 ListenManager）"""
        return self.listen_manager._try_get_all_subwindow_names()

    def _get_verified_subwindow(self, nickname):
        """获取并校验子窗口对象（委托给 ListenManager）"""
        return self.listen_manager._get_verified_subwindow(nickname)

    # ----------------------------------------------------------
    # AI 消息处理辅助方法（委托给 MessageHandler）
    # ----------------------------------------------------------

    def _get_group_api(self, group_name):
        """获取群组 AI 接口（委托给 MessageHandler）"""
        return self.message_handler._get_group_api(group_name)

    def _get_chat_prompt(self, user_name):
        """获取私聊用户 Prompt（委托给 MessageHandler）"""
        return self.message_handler._get_chat_prompt(user_name)

    def _get_group_prompt(self, group_name):
        """获取群组 Prompt（委托给 MessageHandler）"""
        return self.message_handler._get_group_prompt(group_name)

    def _build_split_prompt(self, base_prompt, max_chars, max_count):
        """构建拆分 Prompt（委托给 MessageHandler）"""
        return self.message_handler._build_split_prompt(base_prompt, max_chars, max_count)

    def _parse_split_reply(self, reply, max_count):
        """解析拆分回复（委托给 MessageHandler）"""
        return self.message_handler._parse_split_reply(reply, max_count)

    def _clean_reply_for_send(self, reply):
        """清洗回复内容（委托给 MessageHandler）"""
        return self.message_handler._clean_reply_for_send(reply)

    def _chatlog_send_ai(self, chat_name, message):
        """Chatlog 模式下发送 AI 回复（委托给 MessageHandler）"""
        return self.message_handler._chatlog_send_ai(chat_name, message)

    # ----------------------------------------------------------
    # 错误报告
    # ----------------------------------------------------------

    def is_err(self, title, msg=None):
        """
        错误报告功能：记录日志并发送邮件通知。

        :param title: 错误标题
        :param msg:   错误详情（可选）
        """
        log(level="ERROR", message=f"{title} - {msg}" if msg else title)
        try:
            import email_send
            if msg:
                email_send.send_email(title, str(msg))
            else:
                email_send.send_email(title, "")
        except Exception as e:
            log(level="ERROR", message=f"发送错误邮件失败: {e}")

    # ----------------------------------------------------------
    # 机器人生命周期
    # ----------------------------------------------------------

    def get_status(self):
        """
        暴露机器人运行状态数据，供 Web 状态面板采集。
        :return: 包含运行参数和统计数据的字典
        """
        uptime_secs = int((datetime.now() - self.start_time).total_seconds())
        hours, rem  = divmod(uptime_secs, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str  = f"{hours}h {minutes}m {seconds}s"

        wx_nickname = None
        if self.wx:
            try:
                wx_nickname = self.wx.nickname
            except Exception:
                pass

        scheduled_enabled = sum(
            1 for t in self.config.scheduled_msg_list if t.get('enabled', True)
        ) if self.config.scheduled_msg_list else 0

        return {
            "running":            self.run_flag,
            "version":            self.ver,
            "start_time":         self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime":             uptime_str,
            "wx_nickname":        wx_nickname,
            "api_sdk":            self.config.api_sdk,
            "model":              self.api.DS_NOW_MOD,
            "api_index":          self.config.api_index + 1,
            "api_total":          len(self.config.api_configs),
            "listen_mode":        "黑名单" if self.config.AllListen_switch else "白名单",
            "listen_count":       len(self.config.listen_list),
            "chat_listen_only":   self.config.chat_listen_only,
            "group_switch":       self.config.group_switch,
            "group_listen_only":  self.config.group_listen_only,
            "group_count":        len(self.config.group),
            "msg_received":       self.msg_received_count,
            "msg_replied":        self.msg_replied_count,
            "last_msg_time":      self.last_msg_time,
            "last_msg_sender":    self.last_msg_sender,
            "callback_is_die":    self.callback_is_die,
            "scheduled_switch":   self.config.scheduled_msg_switch,
            "scheduled_count":    scheduled_enabled,
            "chat_keyword_switch":   self.config.chat_keyword_switch,
            "group_keyword_switch":  self.config.group_keyword_switch,
            "group_keyword_at_only": self.config.group_keyword_at_only,
            "keyword_count":         len(self.config.keyword_dict),
            "memory_switch":         self.config.memory_switch,
            "memory_context_count":  self.config.memory_context_count,
            "reply_delay_switch":    self.config.reply_delay_switch,
            "reply_delay_min":       self.config.reply_delay_min,
            "reply_delay_max":       self.config.reply_delay_max,
            "chat_max_round_switch": self.config.chat_max_round_switch,
            "chat_max_round_default": self.config.chat_max_round_default,
            "chat_max_round_reset_days": self.config.chat_max_round_reset_days,
            "pause_chat_reply":      self.config.chat_listen_only,
            "pause_group_reply":     self.config.group_listen_only,
            "chatlog_listen_switch":  self.config.chatlog_listen_switch,
            "chatlog_context_switch": self.config.chatlog_context_switch,
            "chatlog_connected":      self.chatlog_manager.chatlog_client is not None and self.chatlog_manager.chatlog_client.health_check(),
        }

    def stop_wxbot(self):
        """安全停止机器人：停止 wxautox 监听并退出主循环"""
        try:
            self.run_flag = False
            if self.wx and hasattr(self.wx, '_listener_thread'):
                self.wx.StopListening()
            if hasattr(self, 'task_queue') and self.task_queue:
                self.task_queue.stop()
            if hasattr(self, 'redis_manager') and self.redis_manager:
                self.redis_manager.close()
            log(level="WARNING", message='siver_wxbot安全退出！！')
            return True
        except Exception as e:
            if hasattr(self.wx, 'nickname'):
                self.is_err(self.wx.nickname + ' wxbot机器人关闭程序执行出错！！', e)
            else:
                self.is_err('wxbot机器人关闭程序执行出错！！', e)
            return False

    def main(self):
        """
        机器人主运行函数：
        - 校验 wxautox 授权
        - 初始化微信监听器
        - 进入主循环，依次执行：离线检测、新好友检测、全局监听/定时任务
        """
        # self.key_pass(2025, 6, 20, 0, 0, 0)  # 打包保护锁（按需启用）
        log(message=f"wxbot\n版本: wxbot_{self.ver}\n")

        # 初始化微信监听器
        try:
            self.init_wx_listeners()
            log(message=f"UI面板状态更新完成")

            wait_time      = 3   # 主循环每 1 秒轮询一次
            check_interval = 10  # 每 10 次循环执行一次离线检测
            check_counter      = 0
            check_new_counter  = 0
            last_time          = time.time()
            log(message='siver_wxbot初始化完成，开始监听消息(作者:https://www.siver.top)')
            self.run_flag = True
        except Exception as e:
            print(traceback.format_exc())
            log(level="ERROR", message=str(e) + "\n 初始化微信监听器失败，请检查微信是否启动登录正确，微信主窗口是否开着")

            log(level="ERROR", message=str(e) + "\n 请尝试退出wx再重新登录后再启动")
            log(level="ERROR", message=str(e) + "\n 若重启wx还是不行，就请重启整个面板程序，面板和wx都重启了还不行就请进入面板右上角文档检查环境要求，wx版本是否匹配,4.1.7 ~ 4.1.9.35")
            log(level="ERROR", message=str(e) + "\n 若以上情况都检查完没有问题，那大概率为wx本身或者windows系统不稳定导致的，重启程序即可，若是一直这样，如果您是虚拟机就请分配更多性能，若是实体机可以联系作者询问")
            self.run_flag = False

        # 主循环
        while self.run_flag:
            try:
                # ---- 离线检测模块（每 check_interval 次循环执行一次）----
                check_counter += 1
                if check_counter >= check_interval:
                    try:
                        if self.callback_is_die:
                            # 回调函数已出错，停止所有监听并退出主循环
                            if self.wx and hasattr(self.wx, '_listener_thread'):
                                self.wx.StopListening()
                            log(level="ERROR", message="检测到回调函数出错!!已停止所有监听并跳出主线程!!")
                            break
                        if not self.check_wechat_window():
                            # 微信离线，阻塞等待人工处理
                            self.is_err(self.wx.nickname + " wxbot监听出错！！微信可能已被弹出登录！！在线检查失败！！")
                            self.stop_wxbot()
                            log(level="ERROR", message=f"微信 {self.wx.nickname} 已被弹出登录！！请检查微信是否登录！！")
                            break
                    except Exception as e:
                        self.is_err(self.wx.nickname + " wxbot监听出错！！微信可能已被弹出登录！！在线检查失败！！", e)
                        self.stop_wxbot()
                        log(level="ERROR", message=f"微信 {self.wx.nickname} 已被弹出登录！！请检查微信是否登录！！")
                        break
                    check_counter = 0

                # ---- 新好友检测模块（随机检查，间隔由配置决定）----
                if self.config.new_frined_switch:
                    # 将秒数阈值除以循环周期得到循环次数（取整，最小1次）
                    check_new_friend_time_MIN = max(1, int(self.config.new_friend_check_min / wait_time))
                    check_new_friend_time_MAX = max(check_new_friend_time_MIN, int(self.config.new_friend_check_max / wait_time))
                    check_new_counter += 1
                    if check_new_counter >= random.randint(check_new_friend_time_MIN, check_new_friend_time_MAX):
                        try:
                            self.Pass_New_Friends()
                            # log(message="检查新好友完成")
                        except Exception as e:
                            self.is_err(self.wx.nickname + "  智能客服bot监听新好友出错！！请检查程序！！", e)
                        check_new_counter = 0

                # ---- Chatlog 监听模式 ----
                if self.config.chatlog_listen_switch:
                    try:
                        self.chatlog_listen_loop()
                    except Exception as e:
                        log(level="ERROR", message=f"Chatlog 监听模式出错：{e}")
                
                # ---- 全局监听模式（黑名单模式下启用）----
                elif self.config.AllListen_switch:
                    try:
                        last_time = self.ALLListen_mode(last_time=last_time)
                    except Exception as e:
                        if not self.run_flag:
                            log(level="ERROR", message=str(e) + "\n全局模式出错！！请检查程序！！")

                # ---- 定时任务执行（定时消息 / 定时朋友圈）----
                if self.config.scheduled_msg_switch or self.config.scheduled_moments_switch:
                    schedule.run_pending()

                # ---- 随机定时朋友圈模块 ----
                if self.config.random_moments_switch:
                    try:
                        self._check_random_moments()
                    except Exception as e:
                        log(level="ERROR", message=f"随机定时朋友圈模块出错：{e}")
                else:
                    self._random_moments_state = {}  # 开关关闭时清空缓存

                # ---- 随机定时消息模块 ----
                if self.config.random_msg_switch:
                    try:
                        self._check_random_msg()
                    except Exception as e:
                        log(level="ERROR", message=f"随机定时消息模块出错：{e}")
                else:
                    self._random_msg_state = {}  # 开关关闭时清空缓存

                # ---- 随机朋友圈点赞模块 ----
                if self.config.moments_like_switch:
                    if self._moments_like_next_time is None:
                        # 在 [min, max] 分钟范围内随机选取下次触发间隔
                        lo = max(1, self.config.moments_like_min)
                        hi = max(lo, self.config.moments_like_max)
                        delay_min = random.randint(lo, hi)
                        self._moments_like_next_time = datetime.now() + timedelta(minutes=delay_min)
                        log(message=f"随机朋友圈点赞：下次触发 {self._moments_like_next_time.strftime('%H:%M:%S')}（{delay_min} 分钟后）")
                    elif datetime.now() >= self._moments_like_next_time:
                        try:
                            self._do_moments_like()
                        except Exception as e:
                            log(level="ERROR", message=f"随机朋友圈点赞模块出错：{e}")
                        self._moments_like_next_time = None  # 执行后重置，下次循环重新生成间隔
                else:
                    self._moments_like_next_time = None  # 开关关闭时重置计时器

            except Exception as e:
                self.is_err(
                    self.wx.nickname + " wxbot消息处理出错！！微信可能已被弹出登录！！处理监听失败！！",
                    e,
                )
                self.run_flag = False

            _sleep_time = self.config.chatlog_polling_interval if self.config.chatlog_listen_switch else wait_time
            time.sleep(_sleep_time)

        log(level="WARNING", message='siver_wxbot主线程安全退出，正在退出监听...')

    def run(self):
        """启动机器人（对外暴露的入口函数）"""
        self.main()

    def stop(self):
        """停止机器人（对外暴露的入口函数）"""
        self.stop_wxbot()


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    bot = WXBot()
    bot.run()
