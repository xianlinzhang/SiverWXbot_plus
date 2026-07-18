from __future__ import annotations
from wxautox4 import uia
from wxautox4.param import (
    WxParam,
    WxResponse,
)
from wxautox4.languages import MENU_OPTIONS
from wxautox4.ui.component import Menu
from wxautox4.utils.tools import wxlog_debug_control
from wxautox4.utils.win32 import SetClipboardText
from wxautox4.utils.human import (
    human_sleep,
    human_click,
    human_dbl_click,
)
from wxautox4.logger import wxlog
import time
from typing import (
    Union,
    List
)
import re


class SessionBox:
    def __init__(self, control, parent):
        self.control: uia.Control = control
        self.root = parent.root
        self.parent = parent
        self.init()

    def init(self):

        # 两个个布局，搜索输入框和添加群聊(B0)、聊天列表(B1)
        # _______________
        # | B0 |
        # |————|
        # |    |
        # | B1 |   <--- 微信会话布局简图示意
        # |    |
        # |————|
        # ———————————————

        # B0搜索输入框
        self.searchbox = self.control.GroupControl(ClassName="mmui::XSearchField").EditControl()

        # B1搜索输入框
        self.session_list = self.control.GroupControl(ClassName="mmui::ChatSessionList").ListControl(ClassName="mmui::XTableView", Name="会话")

        self.search_content = None

        # wxlog_debug_control('session_list', self.session_list)
        # self.search_content = self.parent.control.WindowControl(ClassName="mmui::SearchContentPopover")
        # wxlog_debug_control('search_content', self.search_content)


    def get_search_content(self):
        wxlog.debug(f"开始get_search_content")
        if self.search_content:
            return self.search_content
        else:
            # self.search_content = self.root.control.FindControlByCondition( {'ClassName': 'mmui::SearchContentPopover'})
            self.search_content = self.parent.control.WindowControl(ClassName="mmui::SearchContentPopover")
            wxlog_debug_control('search_content', self.search_content)
            return self.search_content


    def roll_up(self, n: int=5):
        self.control.MiddleClick()
        self.control.WheelUp(wheelTimes=n)

    def roll_down(self, n: int=5):
        self.control.MiddleClick()
        self.control.WheelDown(wheelTimes=n)

    def get_session(self) -> List[SessionElement]:
        if self.session_list.Exists(0):
            return [SessionElement(i, self) for i in self.session_list.GetChildren()]
        else:
            return []

    def search(
            self, 
            keywords: str,
            force: bool = False,
            force_wait: Union[float, int] = 0.5
        ):
        """
        搜索聊天会话，支持拟人化输入延迟
        
        Args:
            keywords: 搜索关键词
            force: 是否强制重新搜索
            force_wait: 强制搜索时等待时间
            
        Returns:
            List[SearchResultElement]: 搜索结果列表
        """
        wxlog.debug(f"开始search")
        
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(0.1, 0.3)
        
        self.control.SendKeys('{Ctrl}f', waitTime=0)
        
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(0.2, 0.5)

        if WxParam.ENABLE_HUMANIZATION:
            for char in keywords:
                self.searchbox.SendKeys(char, waitTime=0)
                human_sleep(WxParam.SEARCH_KEY_INTERVAL_MIN, WxParam.SEARCH_KEY_INTERVAL_MAX)
            human_sleep(0.3, 0.8)
        else:
            self.searchbox.SendKeys(keywords, waitTime=1.5)
            time.sleep(force_wait)

        search_result = self.get_search_content().ListControl()

        if force:
            if WxParam.ENABLE_HUMANIZATION:
                human_sleep(0.5, 1.0)
            else:
                time.sleep(force_wait)

        return [SearchResultElement(i) for i in search_result.GetChildren()]
    
    def switch_chat(
        self,
        keywords: str, 
        exact: bool = True,
        force: bool = False,
        force_wait: Union[float, int] = 0.5
    ):
        """
        根据关键词切换到指定的聊天窗口
        
        通过微信的搜索功能查找聊天会话，支持精确匹配和模糊匹配两种模式，
        可按昵称、微信号进行匹配。搜索超时后自动取消搜索状态。
        
        Args:
            keywords: 搜索关键词，可以是昵称、微信号或备注名
            exact: 是否精确匹配，默认为 True，精确匹配时会优先匹配完全一致的文本，
                   其次尝试按微信号或昵称字段进行匹配
            force: 是否强制重新搜索，默认为 False，设为 True 时会清除搜索框内容后重新输入
            force_wait: 强制搜索时等待搜索框清空的时间（秒），默认为 0.5 秒
        
        Returns:
            str: 成功切换时返回实际匹配到的聊天对象名称；未找到时返回 None
        """
        wxlog.debug(f"切换聊天窗口: {keywords}, {exact}, {force}, {force_wait}")


        # 执行搜索操作，在搜索框中输入关键词
        search_result = self.search(keywords, force, force_wait)
        
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(WxParam.SEARCH_CLICK_DELAY_MIN, WxParam.SEARCH_CLICK_DELAY_MAX)
        
        # 记录搜索开始时间，用于超时判断
        t0 = time.time()
        
        # 循环等待搜索结果出现，直到超时
        while time.time() - t0 < WxParam.SEARCH_CHAT_TIMEOUT:
            # 每次循环清空结果列表，重新获取最新的搜索结果
            results = []
            search_result_items = self.get_search_content().ListControl().GetChildren()
            
            # 遍历所有搜索结果项
            for search_result_item in search_result_items:
                # 获取搜索结果项的文本内容（通常包含昵称、微信号等信息）
                text: str = search_result_item.Name

                wxlog.debug(f"关键词: {keywords}, 搜索到 {text}")

                # 根据匹配模式进行处理
                if exact:
                    # 精确匹配模式
                    # 1. 首先尝试完全匹配
                    if text == keywords:
                        if WxParam.ENABLE_HUMANIZATION:
                            human_click(search_result_item,min_delay=WxParam.CLICK_DELAY_MIN,max_delay=WxParam.CLICK_DELAY_MAX)
                        else:
                            search_result_item.Click()
                        return keywords
                    # 2. 尝试按微信号字段匹配（格式如"昵称 微信号: xxx"）
                    elif (
                        ' 微信号: ' in text
                        and (split:=text.split(' 微信号: '))[-1].lower() == keywords.lower()
                    ):
                        if WxParam.ENABLE_HUMANIZATION:
                            human_click(search_result_item,min_delay=WxParam.CLICK_DELAY_MIN,max_delay=WxParam.CLICK_DELAY_MAX)
                        else:
                            search_result_item.Click()
                        return split[0]  # 返回实际昵称
                    # 3. 尝试按昵称字段匹配（格式如"备注名 昵称: xxx"）
                    elif (
                        ' 昵称: ' in text
                        and (split:=text.split(' 昵称: '))[-1].lower() == keywords.lower()
                    ):
                        if WxParam.ENABLE_HUMANIZATION:
                            human_click(search_result_item,min_delay=WxParam.CLICK_DELAY_MIN,max_delay=WxParam.CLICK_DELAY_MAX)
                        else:
                            search_result_item.Click()
                        return split[0]  # 返回实际备注名
                else:
                    # 模糊匹配模式，只要关键词在文本中出现就匹配
                    if keywords in text:
                        if WxParam.ENABLE_HUMANIZATION:
                            human_click(search_result_item,min_delay=WxParam.CLICK_DELAY_MIN,max_delay=WxParam.CLICK_DELAY_MAX)
                        else:
                            search_result_item.Click()
                        return text
                    
            if WxParam.ENABLE_HUMANIZATION:
                human_sleep(0.1, 0.3)
        
        # 搜索超时仍未找到匹配项，取消搜索状态
        if self.search_content.Exists(0):
            self.control.MiddleClick()

    def open_separate_window(self, name: str):
        """
        在独立窗口中打开会话，支持拟人化操作延迟
        
        Args:
            name: 会话名称
            
        Returns:
            WxResponse: 操作结果
        """
        wxlog.debug(f"打开独立窗口: {name}")
        realname = self.switch_chat(name)
        if not realname:
            return WxResponse.failure('未找到会话')
        
        if WxParam.ENABLE_HUMANIZATION:
            human_sleep(0.3, 0.8)
        else:
            time.sleep(0.3)
            
        while True:
            session = [i for i in self.get_session() if uia.IsElementInWindow(self.session_list, i.control)][0]
            if session.content.startswith(realname):
                break
        
        if WxParam.ENABLE_HUMANIZATION:
            human_dbl_click(session.control,min_delay=WxParam.CLICK_DELAY_MIN,max_delay=WxParam.CLICK_DELAY_MAX)
        else:
            session.double_click()
            
        return WxResponse.success(data={'nickname': realname})


    def go_top(self):
        wxlog.debug("回到会话列表顶部")
        self.control.MiddleClick()
        self.control.SendKeys('{Home}')

    def go_bottom(self):
        wxlog.debug("回到会话列表底部")
        self.control.MiddleClick()
        self.control.SendKeys('{End}')
    
class SessionElement:
    def __init__(
            self, 
            control: uia.Control, 
            parent: SessionBox, 
        ):
        self.root = parent.root
        self.parent = parent
        self.control = control
        self.content = control.Name

    @property
    def texts(self) -> List[str]:
        """拆分当前会话控件中的文本行"""

        return [
            line for line in str(self.content).split('\n')
            if line and line.strip()
        ]

    @property
    def name(self) -> str:
        """会话名称"""

        if self.texts:
            return self.texts[0]
        return ''

    @property
    def unread_count(self) -> int:
        """未读消息数量"""

        unread_pattern = re.compile(r'\[(\d+)条\]')
        for text in self.texts:
            if match := unread_pattern.search(text):
                return int(match.group(1))
        return 0

    def _menu_option_text(self, option_key: str) -> str:
        option = MENU_OPTIONS.get(option_key, {})
        lang = getattr(WxParam, 'LANGUAGE', 'cn')
        text = option.get(lang) if isinstance(option, dict) else None
        if not text:
            text = option.get('cn') if isinstance(option, dict) else None
        return text or option_key

    def select_menu_option(self, option_key: str, wait=0.3):
        """根据配置语言选择菜单项"""

        option_text = self._menu_option_text(option_key)
        return self.select_option(option_text, wait)

    def __repr__(self):
        content = str(self.content).replace('\n', ' ')
        if len(content) > 5:
            content = content[:5] + '...'
        return f"<wxauto4 Session Element({content})>"
    
    def roll_into_view(self):
        uia.RollIntoView(self.control.GetParentControl(), self.control)

    # @uilock
    def _click(self, right: bool=False, double: bool=False):
        """
        点击会话元素，支持拟人化操作
        
        Args:
            right: 是否右键点击
            double: 是否双击
        """
        self.roll_into_view()
        
        if WxParam.ENABLE_HUMANIZATION:
            if right:
                self.control.RightClick(simulateMove=True)
            elif double:
                human_dbl_click(self.control,
                               min_delay=WxParam.CLICK_DELAY_MIN,
                               max_delay=WxParam.CLICK_DELAY_MAX)
            else:
                human_click(self.control,
                           min_delay=WxParam.CLICK_DELAY_MIN,
                           max_delay=WxParam.CLICK_DELAY_MAX)
        else:
            if right:
                self.control.RightClick()
            elif double:
                self.control.DoubleClick()
            else:
                self.control.Click()

    def click(self):
        self._click()

    def right_click(self):
        self._click(right=True)

    def double_click(self):
        self._click(double=True)

    def select_option(self, option: str, wait=0.3):
        """
        选择右键菜单项，支持拟人化操作延迟
        
        Args:
            option: 菜单项名称
            wait: 等待菜单出现的时间
            
        Returns:
            WxResponse: 操作结果
        """
        self.roll_into_view()
        
        if WxParam.ENABLE_HUMANIZATION:
            self.control.RightClick(simulateMove=True)
            human_sleep(0.2, 0.5)
        else:
            self.control.RightClick()
            time.sleep(wait)
            
        menu = Menu(self.parent)
        return menu.select(option)

    def pin(self):
        """置顶聊天"""

        return self.select_menu_option('置顶')

    def unpin(self):
        """取消置顶聊天"""

        return self.select_menu_option('取消置顶')

    def mark_unread(self):
        """标记为未读"""

        return self.select_menu_option('标为未读')

    def toggle_mute(self):
        """切换消息免打扰状态"""

        return self.select_menu_option('消息免打扰')

    def open_in_separate_window(self):
        """在独立窗口中打开会话"""

        return self.select_menu_option('在独立窗口打开')

    def hide(self):
        """不显示聊天"""

        return self.select_menu_option('不显示聊天')

    def delete(self):
        """删除聊天"""

        return self.select_menu_option('删除聊天')

class SearchResultElement:
    def __init__(self, control):
        self.control = control
        self.content = control.Name
        self.type = control.ClassName

    def __repr__(self):
        content = str(self.content).replace('\n', ' ')
        if len(content) > 5:
            content = content[:5] + '...'
        return f"<wxauto4 Search Element({content})>"

    def get_all_text(self):
        return [
            line for line in str(self.content).split('\n')
            if line and line.strip()
        ]
    
    def click(self):
        """
        点击搜索结果，支持拟人化操作
        
        使用平滑鼠标移动和随机点击位置
        """
        uia.RollIntoView(self.control.GetParentControl(), self.control)
        
        if WxParam.ENABLE_HUMANIZATION:
            human_click(self.control,
                       min_delay=WxParam.CLICK_DELAY_MIN,
                       max_delay=WxParam.CLICK_DELAY_MAX)
        else:
            self.control.Click()

    def close(self):
        """关闭搜索结果"""
        self.control.SendKeys('{Esc}')
