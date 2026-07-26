from typing import Literal
import os

PROJECT_NAME = 'wxautox4'

class WxParam:
    # 语言设置
    LANGUAGE: Literal['cn', 'cn_t', 'en'] = 'cn'

    # 是否启用日志文件
    ENABLE_FILE_LOGGER: bool = True

    # 下载文件/图片默认保存路径
    DEFAULT_SAVE_PATH: str = os.path.join(os.getcwd(), 'wxauto4文件下载')

    # 是否启用消息哈希值用于辅助判断消息，开启后会稍微影响性能
    MESSAGE_HASH: bool = False

    # 头像到消息X偏移量，用于消息定位，点击消息等操作
    DEFAULT_MESSAGE_XBIAS = 51
    DEFAULT_MESSAGE_YBIAS = 30

    # 是否强制重新自动获取X偏移量，如果设置为True，则每次启动都会重新获取
    FORCE_MESSAGE_XBIAS: bool = False

    # 聊天窗口大小配置
    CHAT_WINDOW_SIZE: tuple = (1500, 6000)

    # 监听消息时间间隔范围，单位秒（随机取范围内的值）
    LISTEN_INTERVAL_MIN: float = 0.8
    LISTEN_INTERVAL_MAX: float = 1.5
    
    # 监听消息时间间隔（兼容性属性，返回范围中间值）
    LISTEN_INTERVAL: float = (LISTEN_INTERVAL_MIN + LISTEN_INTERVAL_MAX) / 2

    # 监听执行器线程池大小
    LISTENER_EXCUTOR_WORKERS: int = 4

    # 搜索聊天对象超时时间，单位秒
    SEARCH_CHAT_TIMEOUT: int = 2

    # 微信笔记加载超时时间，单位秒
    NOTE_LOAD_TIMEOUT: int = 30

    # 发送文件超时时间，单位秒
    SEND_FILE_TIMEOUT: int = 10

    # ========== 拟人化配置 ==========

    # 是否启用拟人化操作（启用后操作更接近人类行为，但会增加少量延迟）
    ENABLE_HUMANIZATION: bool = True

    # 鼠标移动时间范围（秒）
    MOUSE_MOVE_MIN: float = 0.2
    MOUSE_MOVE_MAX: float = 0.8

    # 点击位置最大随机偏移量（像素）
    CLICK_OFFSET_MAX: int = 15

    # 点击前延迟范围（秒）
    CLICK_DELAY_MIN: float = 0.1
    CLICK_DELAY_MAX: float = 0.3

    # 按键间隔范围（秒）- 模拟人类打字速度
    KEY_INTERVAL_MIN: float = 0.05
    KEY_INTERVAL_MAX: float = 0.2

    # 短消息阈值（字符）- 小于此值使用逐字输入，否则使用粘贴
    SHORT_MESSAGE_THRESHOLD: int = 50

    # 搜索关键词输入间隔范围（秒）
    SEARCH_KEY_INTERVAL_MIN: float = 0.03
    SEARCH_KEY_INTERVAL_MAX: float = 0.1

    # 搜索结果点击前延迟范围（秒）
    SEARCH_CLICK_DELAY_MIN: float = 0.2
    SEARCH_CLICK_DELAY_MAX: float = 0.5

    # 噪声行为执行概率（0.0-1.0）- 在监听循环中随机执行微小动作
    NOISE_ACTION_PROBABILITY: float = 0.1

    # 粘贴前后延迟范围（秒）
    PASTE_DELAY_MIN: float = 0.2
    PASTE_DELAY_MAX: float = 0.5

class WxResponse(dict):
    def __init__(self, status: str, message: str = None, data: dict = None):
        super().__init__(status=status, message=message, data=data)

    def __str__(self):
        return str(self.to_dict())
    
    def __repr__(self):
        return str(self.to_dict())

    def to_dict(self):
        return {
            'status': self['status'],
            'message': self['message'],
            'data': self['data']
        }

    def __bool__(self):
        return self.is_success
    
    @property
    def is_success(self):
        return self['status'] == '成功'

    @classmethod
    def success(cls, message=None, data: dict = None):
        return cls(status="成功", message=message, data=data)

    @classmethod
    def failure(cls, message: str, data: dict = None):
        return cls(status="失败", message=message, data=data)

    @classmethod
    def error(cls, message: str, data: dict = None):
        return cls(status="错误", message=message, data=data)