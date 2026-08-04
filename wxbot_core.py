#!/usr/bin/env python3
# Siver微信机器人 siver_wxbot - 面向对象版本 - wxautox4版本
# 作者：https://www.siver.top
from wxautox4.utils.useful import check_license

from core._version import version, version_log

import random
# ============================================================
# 标准库导入
# ============================================================
import sys
import threading
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
from core.deal_queue_consumer import DealQueueConsumer
from core.ai_worker import AIWorker

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

        # 同城信息队列消费者（需要 bot.redis_manager，不自动启动线程）
        self.deal_consumer = DealQueueConsumer(self)

        # AI 回复工作线程（方案 A：单 worker 串行，AI 生成从主线程解耦）
        self.ai_worker = AIWorker()
        # 统计计数线程安全（主循环 / task_queue 回调 / ai_worker / 群组路径多线程触碰）
        self._count_lock = threading.RLock()

        self._install_forwarders()

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
        tmp.app_type = cfg.get('app_type', 'chat')
        tmp.workflow_input_key = cfg.get('workflow_input_key', 'query')
        tmp.workflow_output_key = cfg.get('workflow_output_key', 'text')
        tmp.ai_request_timeout = self.config.ai_request_timeout
        tmp.redis_enabled = self.config.redis_enabled
        tmp.redis_host = self.config.redis_host
        tmp.redis_port = self.config.redis_port
        tmp.redis_db = self.config.redis_db
        tmp.redis_password = self.config.redis_password
        tmp.redis_timeout = self.config.redis_timeout
        tmp.redis_retry_count = self.config.redis_retry_count
        tmp.redis_fallback = self.config.redis_fallback
        tmp.redis_fallback_path = self.config.redis_fallback_path

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

    def _incr_replied(self, n: int = 1) -> None:
        """线程安全地递增已回复计数"""
        with self._count_lock:
            self.msg_replied_count += n

    def _incr_received(self, n: int = 1) -> None:
        """线程安全地递增已接收计数"""
        with self._count_lock:
            self.msg_received_count += n

    def enqueue_ai(self, job, context: str = "") -> None:
        """把 AI 生成任务交给 AIWorker（非阻塞），主线程不触碰 AI"""
        self.ai_worker.enqueue(job, context)

    def stop_wxbot(self):
        """安全停止机器人：停止 wxautox 监听并退出主循环"""
        try:
            self.run_flag = False
            if self.wx and hasattr(self.wx, '_listener_thread'):
                self.wx.StopListening()
            if hasattr(self, 'task_queue') and self.task_queue:
                self.task_queue.stop()
            if hasattr(self, 'ai_worker') and self.ai_worker:
                self.ai_worker.stop()
            if hasattr(self, 'deal_consumer') and self.deal_consumer:
                self.deal_consumer.stop()
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


    def _install_forwarders(self):
        """生成式转发：由 _FORWARD_TABLE 驱动，动态绑定聚合转发方法。"""
        install_forwarders(type(self))

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

                # ---- 同城信息队列消费者 ----
                try:
                    self.deal_consumer.check()
                except Exception as e:
                    log(level="ERROR", message=f"同城信息消费者模块出错：{e}")

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


# ========================================================================
# 生成式转发表：WXBot 对外暴露的聚合转发（组合 > 手抄）
# 新 core 方法只需在对应聚合对象下登记一行，勿手抄转发方法。
# ========================================================================
_FORWARD_TABLE = {
    "chatlog_manager": [
        "_convert_chatlog_msg",
        "_enrich_context_with_chatlog",
        "_init_chatlog_client",
        "chatlog_listen_loop",
        "chatlog_process_message",
        "refresh_chatlog_contacts",
    ],
    "command_handler": [
        "_build_status_msg",
        "handle_add_group",
        "handle_add_user",
        "handle_change_prompt",
        "handle_change_welcome_msg",
        "handle_clear_all_memory",
        "handle_clear_memory",
        "handle_clear_user_memory",
        "handle_disable_group_bot",
        "handle_disable_welcome_msg",
        "handle_enable_group_bot",
        "handle_enable_welcome_msg",
        "handle_group_switch_status",
        "handle_image_recognition_status",
        "handle_list_api_configs",
        "handle_list_prompts",
        "handle_new_friend_status",
        "handle_remove_group",
        "handle_remove_user",
        "handle_select_api_config",
        "handle_split_reply_status",
        "handle_switch_prompt",
        "handle_welcome_msg_status",
        "process_command",
        "send_command_list",
    ],
    "listen_manager": [
        "ALLListen_mode",
        "_get_all_subwindow_names",
        "_get_verified_subwindow",
        "_is_contact_in_listen_list",
        "_listen_add_error",
        "_try_get_all_subwindow_names",
        "add_chat_to_listen",
        "check_wechat_window",
        "init_wx_listeners",
        "is_chat_listened",
        "listen_mode",
        "new_msg_get_plus",
        "next_message_handle",
    ],
    "message_handler": [
        "_build_split_prompt",
        "_chatlog_send_ai",
        "_check_chat_max_round_limit",
        "_clean_reply_for_send",
        "_get_chat_max_round",
        "_get_chat_prompt",
        "_get_group_api",
        "_get_group_prompt",
        "_get_reply_count_key",
        "_handle_custom_forward",
        "_is_custom_forward_source",
        "_parse_split_reply",
        "message_handle_callback",
        "process_message",
        "wx_send_ai",
    ],
    "wx_utils": [
        "Pass_New_Friends",
        "_check_random_moments",
        "_check_random_msg",
        "_do_moments_like",
        "_remark_unit_len",
        "_truncate_remark_units",
        "build_new_friend_remark",
        "find_new_group_friend",
        "is_image_path",
        "send_group_welcome_msg",
        "send_scheduled_moments",
        "send_scheduled_msg",
    ],
}


def _make_forwarder(agg_attr, name):
    def _forward(self, *args, **kwargs):
        return getattr(getattr(self, agg_attr), name)(*args, **kwargs)
    _forward.__name__ = name
    _forward.__qualname__ = "WXBot.%s" % name
    _forward.__doc__ = "%s（生成式转发：委托给 self.%s.%s，由 _FORWARD_TABLE 自动生成）" % (name, agg_attr, name)
    return _forward


def install_forwarders(cls):
    for agg_attr, names in _FORWARD_TABLE.items():
        for name in names:
            setattr(cls, name, _make_forwarder(agg_attr, name))


if __name__ == "__main__":
    bot = WXBot()
    bot.run()

