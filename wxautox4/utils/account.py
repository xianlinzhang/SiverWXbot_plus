"""微信账号信息提取模块

该模块提供从微信进程中提取账号信息的功能，主要流程：
1. 获取微信进程打开的文件句柄
2. 查找数据库文件路径 (Msg\\Misc.db 或 db_storage\\session\\session.db)
3. 解析路径提取账号名和数据目录
4. 构建 Account 对象

支持微信4.x版本的数据目录结构。
"""

from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import os
import re
import psutil

from wxautox4.utils.win32 import GetAllWindows


@dataclass
class Account:
    """微信账号信息对象
    
    Attributes:
        wxid: 微信ID，如 wxid_mertt4k5z7j429_a847
        nickname: 微信昵称
        data_dir: 账号数据目录路径
        db_path: 数据库文件路径
        pid: 微信进程ID
        exe_path: 微信可执行文件路径
        status: 账号状态 (online/offline)
        version: 微信版本号
        platform: 平台类型
    """
    wxid: str = ""
    nickname: str = ""
    data_dir: str = ""
    db_path: str = ""
    pid: int = 0
    exe_path: str = ""
    status: str = ""
    version: str = ""
    platform: str = "windows"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __repr__(self):
        return f"<Account wxid='{self.wxid}', nickname='{self.nickname}', data_dir='{self.data_dir}'>"


def _get_wechat_processes() -> List[psutil.Process]:
    """获取所有微信进程
    
    支持多种微信进程名：wechat.exe, WeChatAppEx.exe, Weixin.exe, WeChat.exe
    
    Returns:
        List[psutil.Process]: 微信进程列表
    """
    processes = []
    wechat_names = {'wechat.exe', 'wechatappex.exe', 'weixin.exe'}
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if proc.name().lower() in wechat_names:
                processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return processes


def _extract_wxid_from_path(path: str) -> Optional[str]:
    """从路径中提取wxid
    
    Args:
        path: 文件或目录路径
        
    Returns:
        Optional[str]: wxid，提取失败返回None
    """
    wxid_pattern = re.search(r'(wxid_[a-zA-Z0-9_-]+)', path)
    if wxid_pattern:
        return wxid_pattern.group(1)
    return None


def _get_base_wxid(wxid: str) -> str:
    """获取基础wxid（去掉末尾的_xxx后缀）
    
    Args:
        wxid: 完整的wxid
        
    Returns:
        str: 基础wxid
    """
    wxid_match = re.match(r'(wxid_[a-zA-Z0-9_-]+)', wxid)
    if wxid_match:
        full_wxid = wxid_match.group(1)
        suffix_match = re.match(r'(wxid_[a-zA-Z0-9]+)_[a-f0-9]+$', full_wxid)
        if suffix_match:
            return suffix_match.group(1)
        return full_wxid
    return wxid


def _find_db_paths_from_open_files(proc: psutil.Process) -> List[str]:
    """从进程打开的文件中查找数据库文件路径
    
    Args:
        proc: 进程对象
        
    Returns:
        List[str]: 数据库文件路径列表
    """
    db_paths = []
    try:
        for open_file in proc.open_files():
            path = open_file.path
            if path.endswith('.db'):
                db_paths.append(path)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return db_paths


def _find_account_from_process_files(proc: psutil.Process) -> Optional[Account]:
    """从进程打开的文件中提取账号信息
    
    Args:
        proc: 进程对象
        
    Returns:
        Optional[Account]: Account对象，提取失败返回None
    """
    db_paths = _find_db_paths_from_open_files(proc)
    
    for db_path in db_paths:
        wxid = _extract_wxid_from_path(db_path)
        if wxid:
            account = Account(
                wxid=wxid,
                db_path=db_path,
                pid=proc.pid,
                exe_path=proc.exe()
            )
            
            data_dir_pattern = re.search(r'(.*?)[\\/](?:Msg|db_storage|login)', db_path)
            if data_dir_pattern:
                account.data_dir = data_dir_pattern.group(1)
            else:
                parts = db_path.split(os.sep)
                for i, part in enumerate(parts):
                    if part.startswith('wxid_'):
                        account.data_dir = os.sep.join(parts[:i + 1])
                        break
            
            if not account.data_dir:
                account.data_dir = os.path.dirname(db_path)
            
            account.status = "online"
            
            try:
                info = proc.as_dict(['name', 'exe', 'pid'])
                exe_path = info.get('exe', '')
                account.version = _get_wechat_version(exe_path)
            except Exception:
                pass
            
            return account
    
    return None


def _get_wechat_version(exe_path: str) -> str:
    """获取微信版本号
    
    Args:
        exe_path: 微信可执行文件路径
        
    Returns:
        str: 版本号，获取失败返回空字符串
    """
    if not exe_path or not os.path.exists(exe_path):
        return ""
    
    try:
        import win32api
        info = win32api.GetFileVersionInfo(exe_path, '\\')
        version = "{}.{}.{}.{}".format(
            win32api.HIWORD(info['FileVersionMS']),
            win32api.LOWORD(info['FileVersionMS']),
            win32api.HIWORD(info['FileVersionLS']),
            win32api.LOWORD(info['FileVersionLS'])
        )
        return version
    except Exception:
        return ""


def _find_accounts_from_chatlog() -> List[Account]:
    """从Documents\\chatlog目录查找账号信息
    
    Returns:
        List[Account]: Account对象列表
    """
    accounts = []
    documents_dir = os.path.join(os.environ.get('USERPROFILE', ''), 'Documents', 'chatlog')
    
    if not os.path.exists(documents_dir):
        return accounts
    
    try:
        entries = os.listdir(documents_dir)
        for entry in entries:
            entry_path = os.path.join(documents_dir, entry)
            if os.path.isdir(entry_path) and entry.startswith('wxid_'):
                wxid = _extract_wxid_from_path(entry)
                if wxid:
                    session_db_path = os.path.join(entry_path, 'db_storage', 'session', 'session.db')
                    
                    account = Account(
                        wxid=wxid,
                        data_dir=entry_path,
                        status="online"
                    )
                    
                    if os.path.exists(session_db_path):
                        account.db_path = session_db_path
                    else:
                        db_files = []
                        for root, dirs, files in os.walk(entry_path):
                            for f in files:
                                if f.endswith('.db'):
                                    db_files.append(os.path.join(root, f))
                        if db_files:
                            account.db_path = db_files[0]
                    
                    accounts.append(account)
    except Exception:
        pass
    
    return accounts


def _find_accounts_from_xwechat() -> List[Account]:
    """从xwechat目录查找账号信息
    
    Returns:
        List[Account]: Account对象列表
    """
    accounts = []
    appdata = os.environ.get('APPDATA', '')
    
    if not appdata:
        return accounts
    
    xwechat_dir = os.path.join(appdata, 'Tencent', 'xwechat', 'login')
    
    if not os.path.exists(xwechat_dir):
        return accounts
    
    try:
        entries = os.listdir(xwechat_dir)
        for entry in entries:
            if entry.startswith('wxid_'):
                login_data_dir = os.path.join(xwechat_dir, entry)
                if os.path.isdir(login_data_dir):
                    wxid = _extract_wxid_from_path(entry)
                    if wxid:
                        account = Account(
                            wxid=wxid,
                            data_dir=login_data_dir,
                            status="online"
                        )
                        
                        db_files = []
                        for root, dirs, files in os.walk(os.path.join(appdata, 'Tencent', 'xwechat')):
                            if entry in root:
                                for f in files:
                                    if f.endswith('.db'):
                                        db_files.append(os.path.join(root, f))
                        
                        if db_files:
                            account.db_path = db_files[0]
                        
                        accounts.append(account)
    except Exception:
        pass
    
    return accounts


def _find_accounts_from_custom_datadir() -> List[Account]:
    """从自定义数据目录查找账号信息
    
    扫描常见的微信数据目录位置：
    - E:\\xwechat_files\\wxid_xxx
    - D:\\xwechat_files\\wxid_xxx
    
    Returns:
        List[Account]: Account对象列表
    """
    accounts = []
    custom_paths = [
        'E:\\xwechat_files',
        'D:\\xwechat_files',
        'C:\\xwechat_files',
        os.path.join(os.environ.get('USERPROFILE', ''), 'xwechat_files'),
    ]
    
    for base_path in custom_paths:
        if not os.path.exists(base_path):
            continue
        
        try:
            entries = os.listdir(base_path)
            for entry in entries:
                entry_path = os.path.join(base_path, entry)
                if os.path.isdir(entry_path) and entry.startswith('wxid_'):
                    wxid = _extract_wxid_from_path(entry)
                    if wxid:
                        account = Account(
                            wxid=wxid,
                            data_dir=entry_path,
                            status="online"
                        )
                        
                        db_files = []
                        for root, dirs, files in os.walk(entry_path):
                            for f in files:
                                if f.endswith('.db'):
                                    db_files.append(os.path.join(root, f))
                        
                        if db_files:
                            account.db_path = db_files[0]
                        
                        accounts.append(account)
        except Exception:
            continue
    
    return accounts


def _get_wechat_window_titles() -> Dict[int, str]:
    """获取微信窗口标题（昵称）
    
    Returns:
        Dict[int, str]: PID到昵称的映射
    """
    pid_to_title = {}
    windows = GetAllWindows(classname='Qt51514QWindowIcon')
    
    for hwnd, clsname, title in windows:
        if title and title != '微信':
            try:
                import win32process
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                pid_to_title[pid] = title
            except Exception:
                continue
    
    return pid_to_title


def get_account_from_process(pid: int = None) -> Optional[Account]:
    """从微信进程提取账号信息
    
    主入口函数，按以下流程提取：
    1. 获取微信进程打开的文件句柄
    2. 查找数据库文件路径 (Msg\\Misc.db 或 db_storage\\session\\session.db)
    3. 解析路径提取账号名和数据目录
    4. 构建 Account 对象
    
    如果文件句柄枚举失败，会自动回退到遍历微信数据目录查找。
    
    Args:
        pid: 进程ID，不指定则自动查找微信进程
        
    Returns:
        Optional[Account]: Account对象，提取失败返回None
    """
    all_accounts = get_all_accounts()
    
    if pid is not None:
        for account in all_accounts:
            if account.pid == pid:
                return account
    
    return all_accounts[0] if all_accounts else None


def get_all_accounts() -> List[Account]:
    """获取所有微信账号信息
    
    返回去重后的账号列表，基于基础wxid进行去重。
    
    Returns:
        List[Account]: 所有账号列表
    """
    all_account_candidates = []
    seen_base_wxids = {}
    
    processes = _get_wechat_processes()
    
    for proc in processes:
        account = _find_account_from_process_files(proc)
        if account and account.wxid:
            all_account_candidates.append(account)
    
    chatlog_accounts = _find_accounts_from_chatlog()
    all_account_candidates.extend(chatlog_accounts)
    
    custom_accounts = _find_accounts_from_custom_datadir()
    all_account_candidates.extend(custom_accounts)
    
    xwechat_accounts = _find_accounts_from_xwechat()
    all_account_candidates.extend(xwechat_accounts)
    
    for account in all_account_candidates:
        if not account.wxid:
            continue
        
        base_wxid = _get_base_wxid(account.wxid)
        
        if base_wxid not in seen_base_wxids:
            seen_base_wxids[base_wxid] = account
        else:
            existing = seen_base_wxids[base_wxid]
            
            if account.data_dir and ('xwechat_files' in account.data_dir or os.path.dirname(account.data_dir) == 'E:\\xwechat_files'):
                seen_base_wxids[base_wxid] = account
            elif account.pid and not existing.pid:
                existing.pid = account.pid
                existing.exe_path = account.exe_path
                existing.version = account.version
            elif account.db_path and not existing.db_path:
                existing.db_path = account.db_path
    
    accounts = list(seen_base_wxids.values())
    
    pid_to_title = _get_wechat_window_titles()
    
    for proc in processes:
        try:
            open_files = [f.path for f in proc.open_files()]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            open_files = []
        
        proc_wxid_found = False
        
        for account in accounts:
            if account.wxid in str(account.data_dir):
                if not account.pid or 'WeChatAppEx' in account.exe_path:
                    account.pid = proc.pid
                    account.exe_path = proc.exe()
                    account.version = _get_wechat_version(proc.exe())
                    proc_wxid_found = True
                
                if account.pid in pid_to_title:
                    account.nickname = pid_to_title[account.pid]
                break
        
        if not proc_wxid_found and open_files:
            for account in accounts:
                for open_file in open_files:
                    if account.wxid in open_file and not account.pid:
                        account.pid = proc.pid
                        account.exe_path = proc.exe()
                        account.version = _get_wechat_version(proc.exe())
                        
                        if account.pid in pid_to_title:
                            account.nickname = pid_to_title[account.pid]
                        break
    
    return accounts


def get_account_from_datadir(data_dir: str) -> Optional[Account]:
    """从数据目录构建账号信息
    
    Args:
        data_dir: 数据目录路径
        
    Returns:
        Optional[Account]: Account对象，失败返回None
    """
    try:
        account = Account(data_dir=data_dir)
        
        wxid = _extract_wxid_from_path(data_dir)
        if wxid:
            account.wxid = wxid
        else:
            return None
        
        db_files = []
        for root, dirs, files in os.walk(data_dir):
            for f in files:
                if f.endswith('.db'):
                    db_files.append(os.path.join(root, f))
        if db_files:
            account.db_path = db_files[0]
        
        return account
    except Exception:
        return None