import os
import sys
import json
import time
import uuid

from logger import log
from core.utils import (
    now_time,
    split_long_text,
    _normalize_chat_max_round_map,
    _coerce_int_range,
    human_delay,
    get_run_time,
)


class WXBotConfig:
    """
    微信机器人配置类
    负责从 config.json 中加载、保存、刷新配置，
    以及对监听用户列表、群组列表等进行增删管理。
    """

    def __init__(self):
        _base = os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
        self.CONFIG_FILE = os.path.join(_base, 'config', 'config.json')
        self.prompt_dir  = os.path.join(_base, 'config', 'prompt')
        os.makedirs(os.path.join(_base, 'config'), exist_ok=True)
        self.config = {}

        # ---------- 全局监听开关 ----------
        self.AllListen_switch = False   # True=黑名单模式，False=白名单模式
        self.chat_listen_only = False    # 私聊只监听不 AI 回复

        # ---------- 用户与权限 ----------
        self.listen_list = []           # 白名单/黑名单用户列表
        self.cmd = ""                   # 管理员账号（命令接收者）

        # ---------- AI 接口配置 ----------
        self.api_configs = []           # 接口配置列表，每项含 sdk/key/url/model
        self.api_index = 0              # 当前使用的接口索引
        self.api_sdk  = ""             # 当前接口 SDK（派生）
        self.api_key  = ""             # 当前接口 Key（派生）
        self.base_url = ""             # 当前接口 URL（派生）
        self.model1   = ""             # 当前接口模型（派生，供 AI 类使用）
        self.prompt   = ""             # AI 系统提示词
        self.AtMe     = ""             # 机器人被 @ 的标识（如 "@机器人昵称"）

        # ---------- 群聊配置 ----------
        self.group = []                 # 监听的群聊列表
        self.group_api_map = {}         # 群聊专属接口映射 {群名: api_index}
        self.group_switch = False       # 群机器人总开关
        self.group_listen_only = False   # 群聊只监听不 AI 回复
        self.group_reply_at = False     # 群聊是否仅在被 @ 时才回复
        self.group_welcome = False      # 群新人欢迎语开关
        self.group_welcome_random = 1.0 # 群新人欢迎语触发概率（0.0~1.0）
        self.group_welcome_msg = "欢迎新朋友！请先查看群公告！本消息自动发送!"

        # ---------- 新好友配置 ----------
        self.new_frined_switch = False        # 自动通过新好友开关
        self.new_frien_reply_switch = False   # 新好友自动回复开关
        self.new_frien_msg = []               # 通过后自动发送的打招呼消息列表
        self.new_friend_remark_use_nickname = True
        self.new_friend_remark_prefix_timestamp = False
        self.new_friend_remark_suffix_timestamp = False

        # ---------- 关键词回复配置 ----------
        self.chat_keyword_switch = False    # 私聊关键词回复开关
        self.group_keyword_switch = False   # 群聊关键词回复开关
        self.group_keyword_at_only = False  # 群聊关键词仅被@时触发
        self.keyword_dict = {}              # 关键词 -> 回复内容 字典

        # ---------- 自定义转发配置 ----------
        self.custom_forward_switch = False  # 自定义转发总开关
        self.custom_forward_list   = []     # 自定义转发规则列表

        # ---------- 多 Prompt 配置 ----------
        self.default_prompt   = "默认"      # 全局/fallback prompt 文件名（不含 .md）
        self.chat_prompt_map  = {}          # 私聊白名单用户 -> prompt 名称
        self.chat_api_map     = {}          # 私聊白名单用户 -> API 接口索引
        self.chat_max_round_map = {}        # 私聊白名单用户 -> 专属回复轮数上限
        self.group_prompt_map = {}          # 群组名称 -> prompt 名称

        # ---------- 定时消息配置 ----------
        self.scheduled_msg_switch = False    # 定时消息总开关
        self.scheduled_msg_list = []         # 定时消息任务列表

        # ---------- 随机定时消息配置 ----------
        self.random_msg_switch = False  # 随机定时消息总开关
        self.random_msg_list   = []     # 随机定时消息任务列表

        # ---------- 定时朋友圈配置 ----------
        self.scheduled_moments_switch = False  # 定时朋友圈总开关
        self.scheduled_moments_list = []       # 定时朋友圈任务列表

        # ---------- 随机朋友圈点赞配置 ----------
        self.moments_like_switch = False  # 随机点赞总开关
        self.moments_like_min    = 60     # 随机间隔最小分钟数
        self.moments_like_max    = 120    # 随机间隔最大分钟数

        # ---------- 随机定时朋友圈配置 ----------
        self.random_moments_switch = False  # 随机定时朋友圈总开关
        self.random_moments_list   = []     # 随机定时朋友圈任务列表

        # ---------- 对话记忆配置 ----------
        self.memory_switch        = True      # 记忆开关（默认开启）
        self.memory_max_count     = 3000     # 单窗口最多存储条数（上限 5000）
        self.memory_context_count = 1000     # AI 请求时带入条数

        # ---------- 发送延迟配置 ----------
        self.reply_delay_switch = True  # 模拟人工操作延迟开关（默认开启）
        self.reply_delay_min    = 1     # 最小延迟秒数
        self.reply_delay_max    = 5     # 最大延迟秒数
        self.clean_ai_reply_switch = True  # AI 回复清洗开关

        # ---------- Chatlog 配置 ----------
        self.chatlog_url = 'http://127.0.0.1:5030'                     # Chatlog 服务 URL
        self.chatlog_listen_switch = False                             # Chatlog 监听模式开关
        self.chatlog_context_switch = False                            # Chatlog 上下文增强开关
        self.chatlog_contact_lookup_switch = False                     # Chatlog 联系人查询开关
        self.chatlog_polling_interval = 10*60                           # Chatlog 轮询间隔（秒）
        self.chatlog_context_count = 20                                # Chatlog 上下文拉取条数
        self.chatlog_request_timeout = 5                               # Chatlog 请求超时时间（秒）

        # ---------- 消息存储配置 ----------
        self.chat_reply_confirm_switch = False                         # 私聊回复确认开关
        self.chat_reply_confirm_wait_timeout = 300                     # 确认等待超时时间（秒）
        self.message_store_max_count = 1000                            # 单会话最大存储消息数

        # ---------- 微信界面操作锁配置 ----------
        self.wx_lock_enabled = True                                    # 微信界面操作锁开关
        self.wx_lock_timeout = 300                                     # 锁自动超时时间（秒）

        # 初始化时自动加载配置并同步到属性
        self.load_config()
        self.update_global_config()

    # ----------------------------------------------------------
    # 配置文件读写
    # ----------------------------------------------------------

    def load_config(self):
        """从 config.json 加载配置到 self.config 字典"""
        # 若配置文件不存在，先创建默认配置
        if not os.path.exists(self.CONFIG_FILE):
            self.create_new_config_file()
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as file:
                self.config = json.load(file)
                log(message="配置文件加载成功")
        except Exception as e:
            log(level="ERROR", message="打开配置文件失败，请检查配置文件！" + str(e))
            # 配置文件损坏或缺失时阻塞程序，避免带着错误配置继续运行
            while True:
                time.sleep(100)

    def create_new_config_file(self):
        """若配置文件不存在，则创建一份包含默认值的配置文件"""
        try:
            if not os.path.exists(self.CONFIG_FILE):
                base_config = {
                    "api_configs": [
                        {"sdk": "", "key": "", "url": "", "model": ""},
                        {"sdk": "", "key": "", "url": "", "model": ""},
                    ],
                    "api_index": 0,
                    "prompt": "你是一个ai回复助手，请根据用户的问题给出回答,回复尽量保持在30字以内",
                    "admin": "文件传输助手",
                    "AllListen_switch": False,
                    "AllListen_filter_mute": True,
                    "chat_listen_only": False,
                    "listen_list": [],
                    "group": [],
                    "group_api_map": {},
                    "group_switch": False,
                    "group_listen_only": False,
                    "group_reply_at": False,
                    "group_reply_at_msg": True,
                    "group_reply_quote": False,
                    "group_welcome": False,
                    "group_welcome_random": 1.0,
                    "group_welcome_msg": "欢迎新朋友！请先查看群公告！",
                    "new_friend_switch": False,
                    "new_friend_reply_switch": False,
                    "new_friend_msg": [],
                    "new_friend_check_min": 60,
                    "new_friend_check_max": 300,
                    "new_friend_remark_use_nickname": True,
                    "new_friend_remark_prefix": "",
                    "new_friend_remark_prefix_timestamp": False,
                    "new_friend_remark_suffix": "_机器人备注",
                    "new_friend_remark_suffix_timestamp": False,
                    "new_friend_tags": [],
                    "chat_keyword_switch": False,
                    "group_keyword_switch": False,
                    "group_keyword_at_only": False,
                    "keyword_dict": {},
                    "custom_forward_switch": False,
                    "custom_forward_list": [],
                    "default_prompt": "默认",
                    "chat_prompt_map": {},
                    "chat_api_map": {},
                    "chat_max_round_map": {},
                    "group_prompt_map": {},
                    "scheduled_msg_switch": False,
                    "scheduled_msg_list": [],
                    "random_msg_switch": False,
                    "random_msg_list": [],
                    "scheduled_moments_switch": False,
                    "scheduled_moments_list": [],
                    "moments_like_switch": False,
                    "moments_like_min": 60,
                    "moments_like_max": 120,
                    "random_moments_switch": False,
                    "random_moments_list": [],
                    "everyday_start_stop_bot_switch": False,
                    "everyday_start_bot_time": "08:00",
                    "everyday_stop_bot_time": "23:00",
                    "memory_switch": True,
                    "memory_max_count": 3000,
                    "memory_context_count": 1000,
                    "reply_delay_switch": True,
                    "reply_delay_min": 1,
                    "reply_delay_max": 5,
                    "clean_ai_reply_switch": True,
                    "chat_image_recognition_switch": False,
                    "chat_image_recognition_api": 0,
                    "group_image_recognition_switch": False,
                    "group_image_recognition_api": 0,
                    "api_error_reply": "在忙，我稍后回复您",
                    "api_error_reply_once": False,
                    "chat_max_round_switch": False,
                    "chat_max_round_default": 99,
                    "chat_max_round_reset_days": 0,
                    "chat_max_round_reply": "",
                    "chat_max_round_reply_once": False,
                    "chat_split_reply_switch": False,
                    "chat_split_max_chars": 100,
                    "chat_split_max_count": 4,
                    "group_split_reply_switch": False,
                    "group_split_max_chars": 100,
                    "group_split_max_count": 4,
                    "siver_panel_enabled": False,
                    "siver_panel_activation_code": "",
                    "siver_panel_activation_code_applied_hash": "",
                    "siver_panel_activation_code_failed_hash": "",
                    "siver_panel_slug": "",
                    "siver_panel_install_id": "",
                    "siver_panel_machine_fingerprint": "",
                    "siver_panel_device_id": "",
                    "siver_panel_device_secret": "",
                    "siver_panel_base_url": "https://panel.siver.top",
                    "siver_panel_ws_url": "wss://panel.siver.top/relay/ws",
                    "siver_panel_panel_url": "",
                    "siver_panel_service_expire_at": "",
                    "siver_panel_last_error_code": "",
                    "siver_panel_last_error_message": "",
                    "chatlog_url": "http://127.0.0.1:5030",
                    "chatlog_listen_switch": False,
                    "chatlog_context_switch": False,
                    "chatlog_contact_lookup_switch": False,
                    "chatlog_polling_interval": 3,
                    "chatlog_context_count": 20,
                    "chatlog_request_timeout": 5,
                    "chatlog_reply_delay": 60,
                    "chat_reply_confirm_switch": False,
                    "chat_reply_confirm_wait_timeout": 300,
                    "message_store_max_count": 1000,
                    "wx_lock_enabled": True,
                    "wx_lock_timeout": 300,
                }
                with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(base_config, f, ensure_ascii=False, indent=4)
                log(message=f"已创建默认配置文件：\n{os.path.abspath(self.CONFIG_FILE)}\n请根据需求修改配置后重启")
        except Exception as e:
            log(level="ERROR", message="创建默认配置文件失败，请检查配置文件！" + str(e))
            while True:
                time.sleep(100)

    def save_config(self):
        """将当前 self.config 字典持久化写回 config.json"""
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as file:
                json.dump(self.config, file, ensure_ascii=False, indent=4)
        except Exception as e:
            log(level="ERROR", message="保存配置文件失败:" + str(e))

    def refresh_config(self):
        """重新加载配置文件，并将最新值同步到所有属性"""
        self.load_config()
        self.update_global_config()

    def init_prompt_dir(self):
        """确保 prompt 目录存在；迁移旧 prompt 字段；空目录时写入默认 prompt"""
        os.makedirs(self.prompt_dir, exist_ok=True)
        # 迁移旧 prompt 字段：先写文件，成功后才删字段并保存，防止写入失败时数据丢失
        if 'prompt' in self.config:
            target = os.path.join(self.prompt_dir, '默认.md')
            try:
                with open(target, 'w', encoding='utf-8') as f:
                    f.write(self.config['prompt'])
                del self.config['prompt']
                self.save_config()
                log(message="已将旧 prompt 字段迁移至 config/prompt/默认.md")
            except Exception as e:
                log(level="ERROR", message=f"迁移 prompt 到文件失败: {e}，旧 prompt 字段已保留")
        # 空目录兜底
        try:
            md_files = [f for f in os.listdir(self.prompt_dir) if f.endswith('.md')]
        except Exception:
            md_files = []
        if not md_files:
            try:
                with open(os.path.join(self.prompt_dir, '默认.md'), 'w', encoding='utf-8') as f:
                    f.write("你是一个ai回复助手，请根据用户的问题给出回答,回复尽量保持在30字以内")
            except Exception as e:
                log(level="ERROR", message=f"创建默认 prompt 文件失败: {e}")

    def get_prompt_content(self, name):
        """按名称读取 prompt 文件内容，找不到时 fallback 到 default_prompt，最终返回空字符串"""
        if not name:
            name = self.default_prompt
        path = os.path.join(self.prompt_dir, f'{name}.md')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        # fallback 到 default_prompt
        if name != self.default_prompt:
            fallback = os.path.join(self.prompt_dir, f'{self.default_prompt}.md')
            if os.path.exists(fallback):
                try:
                    with open(fallback, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception:
                    pass
        return ""

    # ----------------------------------------------------------
    # 配置同步：将 config 字典中的值同步到实例属性
    # ----------------------------------------------------------

    def update_global_config(self):
        """将 self.config 字典中的各配置项同步到对应实例属性"""
        # AI 接口列表（新格式）
        # 旧配置迁移：若 api_configs 不存在则从旧字段迁移并立即写回
        if 'api_configs' not in self.config and 'api_sdk' in self.config:
            self.config['api_configs'] = [
                {
                    'sdk':   self.config.get('api_sdk', ''),
                    'key':   self.config.get('api_key', ''),
                    'url':   self.config.get('base_url', ''),
                    'model': self.config.get('model1', ''),
                },
                {
                    'sdk':   self.config.get('api_sdk', ''),
                    'key':   self.config.get('api_key', ''),
                    'url':   self.config.get('base_url', ''),
                    'model': self.config.get('model2', ''),
                },
            ]
            self.config['api_index'] = 0
            for old_key in ('api_sdk', 'api_key', 'base_url', 'model1', 'model2', 'api_sdk_list'):
                self.config.pop(old_key, None)
            self.save_config()
            log(message="旧 API 配置已自动迁移为新格式并保存")

        self.api_configs = self.config.get('api_configs', [
            {"sdk": "", "key": "", "url": "", "model": ""},
            {"sdk": "", "key": "", "url": "", "model": ""},
        ])
        self.api_index = self.config.get('api_index', 0)
        if self.api_index >= len(self.api_configs):
            self.api_index = 0

        # 从当前接口配置派生兼容属性（供 AI 接口类使用）
        _cur = self.api_configs[self.api_index] if self.api_configs else {}
        self.api_sdk  = _cur.get('sdk', '')
        self.api_key  = _cur.get('key', '')
        self.base_url = _cur.get('url', '')
        self.model1   = _cur.get('model', '')
        self.prompt   = self.config.get('prompt', "")

        # 微信基础配置
        self.cmd            = self.config.get('admin', "")
        self.listen_list          = self.config.get('listen_list', [])
        self.AllListen_switch     = self.config.get('AllListen_switch')
        self.AllListen_filter_mute = bool(self.config.get('AllListen_filter_mute', True))
        self.chat_listen_only     = bool(self.config.get('chat_listen_only', False))

        # 群聊配置
        self.group                = self.config.get('group', [])
        self.group_api_map        = self.config.get('group_api_map', {})
        self.group_switch         = self.config.get('group_switch')
        self.group_listen_only    = bool(self.config.get('group_listen_only', False))
        self.group_reply_at       = self.config.get('group_reply_at')
        self.group_reply_at_msg   = bool(self.config.get('group_reply_at_msg', True))
        self.group_reply_quote    = bool(self.config.get('group_reply_quote', False))
        self.group_welcome        = self.config.get('group_welcome')
        self.group_welcome_random = self.config.get('group_welcome_random')
        self.group_welcome_msg    = self.config.get('group_welcome_msg', '')

        # 新好友配置
        self.new_frined_switch       = self.config.get('new_friend_switch')
        self.new_frien_reply_switch  = self.config.get('new_friend_reply_switch', False)
        self.new_frien_msg           = self.config.get('new_friend_msg', [])
        self.new_friend_check_min    = max(60, int(self.config.get('new_friend_check_min', 60)))
        self.new_friend_check_max    = min(3600, max(self.new_friend_check_min, int(self.config.get('new_friend_check_max', 300))))
        self.new_friend_remark_use_nickname = bool(self.config.get('new_friend_remark_use_nickname', True))
        self.new_friend_remark_prefix = self.config.get('new_friend_remark_prefix', '')
        self.new_friend_remark_prefix_timestamp = bool(self.config.get('new_friend_remark_prefix_timestamp', False))
        self.new_friend_remark_suffix = self.config.get('new_friend_remark_suffix', '_机器人备注')
        self.new_friend_remark_suffix_timestamp = bool(self.config.get('new_friend_remark_suffix_timestamp', False))
        self.new_friend_tags         = self.config.get('new_friend_tags', [])

        # 关键词配置
        self.chat_keyword_switch   = self.config.get('chat_keyword_switch')
        self.group_keyword_switch  = self.config.get('group_keyword_switch')
        self.group_keyword_at_only = self.config.get('group_keyword_at_only', False)
        self.keyword_dict          = self.config.get('keyword_dict', {})

        # 定时消息配置
        self.scheduled_msg_switch = self.config.get('scheduled_msg_switch',
                                                     self.config.get('everyday_msg_switch', False))
        self.scheduled_msg_list   = self.config.get('scheduled_msg_list', [])

        # 随机定时消息配置
        self.random_msg_switch = self.config.get('random_msg_switch', False)
        self.random_msg_list   = self.config.get('random_msg_list', [])

        # 定时朋友圈配置
        self.scheduled_moments_switch = self.config.get('scheduled_moments_switch', False)
        self.scheduled_moments_list   = self.config.get('scheduled_moments_list', [])

        # 随机朋友圈点赞配置
        self.moments_like_switch = self.config.get('moments_like_switch', False)
        self.moments_like_min    = max(1,    int(self.config.get('moments_like_min', 60)))
        self.moments_like_max    = max(self.moments_like_min, int(self.config.get('moments_like_max', 120)))

        # 随机定时朋友圈配置
        self.random_moments_switch = self.config.get('random_moments_switch', False)
        self.random_moments_list   = self.config.get('random_moments_list', [])

        # 旧配置自动迁移：everyday_msg_dict -> scheduled_msg_list
        if not self.scheduled_msg_list and self.config.get('everyday_msg_dict'):
            for target, tasks in self.config.get('everyday_msg_dict', {}).items():
                for task in tasks:
                    self.scheduled_msg_list.append({
                        'id': str(uuid.uuid4())[:8],
                        'enabled': True,
                        'targets': [target],
                        'time': task.get('time', '08:00'),
                        'repeat_type': 'daily',
                        'weekdays': [],
                        'dates': [],
                        'msgs': task.get('msgs', []),
                    })

        # 旧配置自动迁移：target(str) -> targets(list)
        _target_migrated = False
        for task in self.scheduled_msg_list:
            if 'targets' not in task:
                old = task.pop('target', '')
                task['targets'] = [old] if old else []
                _target_migrated = True
        if _target_migrated:
            self.config['scheduled_msg_list'] = self.scheduled_msg_list
            self.save_config()
            log(message="已自动迁移定时消息发送目标格式 target -> targets 并写回配置文件")

        # 对话记忆配置
        self.memory_switch        = self.config.get('memory_switch', True)
        self.memory_max_count     = int(self.config.get('memory_max_count', 3000))
        self.memory_context_count = int(self.config.get('memory_context_count', 1000))

        # 发送延迟配置（若旧配置文件中不存在则自动补写默认值）
        _delay_defaults = {'reply_delay_switch': True, 'reply_delay_min': 1, 'reply_delay_max': 5}
        _needs_save = any(k not in self.config for k in _delay_defaults)
        for k, v in _delay_defaults.items():
            self.config.setdefault(k, v)
        if _needs_save:
            self.save_config()
            log(message="已自动补充发送延迟配置默认值并写回配置文件")
        self.reply_delay_switch = bool(self.config.get('reply_delay_switch', True))
        self.reply_delay_min    = max(1, int(self.config.get('reply_delay_min', 1)))
        self.reply_delay_max    = max(1, int(self.config.get('reply_delay_max', 5)))
        self.clean_ai_reply_switch = bool(self.config.get('clean_ai_reply_switch', True))

        # 图片识别配置
        self.chat_image_recognition_switch  = bool(self.config.get('chat_image_recognition_switch', False))
        self.chat_image_recognition_api     = int(self.config.get('chat_image_recognition_api', 0))
        self.group_image_recognition_switch = bool(self.config.get('group_image_recognition_switch', False))
        self.group_image_recognition_api    = int(self.config.get('group_image_recognition_api', 0))

        # 自定义转发配置
        self.custom_forward_switch = bool(self.config.get('custom_forward_switch', False))
        self.custom_forward_list   = self.config.get('custom_forward_list', [])

        # 多 Prompt 配置
        self.default_prompt   = self.config.get('default_prompt', '默认')
        self.chat_prompt_map  = self.config.get('chat_prompt_map', {})
        self.chat_api_map     = self.config.get('chat_api_map', {})
        self.chat_max_round_map = self._normalize_chat_max_round_map(
            self.config.get('chat_max_round_map', {})
        )
        self.group_prompt_map = self.config.get('group_prompt_map', {})
        self.init_prompt_dir()

        # 接口调用失败时的固定回复
        self.api_error_reply = self.config.get('api_error_reply', '在忙，我稍后回复您')
        self.api_error_reply_once = bool(self.config.get('api_error_reply_once', False))

        # 单用户最大回复轮数限制配置
        self.chat_max_round_switch = bool(self.config.get('chat_max_round_switch', False))
        self.chat_max_round_default = self._coerce_int_range(self.config.get('chat_max_round_default', 99), 99, 1, 99999)
        self.chat_max_round_reset_days = self._coerce_int_range(self.config.get('chat_max_round_reset_days', 0), 0, 0, 365)
        self.chat_max_round_reply = self.config.get('chat_max_round_reply', '')
        self.chat_max_round_reply_once = bool(self.config.get('chat_max_round_reply_once', False))

        # 拆分多条回复配置
        self.chat_split_reply_switch  = bool(self.config.get('chat_split_reply_switch', False))
        self.chat_split_max_chars     = max(1, int(self.config.get('chat_split_max_chars', 100)))
        self.chat_split_max_count     = max(1, int(self.config.get('chat_split_max_count', 4)))
        self.group_split_reply_switch = bool(self.config.get('group_split_reply_switch', False))
        self.group_split_max_chars    = max(1, int(self.config.get('group_split_max_chars', 100)))
        self.group_split_max_count    = max(1, int(self.config.get('group_split_max_count', 4)))
        _siver_panel_defaults = {
            'siver_panel_enabled': False,
            'siver_panel_activation_code': '',
            'siver_panel_slug': '',
            'siver_panel_install_id': '',
            'siver_panel_machine_fingerprint': '',
            'siver_panel_device_id': '',
            'siver_panel_device_secret': '',
            'siver_panel_base_url': 'https://panel.siver.top',
            'siver_panel_ws_url': 'wss://panel.siver.top/relay/ws',
            'siver_panel_panel_url': '',
            'siver_panel_service_expire_at': '',
            'siver_panel_last_error_code': '',
            'siver_panel_last_error_message': '',
        }
        _siver_panel_needs_save = any(k not in self.config for k in _siver_panel_defaults)
        if self.config.get('siver_panel_base_url') == 'https://wxbot-panel.siverking.online':
            self.config['siver_panel_base_url'] = 'https://panel.siver.top'
            _siver_panel_needs_save = True
        if self.config.get('siver_panel_ws_url') == 'wss://wxbot-panel.siverking.online/relay/ws':
            self.config['siver_panel_ws_url'] = 'wss://panel.siver.top/relay/ws'
            _siver_panel_needs_save = True
        for k, v in _siver_panel_defaults.items():
            self.config.setdefault(k, v)
        if _siver_panel_needs_save:
            self.save_config()
            log(message='已自动补充 SiverPanel 远程访问配置默认值')

        # Chatlog 配置
        _chatlog_defaults = {
            'chatlog_url': 'http://127.0.0.1:5030',
            'chatlog_listen_switch': False,
            'chatlog_context_switch': False,
            'chatlog_contact_lookup_switch': False,
            'chatlog_polling_interval': 3,
            'chatlog_context_count': 20,
            'chatlog_request_timeout': 5,
            'chatlog_reply_delay': 0,
        }
        _chatlog_needs_save = any(k not in self.config for k in _chatlog_defaults)
        for k, v in _chatlog_defaults.items():
            self.config.setdefault(k, v)
        if _chatlog_needs_save:
            self.save_config()
            log(message='已自动补充 Chatlog 配置默认值')
        self.chatlog_url = self.config.get('chatlog_url', 'http://127.0.0.1:5030')
        self.chatlog_listen_switch = bool(self.config.get('chatlog_listen_switch', False))
        self.chatlog_context_switch = bool(self.config.get('chatlog_context_switch', False))
        self.chatlog_contact_lookup_switch = bool(self.config.get('chatlog_contact_lookup_switch', False))
        self.chatlog_polling_interval = max(1, int(self.config.get('chatlog_polling_interval', 3)))
        self.chatlog_context_count = max(1, int(self.config.get('chatlog_context_count', 20)))
        self.chatlog_request_timeout = max(1, int(self.config.get('chatlog_request_timeout', 5)))
        self.chatlog_reply_delay = int(self.config.get('chatlog_reply_delay', 0))

        # 消息存储配置
        self.chat_reply_confirm_switch = bool(self.config.get('chat_reply_confirm_switch', False))
        self.chat_reply_confirm_wait_timeout = max(60, int(self.config.get('chat_reply_confirm_wait_timeout', 300)))
        self.message_store_max_count = max(100, int(self.config.get('message_store_max_count', 1000)))

        # 微信界面操作锁配置
        self.wx_lock_enabled = bool(self.config.get('wx_lock_enabled', True))
        self.wx_lock_timeout = max(30, int(self.config.get('wx_lock_timeout', 300)))

        log(message="全局配置更新完成")

    def set_config(self, id, new_content):
        """修改指定配置项并保存"""
        self.config[id] = new_content
        self.save_config()
        self.refresh_config()
        log(message=id + "已更改为:" + str(self.config[id]))

    # ----------------------------------------------------------
    # 监听用户管理
    # ----------------------------------------------------------

    def add_user(self, name):
        """将用户添加到监听列表（白名单/黑名单）"""
        if name not in self.config.get('listen_list', []):
            self.config['listen_list'].append(name)
            self.save_config()
            self.refresh_config()
            log(message="添加后的监听用户列表:" + str(self.config['listen_list']))
        else:
            log(message=f"用户 {name} 已在监听列表中")

    def remove_user(self, name):
        """从监听列表中删除指定用户"""
        if name in self.listen_list:
            self.config['listen_list'].remove(name)
            self.save_config()
            self.refresh_config()
            log(message="删除后的监听用户列表:" + str(self.config['listen_list']))
        else:
            log(message=f"用户 {name} 不在监听列表中")

    # ----------------------------------------------------------
    # 监听群组管理
    # ----------------------------------------------------------

    def add_group(self, name):
        """将群组添加到监听列表"""
        if name not in self.config.get('group', []):
            self.config['group'].append(name)
            self.save_config()
            self.refresh_config()
            log(message="添加后的监听群组列表:" + str(self.config['group']))
        else:
            log(message=f"群组 {name} 已在监听列表中")

    def remove_group(self, name):
        """从监听列表中删除指定群组"""
        if name in self.config.get('group', []):
            self.config['group'].remove(name)
            self.save_config()
            self.refresh_config()
            log(message="删除后的监听群组列表:" + str(self.config['group']))
        else:
            log(message=f"群组 {name} 不在监听列表中")

    def set_group_switch(self, switch_value):
        """设置群机器人总开关"""
        self.config['group_switch'] = switch_value
        self.save_config()
        self.refresh_config()
        log(message="群开关设置为" + str(self.config['group_switch']))

    # ----------------------------------------------------------
    # 工具方法（委托给 core.utils）
    # ----------------------------------------------------------

    @staticmethod
    def now_time(time_format="%Y/%m/%d %H:%M:%S "):
        """获取当前时间字符串（当前暂由公共 log 模块显示时间，此处返回空串）"""
        return now_time(time_format)

    @staticmethod
    def split_long_text(text, chunk_size=2000):
        """将超长文本按指定长度切分为列表，用于分段发送"""
        return split_long_text(text, chunk_size)

    @staticmethod
    def _normalize_chat_max_round_map(raw_map):
        """清洗私聊白名单用户的专属回复轮数上限配置"""
        return _normalize_chat_max_round_map(raw_map)

    @staticmethod
    def _coerce_int_range(value, default, min_value, max_value):
        """将配置值转为指定范围内的整数"""
        return _coerce_int_range(value, default, min_value, max_value)

    def human_delay(self):
        """模拟人工操作随机延迟。reply_delay_switch 关闭时直接跳过。"""
        human_delay(self.reply_delay_switch, self.reply_delay_min, self.reply_delay_max)

    @staticmethod
    def get_run_time(start_time):
        """计算并返回自 start_time 至今的运行时长，格式：X天X时X分X秒"""
        return get_run_time(start_time)
