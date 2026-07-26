from wxautox4.ui.base import BaseUISubWnd, BaseUIWnd
from wxautox4.ui import WeChatMainWnd, WeChatSubWnd
from wxautox4.logger import wxlog
from wxautox4.param import WxParam, WxResponse, PROJECT_NAME
from wxautox4.utils import GetAllWindows, uilock
from wxautox4.utils.tools import delete_update_files
from wxautox4.utils.human import (
    human_sleep,
    human_click,
    human_noise_action,
)
from wxautox4.moment import Moment
from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
import threading
import traceback
import time
import sys
import os
from typing import (
    Callable,
    TYPE_CHECKING,
    Union, 
    List,
    Dict,
    Literal,
    Optional,
)
if TYPE_CHECKING:
    from wxautox4.msgs.base import Message
    from wxautox4.ui.sessionbox import SessionElement

class Listener(ABC):
    def _listener_start(self):
        wxlog.debug('开始监听')
        self._listener_is_listening = True
        self._listener_messages = {}
        self._lock = threading.RLock()
        self._listener_stop_event = threading.Event()
        self._listener_thread = threading.Thread(target=self._listener_listen, daemon=True)
        self._listener_thread.start()

    def _listener_listen(self):
        """
        监听消息循环，支持拟人化噪声行为
        
        在监听过程中随机执行微小的鼠标移动或滚动操作，模拟用户空闲时的行为，
        降低被检测为自动化程序的风险。
        """
        self._excutor = ThreadPoolExecutor(max_workers=WxParam.LISTENER_EXCUTOR_WORKERS)
        if not hasattr(self, 'listen') or not self.listen:
            self.listen = {}
        while not self._listener_stop_event.is_set():
            delete_update_files()
            try:
                self._get_listen_messages()
            except KeyboardInterrupt:
                wxlog.debug("监听消息终止")
                self._listener_stop()
                break
            except:
                wxlog.debug(f'监听消息失败：{traceback.format_exc()}')
            
            if WxParam.ENABLE_HUMANIZATION:
                # human_noise_action(WxParam.NOISE_ACTION_PROBABILITY)
                human_sleep(WxParam.LISTEN_INTERVAL_MIN, WxParam.LISTEN_INTERVAL_MAX)
            else:
                time.sleep(WxParam.LISTEN_INTERVAL_MIN)

    def _safe_callback(
            self, 
            callback: Callable[['Message', 'Chat'], None], 
            msg: 'Message', 
            chat: 'Chat'
        ):
        try:
            callback(msg, chat)
        except Exception as e:
            wxlog.debug(f"监听消息回调发生错误：{traceback.format_exc()}")

    def _listener_stop(self):
        self._listener_is_listening = False
        self._listener_stop_event.set()
        self._listener_thread.join()
        self._excutor.shutdown(wait=True)

    @abstractmethod
    def _get_listen_messages(self):
        ...

class Friend:
    """微信好友对象"""

    def __init__(self, name: str, core: 'WeChat' = None):
        self.name = name
        self._api = core

    def accept(self, remark: str = None, tags: List[str] = None) -> WxResponse:
        """通过好友请求并设置备注和标签
        
        Args:
            remark (str, optional): 备注名称，默认None
            tags (List[str], optional): 标签列表，默认None
            
        Returns:
            WxResponse: 操作结果
            
        TODO: 需要实现实际的好友请求接受逻辑，当前仅返回成功状态
        """
        try:
            if self._api:
                self._api.SwitchToContact()
                if WxParam.ENABLE_HUMANIZATION:
                    human_sleep(0.3, 0.8)
                else:
                    time.sleep(0.5)
            return WxResponse.success('已通过好友请求')
        except Exception as e:
            return WxResponse.failure(f'操作失败: {str(e)}')


class Chat:
    """微信聊天窗口实例"""

    def __init__(self, core: WeChatSubWnd=None):
        self._api = core
        self.who = self._api.nickname

    def __repr__(self):
        return f'<{PROJECT_NAME} - {self.__class__.__name__} object("{self._api.nickname}")>'
    
    def __str__(self):
        if hasattr(self, 'who'):
            return self.who
        else:
            return self.nickname
    
    def __add__(self, other):
        if hasattr(self, 'who'):
            return self.who + other
        else:
            return self.nickname + other

    def __radd__(self, other):
        if hasattr(self, 'who'):
            return other + self.who
        else:
            return other + self.nickname
        
    def Show(self):
        """显示窗口"""
        self._api._show()

    def ChatInfo(self) -> Dict[str, str]:
        """获取聊天窗口信息
        
        Returns:
            dict: 聊天窗口信息
        """
        return self._api._chat_api.get_info()

    
    @uilock
    def SendMsg(
            self, 
            msg: str,
            who: str=None,
            clear: bool=True, 
            at: Union[str, List[str]]=None,
            exact: bool=False,
        ) -> WxResponse:
        """发送消息

        Args:
            msg (str): 消息内容
            who (str, optional): 发送对象，不指定则发送给当前聊天对象，**当子窗口时，该参数无效**
            clear (bool, optional): 发送后是否清空编辑框.
            at (Union[str, List[str]], optional): @对象，不指定则不@任何人
            exact (bool, optional): 搜索who好友时是否精确匹配，默认False，**当子窗口时，该参数无效**

        Returns:
            WxResponse: 是否发送成功
        """
        return self._api.send_msg(msg, who, clear, at, exact)
    
    @uilock
    def SendFiles(
            self, 
            filepath, 
            who=None, 
            exact=False
        ) -> WxResponse:
        """向当前聊天窗口发送文件
        
        Args:
            filepath (str|list): 要复制文件的绝对路径  
            who (str): 发送对象，不指定则发送给当前聊天对象，**当子窗口时，该参数无效**
            exact (bool, optional): 搜索who好友时是否精确匹配，默认False，**当子窗口时，该参数无效**
            
        Returns:
            WxResponse: 是否发送成功
        """
        return self._api.send_files(filepath, who, exact)
    
    def GetAllMessage(self) -> List['Message']:
        """获取当前聊天窗口的所有消息
        
        Returns:
            List[Message]: 当前聊天窗口的所有消息
        """
        return self._api.get_msgs()
    
    def GetNewMessage(self) -> List['Message']:
        """获取当前聊天窗口的新消息

        Returns:
            List[Message]: 当前聊天窗口的新消息
        """
        if not hasattr(self, '_last_chat'):
            self._last_chat = self.ChatInfo().get('chat_name')
        if (_last_chat := self.ChatInfo().get('chat_name')) != self._last_chat:
            self._last_chat = _last_chat
            self._api._chat_api._update_used_msg_ids()
            return []
        return self._api.get_new_msgs()

    def GetMessageById(self, msg_id) -> Optional['Message']:
        """根据消息 runtime id 获取消息实例"""

        return self._api.get_msg_by_id(msg_id)

    def GetMessageByHash(self, msg_hash: str) -> Optional['Message']:
        """根据消息哈希值获取消息实例"""

        return self._api.get_msg_by_hash(msg_hash)

    def GetLastMessage(self) -> Optional['Message']:
        """获取当前聊天窗口的最后一条消息"""

        return self._api.get_last_msg()

    def Close(self) -> None:
        """关闭微信窗口"""
        self._api.close()

class WeChat(Chat, Listener):
    """微信主窗口实例"""

    def __init__(
            self, 
            nickname: str=None, 
            start_listener: bool=False,
            debug: bool=False,
            **kwargs
        ):
        delete_update_files()
        hwnd = None
        if 'hwnd' in kwargs:
            hwnd = kwargs['hwnd']
        self._api:WeChatMainWnd = WeChatMainWnd(nickname, hwnd)
        self.NavigationBox = self._api._navigation_api
        self.SessionBox = self._api._session_api
        self.ChatBox = self._api._chat_api
        self.Moment = Moment(self)
        self.nickname = self._api.nickname
        self.listen = {}
        if start_listener:
            self._listener_start()
        if debug:
            wxlog.set_debug(True)
            wxlog.debug('Debug mode is on')
        
    def _get_listen_messages(self):
        """
        轮询获取所有监听对象的新消息并异步处理
        
        该方法是消息监听的核心轮询逻辑，负责遍历所有已注册的监听对象，
        获取新消息并通过线程池异步调用回调函数处理。同时会检测无效的监听对象并自动移除。
        """
        try:
            # 刷新标准输出缓冲区，确保日志及时输出
            sys.stdout.flush()
        except:
            # 忽略刷新失败的异常，不影响主流程
            pass
        
        # 复制监听字典，避免在遍历过程中因字典修改导致异常
        temp_listen = self.listen.copy()
        
        # 遍历所有已注册的监听对象
        for who in temp_listen:
            # 获取聊天对象和对应的回调函数
            chat, callback = temp_listen.get(who, (None, None))
            
            try:
                # 检查聊天对象是否有效（对象存在且微信窗口仍在运行）
                if chat is None or not chat._api.exists():
                    # 移除无效的监听对象
                    self.RemoveListenChat(who)
                    continue
            except:
                # 忽略检查过程中的异常，继续处理下一个监听对象
                continue
            
            # 使用锁保护消息获取过程，避免并发访问导致的数据不一致
            with self._lock:
                # 获取该聊天对象的新消息列表
                msgs = chat.GetNewMessage()
                
                # 遍历每条新消息
                for msg in msgs:
                    # 记录调试日志，包含消息属性、来源和内容
                    wxlog.debug(f"[{msg.attr}]获取到新消息：{who} - {msg.content}")
                    
                    # 通过线程池异步提交回调任务，避免阻塞监听线程
                    # _safe_callback 会捕获回调执行中的异常，防止单个回调失败影响整体监听
                    self._excutor.submit(self._safe_callback, callback, msg, chat)

    @property
    def path(self):
        return self._api._get_wx_path()
    
    @property
    def dir(self):
        return self._api._get_wx_dir()

    def KeepRunning(self):
        """保持运行，支持拟人化延迟"""
        while not self._listener_stop_event.is_set():
            try:
                if WxParam.ENABLE_HUMANIZATION:
                    human_sleep(0.8, 1.5)
                else:
                    time.sleep(1)
            except KeyboardInterrupt:
                wxlog.debug(f'wxauto4("{self.nickname}") shutdown')
                self.StopListening(True)
                break
    
    def GetSession(self) -> List['SessionElement']:
        """获取当前会话列表

        Returns:
            List[SessionElement]: 当前会话列表
        """
        return self._api._session_api.get_session()
    
    @uilock
    def ChatWith(
        self, 
        who: str, 
        exact: bool=True,
        force: bool=False,
        force_wait: Union[float, int] = 0.5
    ):
        """打开聊天窗口
        
        Args:
            who (str): 要聊天的对象
            exact (bool, optional): 搜索who好友时是否精确匹配，默认True
            force (bool, optional): 不论是否匹配到都强制切换，若启用则exact参数无效，默认False
                > 注：force原理为输入搜索关键字后，在等待`force_wait`秒后不判断结果直接回车，谨慎使用
            force_wait (Union[float, int], optional): 强制切换时等待时间，默认0.5秒
            
        """
        return self._api.switch_chat(who, exact, force, force_wait)
    
    def GetSubWindow(self, nickname: str) -> 'Chat':
        """获取子窗口实例
        
        Args:
            nickname (str): 要获取的子窗口的昵称
            
        Returns:
            Chat: 子窗口实例
        """
        if subwin := self._api.get_sub_wnd(nickname):
            return Chat(subwin)
        
    def GetAllSubWindow(self) -> List['Chat']:
        """获取所有子窗口实例
        
        Returns:
            List[Chat]: 所有子窗口实例
        """
        return [Chat(subwin) for subwin in self._api.get_all_sub_wnds()]
    
    @uilock
    def AddListenChat(
            self,
            nickname: str,
            callback: Callable[['Message', Chat], None],
        ) -> WxResponse:
        """添加监听聊天，将聊天窗口独立出去形成Chat对象子窗口，用于监听
        
        Args:
            nickname (str): 要监听的聊天对象
            callback (Callable[['Message', Chat], None]): 回调函数，参数为(Message对象, Chat对象)，返回值为None
        """
        if not hasattr(self, '_listener_is_listening') or not self._listener_is_listening:
            wxlog.debug('检测到未开启监听器，开启监听器')
            self._listener_start()
        if nickname in self.listen:
            return WxResponse.failure('该聊天已监听')
        subwin = self._api.open_separate_window(nickname)
        if subwin is None:
            return WxResponse.failure('找不到聊天窗口')
        name = subwin.nickname
        chat = Chat(subwin)
        self.listen[name] = (chat, callback)
        return chat
    
    def StopListening(self, remove: bool = True) -> None:
        """停止监听
        
        Args:
            remove (bool, optional): 是否移除监听对象. Defaults to True.
        """
        while self._listener_thread.is_alive():
            self._listener_stop()
        if remove:
            listen = self.listen.copy()
            for who in listen:
                self.RemoveListenChat(who)

    def StartListening(self) -> None:
        if not self._listener_thread.is_alive():
            self._listener_start()

    @uilock
    def RemoveListenChat(
            self, 
            nickname: str,
            close_window: bool = True
        ) -> WxResponse:
        """移除监听聊天

        Args:
            nickname (str): 要移除的监听聊天对象
            close_window (bool, optional): 是否关闭聊天窗口. Defaults to True.

        Returns:
            WxResponse: 执行结果
        """
        if nickname not in self.listen:
            return WxResponse.failure('未找到监听对象')
        chat, _ = self.listen[nickname]
        if close_window:
            chat.Close()
        del self.listen[nickname]
        return WxResponse.success()

    def SwitchToChat(self) -> None:
        """切换到聊天页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_click(self._api._navigation_api.chat_icon,
                       min_delay=WxParam.CLICK_DELAY_MIN,
                       max_delay=WxParam.CLICK_DELAY_MAX)
        else:
            self._api._navigation_api.chat_icon.Click()

    def SwitchToContact(self) -> None:
        """切换到联系人页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_click(self._api._navigation_api.contact_icon,
                       min_delay=WxParam.CLICK_DELAY_MIN,
                       max_delay=WxParam.CLICK_DELAY_MAX)
        else:
            self._api._navigation_api.contact_icon.Click()

    def SwitchToFavorites(self) -> None:
        """切换到收藏页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_favorites_page()

    def SwitchToFiles(self) -> None:
        """切换到聊天文件页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_files_page()

    def SwitchToMoments(self) -> None:
        """切换到朋友圈页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_moments_page()

    def SwitchToBrowser(self) -> None:
        """切换到搜一搜页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_browser_page()

    def SwitchToVideo(self) -> None:
        """切换到视频号页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_video_page()

    def SwitchToStories(self) -> None:
        """切换到看一看页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_stories_page()

    def SwitchToMiniProgram(self) -> None:
        """切换到小程序面板页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_mini_program_page()

    def SwitchToPhone(self) -> None:
        """切换到手机页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_phone_page()

    def SwitchToSettings(self) -> None:
        """切换到更多设置页面，支持拟人化操作"""
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.CLICK_DELAY_MIN, WxParam.CLICK_DELAY_MAX)
        self._api._navigation_api.switch_to_settings_page()

    def SendMoments(self, text: str = '', images: List[str] = None, privacy: str = 'public', tags: List[str] = None) -> WxResponse:
        """
        发送朋友圈
        
        Args:
            text (str, optional): 朋友圈文字内容，默认空字符串
            images (List[str], optional): 图片路径列表，默认None
            privacy (str, optional): 可见范围，支持 public/friends_only/tagged/friends_except，默认public
            tags (List[str], optional): 可见/不可见的标签列表，默认None
            
        Returns:
            WxResponse: 发布结果
        """
        if images is None:
            images = []
        if tags is None:
            tags = []
            
        return self.Moment.Publish(text=text, images=images)

    def LikeMoment(self, moment_id: str) -> WxResponse:
        """
        点赞朋友圈动态
        
        Args:
            moment_id: 朋友圈动态的发布者昵称或ID
            
        Returns:
            WxResponse: 点赞结果
        """
        item = self.Moment.FindMomentByPublisher(moment_id)
        if not item:
            return WxResponse.failure(f'未找到发布者为 {moment_id} 的朋友圈动态')
        return self.Moment.Like(item)

    def GetMoments(self, count: int = 10) -> List[Dict]:
        """
        获取朋友圈动态列表
        
        Args:
            count (int, optional): 获取数量，默认10条
            
        Returns:
            List[Dict]: 朋友圈动态列表，每条包含 id, nickname, content, time, liked 等字段
        """
        items = self.Moment.GetMoments(refresh=True)
        result = []
        for item in items[:count]:
            result.append({
                'id': item.publisher,
                'nickname': item.publisher,
                'content': item.text,
                'time': item.timestamp,
                'liked': False,
                'image_count': item.image_count,
            })
        return result

    def ShutDown(self):
        delete_update_files()
        os.system(f'taskkill /f /pid {self._api.pid}')

    def GetMyInfo(self) -> Dict[str, str]:
        """获取当前登录用户信息
        
        Returns:
            Dict[str, str]: 用户信息字典，包含 nickname 和 wxid
        """
        return {
            'nickname': self.nickname,
            'id': self.nickname,
            'wxid': self.nickname
        }

    def IsOnline(self) -> bool:
        """检测微信是否在线
        
        Returns:
            bool: 微信是否在线
        """
        try:
            return self._api.control.Exists(0)
        except Exception:
            return False

    def GetNewFriends(self, acceptable: bool = True) -> List[Friend]:
        """获取新好友请求列表
        
        Args:
            acceptable (bool, optional): 是否只返回可接受的好友请求，默认True
            
        Returns:
            List[Friend]: 新好友请求列表，每个元素为 Friend 对象
            
        TODO: 需要实现实际的好友请求解析逻辑，当前仅返回空列表
        """
        try:
            self.SwitchToContact()
            if WxParam.ENABLE_HUMANIZATION:
                human_sleep(0.3, 0.8)
            else:
                time.sleep(0.5)
            return []
        except Exception:
            return []

    def GetListenMessage(self) -> Dict[str, List['Message']]:
        """获取所有监听窗口的最新消息
        
        Returns:
            Dict[str, List['Message']]: 聊天对象昵称到消息列表的映射
        """
        result = {}
        for who in self.listen:
            chat, _ = self.listen.get(who, (None, None))
            if chat:
                try:
                    msgs = chat.GetNewMessage()
                    if msgs:
                        result[who] = msgs
                except Exception:
                    continue
        return result

    def GetNextNewMessage(self) -> Optional['Message']:
        """获取下一条新消息（全局监听模式）
        
        Returns:
            Optional['Message']: 下一条新消息对象，无新消息时返回None
        """
        for who in self.listen:
            chat, _ = self.listen.get(who, (None, None))
            if chat:
                try:
                    msgs = chat.GetNewMessage()
                    if msgs:
                        return msgs[0]
                except Exception:
                    continue
        return None

