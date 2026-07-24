import threading
import time
from datetime import datetime
from logger import log


class WXLock:
    """
    微信界面操作锁管理类
    用于协调多个任务对微信界面的操作，避免并发操作导致混乱

    锁状态：
    - idle: 空闲，可获取
    - held: 已被占用
    - released: 已释放
    """

    def __init__(self, config=None):
        """
        初始化微信界面操作锁

        :param config: 配置对象，包含 wx_lock_timeout 和 wx_lock_enabled 配置项
        """
        self._lock = threading.Lock()           # 基础锁对象
        self._held = False                      # 是否被占用
        self._holder = None                     # 占用者标识
        self._hold_time = None                  # 占用开始时间
        
        if config is not None:
            self._lock_timeout = getattr(config, 'wx_lock_timeout', 300)   # 锁超时时间（秒）
            self._enabled = getattr(config, 'wx_lock_enabled', True)       # 锁机制开关
        else:
            self._lock_timeout = 300            # 锁超时时间（秒），默认5分钟
            self._enabled = True                # 锁机制开关

    def acquire(self, holder=None, timeout=None):
        """
        获取锁（阻塞等待直到获取）

        :param holder: 占用者标识，用于标识哪个任务占用了锁
        :param timeout: 超时时间（秒），None 表示无限等待
        :return: 是否成功获取锁
        """
        if not self._enabled:
            return True

        wait_start = time.time()
        while True:
            with self._lock:
                if not self._held:
                    self._held = True
                    self._holder = holder
                    self._hold_time = datetime.now()
                    log(message=f"微信界面锁已获取: {holder}")
                    return True

            if timeout is not None and (time.time() - wait_start) >= timeout:
                log(level="WARNING", message=f"获取微信界面锁超时: {holder}")
                return False

            time.sleep(0.1)

    def release(self, holder=None):
        """
        释放锁

        :param holder: 释放者标识，用于验证是否为锁持有者
        :return: 是否成功释放锁
        """
        if not self._enabled:
            return True

        with self._lock:
            if self._held:
                if holder is None or self._holder == holder:
                    held_duration = (datetime.now() - self._hold_time).total_seconds() if self._hold_time else 0
                    log(message=f"微信界面锁已释放: {self._holder}, 持有时间: {held_duration:.2f}秒")
                    self._held = False
                    self._holder = None
                    self._hold_time = None
                    return True
                else:
                    log(level="WARNING", message=f"释放微信界面锁失败: 持有者不匹配，当前持有者: {self._holder}, 请求者: {holder}")
                    return False
            else:
                log(level="WARNING", message=f"释放微信界面锁失败: 锁未被占用")
                return False

    def try_acquire(self, holder=None):
        """
        尝试获取锁（非阻塞，立即返回结果）

        :param holder: 占用者标识
        :return: 是否成功获取锁
        """
        if not self._enabled:
            return True

        with self._lock:
            if not self._held:
                self._held = True
                self._holder = holder
                self._hold_time = datetime.now()
                log(message=f"微信界面锁已获取（try_acquire）: {holder}")
                return True
            return False

    def is_held(self):
        """
        检查锁是否被占用

        :return: 是否被占用
        """
        with self._lock:
            return self._held

    def get_holder(self):
        """
        获取锁占用者

        :return: 占用者标识
        """
        with self._lock:
            return self._holder

    def get_hold_time(self):
        """
        获取锁占用开始时间

        :return: 占用开始时间（datetime对象）
        """
        with self._lock:
            return self._hold_time

    def get_held_duration(self):
        """
        获取锁已占用时长

        :return: 占用时长（秒）
        """
        with self._lock:
            if self._held and self._hold_time:
                return (datetime.now() - self._hold_time).total_seconds()
            return 0

    def force_release(self):
        """
        强制释放锁（管理员操作，忽略持有者验证）

        :return: 是否成功释放锁
        """
        if not self._enabled:
            return True

        with self._lock:
            if self._held:
                held_duration = (datetime.now() - self._hold_time).total_seconds() if self._hold_time else 0
                log(level="WARNING", message=f"微信界面锁被强制释放: {self._holder}, 持有时间: {held_duration:.2f}秒")
                self._held = False
                self._holder = None
                self._hold_time = None
                return True
            return False

    def acquire_with_timeout(self, holder=None, timeout=30):
        """
        获取锁（带超时时间）

        :param holder: 占用者标识
        :param timeout: 超时时间（秒），默认30秒
        :return: 是否成功获取锁
        """
        return self.acquire(holder=holder, timeout=timeout)

    def check_timeout(self):
        """
        检查锁是否超时，如果超时则自动释放

        :return: 是否因为超时而释放
        """
        if not self._enabled:
            return False

        with self._lock:
            if self._held and self._hold_time:
                held_duration = (datetime.now() - self._hold_time).total_seconds()
                if held_duration >= self._lock_timeout:
                    log(level="WARNING", message=f"微信界面锁超时自动释放: {self._holder}, 持有时间: {held_duration:.2f}秒")
                    self._held = False
                    self._holder = None
                    self._hold_time = None
                    return True
        return False

    def set_timeout(self, timeout):
        """
        设置锁超时时间

        :param timeout: 超时时间（秒）
        """
        with self._lock:
            self._lock_timeout = timeout
            log(message=f"微信界面锁超时时间已设置为: {timeout}秒")

    def get_timeout(self):
        """
        获取锁超时时间

        :return: 超时时间（秒）
        """
        with self._lock:
            return self._lock_timeout

    def set_enabled(self, enabled):
        """
        设置锁机制开关

        :param enabled: 是否启用锁机制
        """
        with self._lock:
            self._enabled = enabled
            if not enabled and self._held:
                log(level="WARNING", message=f"锁机制被关闭，强制释放当前锁: {self._holder}")
                self._held = False
                self._holder = None
                self._hold_time = None
            log(message=f"微信界面锁机制已{'启用' if enabled else '禁用'}")

    def is_enabled(self):
        """
        检查锁机制是否启用

        :return: 是否启用
        """
        with self._lock:
            return self._enabled

    def get_status(self):
        """
        获取锁状态信息

        :return: 锁状态字典
        """
        with self._lock:
            return {
                "held": self._held,
                "holder": self._holder,
                "hold_time": self._hold_time.strftime("%Y/%m/%d %H:%M:%S") if self._hold_time else None,
                "held_duration": (datetime.now() - self._hold_time).total_seconds() if self._held and self._hold_time else 0,
                "timeout": self._lock_timeout,
                "enabled": self._enabled,
            }

    def __enter__(self):
        """上下文管理器进入方法"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出方法"""
        self.release()


class WXLockContext:
    """
    微信界面操作锁上下文管理器
    使用方式：
    with WXLockContext(wx_lock, holder="task_name", timeout=30):
        # 执行微信界面操作
    """

    def __init__(self, wx_lock, holder=None, timeout=None):
        """
        :param wx_lock: WXLock 实例
        :param holder: 占用者标识
        :param timeout: 超时时间（秒）
        """
        self._wx_lock = wx_lock
        self._holder = holder
        self._timeout = timeout
        self._acquired = False

    def __enter__(self):
        """上下文管理器进入方法"""
        self._acquired = self._wx_lock.acquire(holder=self._holder, timeout=self._timeout)
        return self._acquired

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出方法"""
        if self._acquired:
            self._wx_lock.release(holder=self._holder)


def wx_lock_decorator(holder=None, timeout=None):
    """
    微信界面操作锁装饰器
    使用方式：
    @wx_lock_decorator(holder="task_name", timeout=30)
    def send_message(self, chat_name, content):
        # 执行微信界面操作
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 尝试从参数中获取 wx_lock 对象
            wx_lock = None
            for arg in args:
                if hasattr(arg, 'wx_lock'):
                    wx_lock = arg.wx_lock
                    break
            if wx_lock is None and len(args) > 0:
                bot = getattr(args[0], 'bot', None)
                if bot and hasattr(bot, 'wx_lock'):
                    wx_lock = bot.wx_lock

            if wx_lock:
                with WXLockContext(wx_lock, holder=holder, timeout=timeout):
                    return func(*args, **kwargs)
            else:
                log(level="WARNING", message=f"未找到 wx_lock 对象，跳过锁操作")
                return func(*args, **kwargs)
        return wrapper
    return decorator
