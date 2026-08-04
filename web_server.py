# /mnt/data/web_server.py
# ---------------------------------------------
# 机器人管理网页（含关键词与群欢迎概率扩展）
# ---------------------------------------------
"""
机器人管理网页
使用 Flask 框架开发，提供机器人控制、配置管理等功能

P2 structural-split：本文件收敛为「共享辅助函数/状态 + create_app() 工厂」。
全部路由已按域拆入 blueprints/（auth/config/prompt/bot/task/message/memory/contacts/system），
由 create_app() 在运行时惰性 import 并注册，杜绝循环 import。
"""
from flask import Flask, url_for
import json
import os
import shutil
import hashlib
import re
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import logging
from functools import wraps
import threading

from core.utils import clean_ai_reply_text
from wxbot_core import CozeAPI, DifyAPI, DusAPI, OpenAIAPI, WXBot, version as BOT_VERSION
from schema.coercers import (
    coerce_bool_fields,
    coerce_list_fields,
    coerce_float_fields,
    coerce_int_range_fields,
    coerce_dict_fields,
)
from logger import log
import logger
import webbrowser
import time
import socket
import email_send
import webhook_send
import ctypes
import pythoncom
import atexit
import importlib.util
import secrets
from collections import defaultdict, deque

# fix_paths.py
import sys

# ============================================================================
# 【域 1】初始化 / 路径 / 通用工具
# ============================================================================
def resource_path(relative_path):
    """ 获取资源的绝对路径（打包后指向 _MEIPASS，用于只读资源如 templates）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def base_dir():
    """获取运行时基础目录（打包后为 exe 所在目录，开发时为脚本所在目录）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")

# 配置参数
CONFIG_FILE = os.path.join(base_dir(), 'config', 'config.json')
ADMIN_FILE  = os.path.join(base_dir(), 'config', 'admin.json')
EMAIL_FILE  = os.path.join(base_dir(), 'config', 'email.txt')
WEBHOOK_FILE = os.path.join(base_dir(), 'config', 'webhook.json')
PROMPT_DIR  = os.path.join(base_dir(), 'config', 'prompt')
BACKUP_BASE = os.path.join(base_dir(), 'old_wxbot_config')
APP_SECRET_FILE = os.path.join(base_dir(), 'config', 'panel_secret.key')
SIVER_PANEL_BASE_URL = 'https://panel.siver.top'
SIVER_PANEL_WS_URL = 'wss://panel.siver.top/relay/ws'
LEGACY_SIVER_PANEL_BASE_URL = 'https://wxbot-panel.siverking.online'
LEGACY_SIVER_PANEL_WS_URL = 'wss://wxbot-panel.siverking.online/relay/ws'
DEFAULT_PROMPT_CONTENT = "你是一个ai回复助手，请根据用户的问题给出回答,回复尽量保持在30字以内"

# 启动时确保目录存在
os.makedirs(os.path.join(base_dir(), 'config'),      exist_ok=True)
os.makedirs(os.path.join(base_dir(), 'panel_logs'),  exist_ok=True)


def load_panel_secret_key():
    """读取或生成持久化 Flask 会话密钥。"""
    if os.path.exists(APP_SECRET_FILE):
        try:
            with open(APP_SECRET_FILE, 'r', encoding='utf-8') as f:
                secret = f.read().strip()
            if secret:
                return secret
        except Exception as e:
            log('WARNING', f'读取面板会话密钥失败，将重新生成: {e}')

    secret = secrets.token_urlsafe(64)
    try:
        with open(APP_SECRET_FILE, 'w', encoding='utf-8') as f:
            f.write(secret)
    except Exception as e:
        log('ERROR', f'写入面板会话密钥失败，当前会话将使用临时密钥: {e}')
    return secret


# ============================================================================
# 【域 2】鉴权 / 登录 / 安全 / siver-panel 远程门面（共享辅助）
# ============================================================================

def hash_password(password):
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)


def verify_password(password, password_hash):
    try:
        return check_password_hash(password_hash, password)
    except Exception:
        return False


def load_siver_panel_manager_class():
    module_path = resource_path('siver_panel.py')
    if not os.path.exists(module_path):
        log('WARNING', f'SiverPanel 客户端模块不存在: {module_path}')
        return None

    try:
        spec = importlib.util.spec_from_file_location('siver_panel_runtime', module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError('无法创建 SiverPanel 模块加载器')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manager_class = getattr(module, 'SiverPanelManager', None)
        if manager_class is None:
            raise RuntimeError('SiverPanelManager 未在模块中定义')
        return manager_class
    except Exception as e:
        log('ERROR', f'加载 SiverPanel 客户端模块失败: {e}')
        return None

def load_admin_credentials():
    """从 admin.json 读取账密，文件不存在时自动创建默认账密文件"""
    default_password = "123456"
    default = {"username": "admin", "password_hash": hash_password(default_password)}
    if not os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, 'w', encoding='utf-8') as f:
                json.dump(default, f, ensure_ascii=False, indent=4)
            log('WARNING', f'账密文件不存在，已创建默认账密文件: {ADMIN_FILE}，请及时修改密码')
        except Exception as e:
            log('ERROR', f'创建账密文件失败: {e}，使用默认账密')
        return default
    try:
        with open(ADMIN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        username = data.get("username", default["username"])
        password_hash = str(data.get("password_hash", "")).strip()
        plain_password = str(data.get("password", "")).strip()

        if plain_password and not password_hash:
            password_hash = hash_password(plain_password)
            with open(ADMIN_FILE, 'w', encoding='utf-8') as fw:
                json.dump({"username": username, "password_hash": password_hash}, fw, ensure_ascii=False, indent=4)
            log('WARNING', '检测到旧版明文密码配置，已自动迁移为哈希存储')

        if not password_hash:
            password_hash = default["password_hash"]

        return {
            "username": username,
            "password_hash": password_hash,
        }
    except Exception as e:
        log('ERROR', f'读取账密文件失败: {e}，使用默认账密')
        return default


# 用户认证信息（从 admin.json 加载）
USERS = load_admin_credentials()

LOGIN_FAIL_LIMIT = 8
LOGIN_FAIL_WINDOW_SEC = 15 * 60
LOGIN_BAN_SEC = 30 * 60
login_failures = defaultdict(deque)
login_bans = {}
panel_server_port = None
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "123456"
FORCE_ADMIN_CHANGE_ALLOWED_PATHS = {
    "/dashboard",
    "/logout",
    "/api/check_auth",
    "/get_admin_config",
    "/save_admin_config",
}


def get_client_ip():
    from flask import request
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP', '').strip()
    if real_ip:
        return real_ip
    return request.remote_addr or 'unknown'


def is_remote_panel_request():
    from flask import request
    if request.headers.get('X-Siver-Remote', '').strip() == '1':
        return True
    forwarded_prefix = request.headers.get('X-Forwarded-Prefix', '').strip()
    return forwarded_prefix.startswith('/panel/')


def is_default_admin_credentials():
    return (
        USERS.get("username") == DEFAULT_ADMIN_USERNAME
        and verify_password(DEFAULT_ADMIN_PASSWORD, USERS.get("password_hash", ""))
    )


def is_force_admin_change_required():
    from flask import session
    if not session.get('logged_in'):
        return False
    if not is_remote_panel_request():
        return False
    return is_default_admin_credentials()


def get_remote_connect_block_reason(*, manual: bool) -> 'tuple[str, str] | None':
    if not is_default_admin_credentials():
        return None
    message = '当前后台仍在使用默认账号密码 admin / 123456。为安全起见，请先在“账号密码”里修改后台账号密码后，再连接远程访问服务。'
    log('WARNING', message)
    return ('default_admin_credentials_block_remote_connect', message)


def is_remote_connect_block_required():
    config = read_config() or {}
    return bool(config.get('siver_panel_enabled') and is_default_admin_credentials())


def is_login_ip_banned(ip):
    expire_ts = login_bans.get(ip)
    if not expire_ts:
        return False, 0
    now = time.time()
    if expire_ts <= now:
        login_bans.pop(ip, None)
        return False, 0
    return True, int(expire_ts - now)


def record_login_failure(ip):
    now = time.time()
    bucket = login_failures[ip]
    while bucket and now - bucket[0] > LOGIN_FAIL_WINDOW_SEC:
        bucket.popleft()
    bucket.append(now)
    if len(bucket) >= LOGIN_FAIL_LIMIT:
        login_bans[ip] = now + LOGIN_BAN_SEC
        bucket.clear()
        return True
    return False


def clear_login_failures(ip):
    login_failures.pop(ip, None)
    login_bans.pop(ip, None)


def is_safe_redirect_target(target):
    from flask import request
    from urllib.parse import urljoin, urlparse
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def absolute_url_for(endpoint, **values):
    from flask import url_for
    return url_for(endpoint, _external=True, **values)


def apply_panel_security_headers(response):
    from flask import request
    session_cookie_name = response.http.request.headers.get('Cookie', '') if False else None
    cookies = response.headers.getlist('Set-Cookie')
    if request.is_secure and cookies:
        rewritten = []
        changed = False
        for cookie in cookies:
            if cookie.startswith('session=') and 'Secure' not in cookie:
                cookie = f'{cookie}; Secure'
                changed = True
            rewritten.append(cookie)
        if changed:
            del response.headers['Set-Cookie']
            for cookie in rewritten:
                response.headers.add('Set-Cookie', cookie)
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    return response


def get_panel_server_port():
    return panel_server_port


SIVER_PANEL_MANAGER_CLASS = load_siver_panel_manager_class()
siver_panel_manager = None
if SIVER_PANEL_MANAGER_CLASS is not None:
    try:
        siver_panel_manager = SIVER_PANEL_MANAGER_CLASS(
            config_path=CONFIG_FILE,
            client_version=BOT_VERSION,
            log_func=log,
        )
        siver_panel_manager.set_connect_guard(get_remote_connect_block_reason)
    except Exception as e:
        log('ERROR', f'初始化 SiverPanel 客户端失败: {e}')

if siver_panel_manager is not None:
    atexit.register(siver_panel_manager.shutdown)


# 日志颜色映射
LOG_COLORS = {
    'INFO': 'text-primary',
    'WARNING': 'text-warning',
    'ERROR': 'text-danger',
    'DEBUG': 'text-secondary',
    'SUCCESS': 'text-success'
}

log_messages = []


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, session, jsonify, redirect
        if not session.get('logged_in'):
            if request.path.startswith('/api/') or request.accept_mimetypes.accept_json:
                return jsonify({'status': 'error', 'message': '未登录'}), 401
            return redirect(absolute_url_for('auth.login', next=request.url))
        if is_force_admin_change_required() and request.path not in FORCE_ADMIN_CHANGE_ALLOWED_PATHS:
            message = '当前为远程访问，且仍在使用默认账号密码，请先修改后台账号密码后再继续使用'
            wants_json = (
                request.path.startswith('/api/')
                or request.accept_mimetypes.accept_json
                or request.headers.get('X-Requested-With', '') == 'XMLHttpRequest'
            )
            if wants_json:
                return jsonify({
                    'status': 'error',
                    'message': message,
                    'error_code': 'force_admin_credential_change_required',
                }), 403
            return redirect(absolute_url_for('auth.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def log_server(level, msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {
        'time': timestamp,
        'level': level,
        'message': msg,
        'color': LOG_COLORS.get(level.upper(), 'text-dark')
    }
    log_messages.append(log_entry)
    if len(log_messages) > 1000:
        log_messages.pop(0)
    print(f"[{timestamp}] [{level}] {msg}")


# ----------------------------------------------------------
# Prompt 文件管理辅助函数
# ----------------------------------------------------------

def _ensure_prompt_dir():
    os.makedirs(PROMPT_DIR, exist_ok=True)
    try:
        md_files = [f for f in os.listdir(PROMPT_DIR) if f.endswith('.md')]
    except Exception:
        md_files = []
    if not md_files:
        try:
            with open(os.path.join(PROMPT_DIR, '默认.md'), 'w', encoding='utf-8') as f:
                f.write(DEFAULT_PROMPT_CONTENT)
        except Exception as e:
            log('ERROR', f'创建默认 prompt 文件失败: {e}')


def _get_prompts_list():
    _ensure_prompt_dir()
    prompts = []
    try:
        for fname in os.listdir(PROMPT_DIR):
            if not fname.endswith('.md'):
                continue
            name = fname[:-3]
            try:
                with open(os.path.join(PROMPT_DIR, fname), 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                content = ''
            prompts.append({'name': name, 'content': content})
    except Exception as e:
        log('ERROR', f'扫描 prompt 目录失败: {e}')
    prompts.sort(key=lambda p: (0 if p['name'] == '默认' else 1, p['name']))
    return prompts


def _migrate_prompt_from_config(config):
    if 'prompt' not in config:
        return False
    os.makedirs(PROMPT_DIR, exist_ok=True)
    target = os.path.join(PROMPT_DIR, '默认.md')
    try:
        with open(target, 'w', encoding='utf-8') as f:
            f.write(config['prompt'])
        log('SUCCESS', '旧 prompt 字段已迁移至 config/prompt/默认.md')
        del config['prompt']
        return True
    except Exception as e:
        log('ERROR', f'迁移 prompt 文件失败: {e}，旧 prompt 字段已保留')
        return False


# ----------------------------------------------------------
# 数据备份辅助函数
# ----------------------------------------------------------

def _do_backup():
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    backup_dir = os.path.join(BACKUP_BASE, ts)
    os.makedirs(backup_dir, exist_ok=True)

    config_src = os.path.join(base_dir(), 'config')
    memory_src = os.path.join(base_dir(), 'memory')

    if os.path.exists(config_src):
        shutil.copytree(config_src, os.path.join(backup_dir, 'config'))
    if os.path.exists(memory_src):
        shutil.copytree(memory_src, os.path.join(backup_dir, 'memory'))

    version_marker = os.path.join(backup_dir, BOT_VERSION)
    try:
        open(version_marker, 'w').close()
    except Exception:
        pass

    log('SUCCESS', f'数据已备份至: {backup_dir}')
    return backup_dir


def _check_and_auto_backup():
    config_src = os.path.join(base_dir(), 'config')
    memory_src = os.path.join(base_dir(), 'memory')
    has_data = os.path.exists(config_src) or os.path.exists(memory_src)
    if not has_data:
        return

    if not os.path.exists(BACKUP_BASE):
        log('INFO', '首次检测到数据目录，自动备份中...')
        _do_backup()
        return

    try:
        backups = [
            d for d in os.listdir(BACKUP_BASE)
            if os.path.isdir(os.path.join(BACKUP_BASE, d))
            and len(d) == 14 and d.isdigit()
        ]
    except Exception:
        backups = []

    if not backups:
        log('INFO', '备份目录为空，执行首次自动备份...')
        _do_backup()
        return

    latest = max(backups)
    try:
        latest_dt = datetime.strptime(latest, '%Y%m%d%H%M%S')
        days_diff = (datetime.now() - latest_dt).days
    except Exception:
        days_diff = 999

    latest_path = os.path.join(BACKUP_BASE, latest)
    version_match = os.path.exists(os.path.join(latest_path, BOT_VERSION))

    if days_diff > 3:
        log('INFO', f'距上次备份已 {days_diff} 天（超过3天），自动备份中...')
        _do_backup()
    elif not version_match:
        try:
            old_ver_files = [f for f in os.listdir(latest_path)
                             if os.path.isfile(os.path.join(latest_path, f))
                             and f.startswith('V')]
            old_ver = old_ver_files[0] if old_ver_files else '未知版本'
        except Exception:
            old_ver = '未知版本'
        log('INFO', f'检测到版本变更（{old_ver} → {BOT_VERSION}），自动备份中...')
        _do_backup()


# ----------------------------------------------------------
# 【域 3】配置 读写 / 后端小配置（admin / email / webhook） / 备份
# ----------------------------------------------------------
def read_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log('ERROR', f'读取配置文件失败: {str(e)}')
        return None


def _parse_hhmm_config(value, field_name):
    """解析 `HH:MM` 格式的时间字段，非法时返回错误信息而不是抛异常。"""
    value = str(value or '').strip()
    if not value:
        return None, f'{field_name} 为空'
    try:
        parsed = datetime.strptime(value, "%H:%M")
        return (parsed.hour, parsed.minute), None
    except ValueError:
        return None, f'{field_name} 格式无效: {value}，应为 HH:MM'


# 保存配置文件
def save_config(config_data):
    try:
        original_config = read_config() or {}
        merged_config = {**original_config, **config_data}

        if 'api_configs' in merged_config:
            for _k in ('api_sdk', 'api_key', 'base_url', 'model1', 'model2', 'api_sdk_list'):
                merged_config.pop(_k, None)

        coerce_bool_fields(merged_config)
        coerce_list_fields(merged_config)
        coerce_float_fields(merged_config, original_config)
        coerce_int_range_fields(merged_config)
        coerce_dict_fields(merged_config)

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(merged_config, f, ensure_ascii=False, indent=4)
        log('SUCCESS', '配置文件保存成功')
        return True
    except Exception as e:
        log('ERROR', f'保存配置文件失败: {str(e)}')
        return False


#   保存配置（路由在 blueprints/config.py）
update_config_status = False


class _TempAPIConfig:
    """用于测试单个接口配置的轻量配置对象，不读写 config.json。"""

    def __init__(self, cfg):
        self.api_sdk = str(cfg.get('sdk', '')).strip()
        self.api_key = str(cfg.get('key', '')).strip()
        self.base_url = str(cfg.get('url', '')).strip().rstrip('/')
        self.model1 = str(cfg.get('model', '')).strip()
        self.prompt = "你是接口连通性测试助手。请只回复 OK。"
        self.app_type = str(cfg.get('app_type', 'chat')).strip() or 'chat'
        self.workflow_input_key = str(cfg.get('workflow_input_key', 'query')).strip() or 'query'
        self.workflow_output_key = str(cfg.get('workflow_output_key', 'text')).strip() or 'text'


def _build_test_api_client(tmp_config):
    sdk = tmp_config.api_sdk
    if sdk == "OpenAI SDK":
        return OpenAIAPI(tmp_config)
    if sdk == "Dify":
        return DifyAPI(tmp_config)
    if sdk == "Coze":
        return CozeAPI(tmp_config)
    if sdk == "DusAPI":
        return DusAPI(tmp_config)
    raise ValueError("不支持的 SDK 类型")


# 启动/停止机器人
bot = None
bot_thread = None

# ----------------------------------------------------------
# 【域 4】机器人 启停 / 授权 / 更新 / 状态 相关
# ----------------------------------------------------------

# 防锁屏 / 防睡眠工具函数（Windows SetThreadExecutionState）
_ES_CONTINUOUS       = 0x80000000
_ES_SYSTEM_REQUIRED  = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002


def _prevent_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
        )
        log('INFO', '【防锁屏】已阻止 Windows 自动锁屏/黑屏/睡眠，避免影响微信自动化操作')
    except Exception as e:
        log('WARNING', f'【防锁屏】设置防睡眠状态失败: {e}')


def _restore_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        log('INFO', '【防锁屏】已恢复 Windows 原有锁屏/黑屏/睡眠策略')
    except Exception as e:
        log('WARNING', f'【防锁屏】恢复睡眠策略失败: {e}')


atexit.register(_restore_sleep)


# ----------------------------------------------------------
# 【域 5】记忆 相关辅助（memory 管理）
# ----------------------------------------------------------
MEMORY_BASE = os.path.join(base_dir(), 'memory')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _memory_is_windows_reserved_name(name):
    stem = name.split('.', 1)[0].upper()
    return stem in WINDOWS_RESERVED_NAMES


def _memory_hash_storage_name(name):
    raw_name = str(name)
    return "hash" + hashlib.sha256(raw_name.encode('utf-8')).hexdigest()


def _memory_resolve_storage_name(chat_name):
    raw_name = str(chat_name)
    storage_name = INVALID_FILENAME_CHARS_RE.sub('', raw_name)
    storage_name = storage_name.strip().rstrip('. ')
    if (
        not storage_name
        or storage_name in ('.', '..')
        or _memory_is_windows_reserved_name(storage_name)
        or len(storage_name) > 120
    ):
        return _memory_hash_storage_name(raw_name)
    return storage_name


def _memory_read_original_name(chat_path, fallback):
    name_path = os.path.join(chat_path, 'name.json')
    if not os.path.exists(name_path):
        return fallback
    try:
        with open(name_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        name = data.get('name') if isinstance(data, dict) else None
        return str(name) if name else fallback
    except Exception:
        return fallback


def _memory_find_chat_dir(wx_path, chat_name):
    storage_name = _memory_resolve_storage_name(chat_name)
    direct_path = os.path.join(wx_path, storage_name)
    if os.path.isdir(direct_path):
        return storage_name, direct_path
    if not os.path.isdir(wx_path):
        return storage_name, direct_path
    for item in os.listdir(wx_path):
        item_path = os.path.join(wx_path, item)
        if os.path.isdir(item_path) and _memory_read_original_name(item_path, item) == chat_name:
            return item, item_path
    return storage_name, direct_path


def _safe_is_dir(parent_abs, name):
    if os.name == 'nt':
        p = '\\\\?\\' + parent_abs + '\\' + name
    else:
        p = os.path.join(parent_abs, name)
    try:
        import stat as _stat
        return _stat.S_ISDIR(os.stat(p).st_mode)
    except OSError:
        return False


# 文件选择互斥锁
_tk_lock = threading.Lock()


def time_start_stop():
    """定时启停"""
    def is_target_time(target_hour, target_minute):
        now = datetime.now()
        return (now.hour == target_hour) and (now.minute == target_minute)
    def load_time_schedule_config():
        time_config = read_config() or {}
        enabled = bool(time_config.get("everyday_start_stop_bot_switch"))
        if not enabled:
            return False, None, None
        start_time, start_err = _parse_hhmm_config(
            time_config.get("everyday_start_bot_time"), "everyday_start_bot_time",
        )
        stop_time, stop_err = _parse_hhmm_config(
            time_config.get("everyday_stop_bot_time"), "everyday_stop_bot_time",
        )
        errors = [err for err in (start_err, stop_err) if err]
        if errors:
            for err in errors:
                log('ERROR', f'定时启停配置校验失败: {err}')
            log('WARNING', '定时启停已临时禁用，本轮不会执行，请修正时间格式后重新保存配置')
            return False, None, None
        return True, start_time, stop_time
    def time_check_thread():
        global bot_thread, bot, update_config_status
        start_hour = start_minute = stop_hour = stop_minute = None
        everyday_start_stop_bot_switch, start_time, stop_time = load_time_schedule_config()
        if start_time:
            start_hour, start_minute = start_time
        if stop_time:
            stop_hour, stop_minute = stop_time
        if everyday_start_stop_bot_switch:
            log('INFO', f'启动定时启停线程，启动时间：{start_hour}:{start_minute}，停止时间：{stop_hour}:{stop_minute}')
        else:
            log('INFO', '定时启停未启用，未启用')

        while True:
            if update_config_status:
                update_config_status = False
                start_hour = start_minute = stop_hour = stop_minute = None
                everyday_start_stop_bot_switch, start_time, stop_time = load_time_schedule_config()
                if start_time:
                    start_hour, start_minute = start_time
                if stop_time:
                    stop_hour, stop_minute = stop_time
                if everyday_start_stop_bot_switch:
                    log('INFO', f'配置更新，启动定时启停线程，启动时间：{start_hour}:{start_minute}，停止时间：{stop_hour}:{stop_minute}')
                else:
                    log('INFO', '配置更新，定时启停未启用')
            if everyday_start_stop_bot_switch:
                if is_target_time(start_hour, start_minute):
                    log('INFO', '到达预定启动时间，正在启动机器人')
                    if bot_thread and bot_thread.is_alive():
                        log("WARNING", "状态：机器人已在运行")
                        log(message="定时启动机器人:机器人已在运行，无需启动")
                    else:
                        def run_bot():
                            pythoncom.CoInitialize()
                            global bot
                            if bot:
                                try:
                                    bot.stop()
                                    log('INFO', '已清理上次残留的 WeChat 监听')
                                except Exception as _e:
                                    log('WARNING', f'清理旧监听时出错（可忽略）: {_e}')
                            bot = WXBot()
                            bot.run()
                            _restore_sleep()
                            pythoncom.CoUninitialize()
                        try:
                            bot_thread = threading.Thread(target=run_bot, daemon=True)
                            bot_thread.start()
                            _prevent_sleep()
                            log(level='INFO', message="定时启动机器人:机器人已启动")
                        except Exception as e:
                            log('ERROR', f'启动机器人失败: {str(e)}')
                    time.sleep(60)
                if is_target_time(stop_hour, stop_minute):
                    log('INFO', '到达预定停止时间，正在停止机器人')
                    if bot_thread and bot_thread.is_alive():
                        if bot.stop_wxbot():
                            log('SUCCESS', '机器人已停止')
                            bot_thread = None
                            bot = None
                            _restore_sleep()
                            log(message="定时停止机器人:机器人已停止")
                        else:
                            log('ERROR', '停止机器人失败')
                    else:
                        log('WARNING', '状态：机器人未运行')
                        log(message="定时停止机器人:机器人未运行，无需停止")
                    time.sleep(60)
            time.sleep(10)

    time_thread = threading.Thread(target=time_check_thread, daemon=True)
    time_thread.start()


def find_free_port(start_port=10001, max_port=11000):
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("未找到可用端口")


def create_app():
    """构建 Flask app：惰性注册全部 blueprint，避免循环 import。"""
    from flask import Flask
    from werkzeug.middleware.proxy_fix import ProxyFix
    app = Flask(__name__, template_folder=resource_path('templates'), static_folder=resource_path('templates/static'))
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_proto=1, x_prefix=1)

    app.config.update(
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_HTTPONLY=False,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=1)
    )
    app.secret_key = load_panel_secret_key()

    app.after_request(apply_panel_security_headers)

    from blueprints import build_blueprints
    for bp in build_blueprints():
        app.register_blueprint(bp)

    return app


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.NullHandler()]
    )
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    log('INFO', '服务器启动中...')
    try:
        if not os.path.exists(CONFIG_FILE):
            default_config = {
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
                "moments_wait_mouse_idle_switch": True,
                "moments_mouse_idle_seconds": 2,
                "moments_mouse_max_wait_seconds": 60,
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
                "custom_forward_switch": False,
                "custom_forward_list": [],
                "default_prompt": "默认",
                "chat_prompt_map": {},
                "chat_api_map": {},
                "chat_max_round_map": {},
                "group_prompt_map": {},
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
                "siver_panel_base_url": SIVER_PANEL_BASE_URL,
                "siver_panel_ws_url": SIVER_PANEL_WS_URL,
                "siver_panel_panel_url": "",
                "siver_panel_service_expire_at": "",
                "siver_panel_last_error_code": "",
                "siver_panel_last_error_message": "",
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            log('WARNING', '配置文件不存在，已创建默认配置文件')
        log('INFO', '服务5s后启动')
        try:
            _check_and_auto_backup()
        except Exception as _backup_e:
            log('ERROR', f'自动备份检查失败: {_backup_e}')
        global panel_server_port
        free_port = find_free_port(10001, 11000)
        panel_server_port = free_port
        log('INFO', f'请访问 http://localhost:{free_port} 或 http://127.0.0.1:{free_port} 进行登录')
        webbrowser.open(f"http://127.0.0.1:{free_port}")
        time_start_stop()
        if siver_panel_manager is not None:
            siver_panel_manager.set_local_port_provider(get_panel_server_port)
            siver_panel_manager.start()
        app = create_app()
        app.run(host='0.0.0.0', port=free_port, debug=False, threaded=True)
    except Exception as e:
        log('ERROR', f'服务器启动失败: {str(e)}')
    finally:
        log('INFO', '服务器已停止')


# 兼容：模块级暴露 app（供既有测试/工具 `from web_server import app` 使用）
try:
    app = create_app()
except Exception:
    app = None


if __name__ == '__main__':
    main()