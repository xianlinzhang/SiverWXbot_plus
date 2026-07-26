"""
拟人化操作模块 - 模拟真实人类行为模式

提供自然的鼠标移动、随机点击位置、逐字输入和可变延迟等功能，
使自动化操作更接近真实用户行为，降低被检测的风险。
"""
import time
import random
import math
import win32api
import win32con
from typing import Optional, Union, Tuple, List
from wxautox4 import uia


def human_sleep(min_sec: float, max_sec: float) -> float:
    """
    生成符合正态分布的随机延迟时间
    
    基于指定范围生成随机等待时间，中间值概率更高，更接近人类行为模式。
    
    Args:
        min_sec: 最小延迟时间（秒）
        max_sec: 最大延迟时间（秒）
        
    Returns:
        float: 实际等待的时间（秒）
    """
    if min_sec >= max_sec:
        duration = min_sec
    else:
        mean = (min_sec + max_sec) / 2
        std_dev = (max_sec - min_sec) / 6
        duration = random.normalvariate(mean, std_dev)
        duration = max(min_sec, min(max_sec, duration))
    
    time.sleep(duration)
    return duration


def _get_cursor_pos() -> Tuple[int, int]:
    """获取当前鼠标光标位置"""
    return win32api.GetCursorPos()


def _set_cursor_pos(x: int, y: int) -> None:
    """设置鼠标光标位置"""
    win32api.SetCursorPos((x, y))


def _bezier_curve(start: Tuple[int, int], end: Tuple[int, int], 
                  control1: Optional[Tuple[int, int]] = None,
                  control2: Optional[Tuple[int, int]] = None) -> List[Tuple[int, int]]:
    """
    计算贝塞尔曲线上的点序列
    
    使用三次贝塞尔曲线生成平滑的鼠标移动轨迹，模拟人类自然的移动路径。
    
    Args:
        start: 起点坐标 (x, y)
        end: 终点坐标 (x, y)
        control1: 第一个控制点，默认自动生成
        control2: 第二个控制点，默认自动生成
        
    Returns:
        list[tuple[int, int]]: 曲线上的点序列
    """
    start_x, start_y = start
    end_x, end_y = end
    
    dx = end_x - start_x
    dy = end_y - start_y
    
    if control1 is None:
        control1 = (
            start_x + dx * random.uniform(0.2, 0.4) + random.randint(-30, 30),
            start_y + dy * random.uniform(0.1, 0.3) + random.randint(-30, 30)
        )
    
    if control2 is None:
        control2 = (
            start_x + dx * random.uniform(0.6, 0.8) + random.randint(-30, 30),
            start_y + dy * random.uniform(0.7, 0.9) + random.randint(-30, 30)
        )
    
    steps = max(abs(dx), abs(dy), 50)
    points = []
    
    for i in range(steps + 1):
        t = i / steps
        t2 = t * t
        t3 = t2 * t
        mt = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        
        x = int(mt3 * start_x + 3 * mt2 * t * control1[0] + 
                3 * mt * t2 * control2[0] + t3 * end_x)
        y = int(mt3 * start_y + 3 * mt2 * t * control1[1] + 
                3 * mt * t2 * control2[1] + t3 * end_y)
        
        if not points or (x != points[-1][0] or y != points[-1][1]):
            points.append((x, y))
    
    return points


def human_move_to(x: int, y: int, min_duration: float = 0.2, 
                  max_duration: float = 0.8) -> float:
    """
    沿贝塞尔曲线平滑移动鼠标到目标位置
    
    模拟人类自然的鼠标移动轨迹，包含轻微抖动和随机速度变化。
    
    Args:
        x: 目标位置的横坐标
        y: 目标位置的纵坐标
        min_duration: 最小移动时间（秒）
        max_duration: 最大移动时间（秒）
        
    Returns:
        float: 实际移动耗时（秒）
    """
    start_pos = _get_cursor_pos()
    
    if start_pos == (x, y):
        return 0.0
    
    duration = random.uniform(min_duration, max_duration)
    points = _bezier_curve(start_pos, (x, y))
    
    if not points:
        _set_cursor_pos(x, y)
        return 0.0
    
    step_duration = duration / len(points)
    start_time = time.time()
    
    for i, (px, py) in enumerate(points):
        _set_cursor_pos(px, py)
        
        if i < len(points) - 1:
            actual_step = step_duration * random.uniform(0.8, 1.2)
            time.sleep(actual_step)
    
    return time.time() - start_time


def _random_offset_within_bounds(center_x: int, center_y: int, 
                                 width: int, height: int,
                                 max_offset: int = 15) -> Tuple[int, int]:
    """
    在边界范围内生成随机偏移坐标
    
    Args:
        center_x: 中心点横坐标
        center_y: 中心点纵坐标
        width: 区域宽度
        height: 区域高度
        max_offset: 最大偏移量（像素）
        
    Returns:
        tuple[int, int]: 偏移后的坐标
    """
    offset_x = random.randint(-max_offset, max_offset)
    offset_y = random.randint(-max_offset, max_offset)
    
    half_width = width // 2
    half_height = height // 2
    
    new_x = max(center_x - half_width + 5, 
                min(center_x + half_width - 5, center_x + offset_x))
    new_y = max(center_y - half_height + 5, 
                min(center_y + half_height - 5, center_y + offset_y))
    
    return new_x, new_y


def human_click(control: uia.Control, min_delay: float = 0.1, 
                max_delay: float = 0.3) -> Tuple[int, int]:
    """
    在控件范围内随机位置点击
    
    模拟人类点击行为：先移动鼠标到控件附近，然后在控件内随机位置点击。
    点击位置不会总是精确居中，而是有一定的随机偏移。
    
    Args:
        control: UIA控件对象
        min_delay: 点击前最小延迟（秒）
        max_delay: 点击前最大延迟（秒）
        
    Returns:
        tuple[int, int]: 实际点击的坐标
    """
    rect = control.BoundingRectangle
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    
    target_x, target_y = _random_offset_within_bounds(center_x, center_y, width, height)
    
    human_move_to(target_x, target_y)
    
    human_sleep(min_delay, max_delay)
    
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
    time.sleep(random.uniform(0.03, 0.07))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
    
    return target_x, target_y


def _escape_sendkeys_char(char: str) -> str:
    """
    转义SendKeys特殊字符
    
    SendKeys将以下字符视为特殊控制序列：{, }, (, ), +, ^, %, ~
    需要用花括号包裹进行转义。
    
    Args:
        char: 单个字符
        
    Returns:
        str: 转义后的字符
    """
    special_chars = {'{', '}', '(', ')', '+', '^', '%', '~'}
    if char in special_chars:
        return '{' + char + '}'
    return char


def human_type_text(text: str, control: uia.Control, 
                    min_interval: float = 0.05, max_interval: float = 0.2) -> float:
    """
    逐字输入文本，模拟人类打字速度
    
    每个字符之间有随机间隔，模拟真实的打字行为。
    支持中英文混合输入，标点符号输入速度可能更快。
    自动转义SendKeys特殊字符（{, }, (, ), +, ^, %, ~）。
    
    Args:
        text: 要输入的文本内容
        control: 目标输入控件（需要先获得焦点）
        min_interval: 字符间最小间隔（秒）
        max_interval: 字符间最大间隔（秒）
        
    Returns:
        float: 实际输入耗时（秒）
    """
    if not text:
        return 0.0
    
    start_time = time.time()
    
    for i, char in enumerate(text):
        escaped_char = _escape_sendkeys_char(char)
        control.SendKeys(escaped_char, waitTime=0, charMode=False)
        
        if i < len(text) - 1:
            if char in '，。！？、；：':
                interval = random.uniform(min_interval * 0.5, max_interval * 0.5)
            elif char in ' \t\n':
                interval = random.uniform(min_interval, max_interval * 0.8)
            else:
                interval = random.uniform(min_interval, max_interval)
            
            time.sleep(interval)
    
    return time.time() - start_time


def human_scroll(direction: str = 'down', times: int = 3, 
                 min_interval: float = 0.1, max_interval: float = 0.3) -> None:
    """
    模拟人类滚动鼠标滚轮的行为
    
    滚动次数和间隔都有随机性，模拟真实用户浏览行为。
    
    Args:
        direction: 滚动方向，'up' 或 'down'
        times: 滚动次数
        min_interval: 滚动间最小间隔（秒）
        max_interval: 滚动间最大间隔（秒）
    """
    scroll_times = random.randint(max(1, times - 1), times + 1)
    
    for _ in range(scroll_times):
        if direction == 'up':
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120, 0)
        else:
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -120, 0)
        
        if _ < scroll_times - 1:
            human_sleep(min_interval, max_interval)


def human_noise_action(probability: float = 0.1) -> bool:
    """
    执行随机噪声行为，模拟用户空闲时的微小动作
    
    在监听循环中定期调用，有一定概率执行微小的鼠标移动或滚动，
    使操作模式更加自然，不易被检测。
    
    Args:
        probability: 执行噪声行为的概率（0.0-1.0）
        
    Returns:
        bool: 是否执行了噪声行为
    """
    if random.random() > probability:
        return False
    
    actions = ['move', 'scroll']
    action = random.choice(actions)
    
    if action == 'move':
        current_x, current_y = _get_cursor_pos()
        offset_x = random.randint(-20, 20)
        offset_y = random.randint(-20, 20)
        human_move_to(current_x + offset_x, current_y + offset_y, 
                      min_duration=0.1, max_duration=0.3)
        human_sleep(0.1, 0.3)
        human_move_to(current_x, current_y, 
                      min_duration=0.1, max_duration=0.3)
    
    elif action == 'scroll':
        direction = random.choice(['up', 'down'])
        human_scroll(direction, times=1, min_interval=0.05, max_interval=0.1)
    
    return True


def human_right_click(control: uia.Control, min_delay: float = 0.1, 
                      max_delay: float = 0.3) -> Tuple[int, int]:
    """
    在控件范围内随机位置右键点击
    
    模拟人类右键点击行为：先移动鼠标到控件附近，然后在控件内随机位置右键点击。
    
    Args:
        control: UIA控件对象
        min_delay: 点击前最小延迟（秒）
        max_delay: 点击前最大延迟（秒）
        
    Returns:
        tuple[int, int]: 实际点击的坐标
    """
    rect = control.BoundingRectangle
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    
    target_x, target_y = _random_offset_within_bounds(center_x, center_y, width, height)
    
    human_move_to(target_x, target_y)
    
    human_sleep(min_delay, max_delay)
    
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, target_x, target_y, 0, 0)
    time.sleep(random.uniform(0.03, 0.07))
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, target_x, target_y, 0, 0)
    
    return target_x, target_y


def human_dbl_click(control: uia.Control, min_delay: float = 0.1, 
                    max_delay: float = 0.3) -> Tuple[int, int]:
    """
    在控件范围内随机位置双击
    
    模拟人类双击行为，两次点击之间有自然的间隔。
    
    Args:
        control: UIA控件对象
        min_delay: 第一次点击前最小延迟（秒）
        max_delay: 第一次点击前最大延迟（秒）
        
    Returns:
        tuple[int, int]: 实际点击的坐标
    """
    rect = control.BoundingRectangle
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    
    target_x, target_y = _random_offset_within_bounds(center_x, center_y, width, height)
    
    human_move_to(target_x, target_y)
    
    human_sleep(min_delay, max_delay)
    
    double_click_interval = random.uniform(0.15, 0.25)
    
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
    time.sleep(random.uniform(0.03, 0.07))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
    
    time.sleep(double_click_interval)
    
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
    time.sleep(random.uniform(0.03, 0.07))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
    
    return target_x, target_y
