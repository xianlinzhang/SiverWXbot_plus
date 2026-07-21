#!/usr/bin/env python3
# Chatlog HTTP API 客户端模块
# 封装 session / chatroom / contact / chatlog 四个核心接口

import time
import json
import requests


class ChatlogError(Exception):
    """Chatlog API 调用异常"""
    pass


class ChatlogClient:
    """
    Chatlog HTTP API 客户端

    封装 Chatlog 服务的四个核心接口，支持超时、重试与错误降级。
    所有接口默认使用 format=json 参数获取结构化数据。

    :param base_url: Chatlog 服务基础 URL，默认 'http://127.0.0.1:5030'
    :param timeout: HTTP 请求超时时间（秒），默认 5
    :param max_retries: 最大重试次数，默认 2
    :param retry_delay: 重试间隔（秒），默认 0.5
    """

    def __init__(self, base_url='http://127.0.0.1:5030', timeout=5, max_retries=2, retry_delay=0.5):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _request(self, endpoint, params=None):
        """
        统一 HTTP 请求封装

        :param endpoint: API 端点路径（如 '/api/v1/session'）
        :param params: 请求参数字典
        :return: 解析后的 JSON 数据（dict 或 list）
        :raises ChatlogError: HTTP 错误或 JSON 解析失败时抛出
        """
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params.setdefault('format', 'json')

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    continue
                raise ChatlogError(f"请求失败 [{url}]: {str(e)}")
            except json.JSONDecodeError as e:
                raise ChatlogError(f"JSON 解析失败 [{url}]: {str(e)}")

    def get_session(self, has_unread=None, ignore_usernames=None):
        """
        获取最近会话列表

        :param has_unread: 是否仅获取有未读消息的会话（1=有未读, 0=无未读, None=全部）
        :param ignore_usernames: 忽略的用户名列表（逗号分隔字符串）
        :return: dict，含 'items' 列表，每项包含：
                 - userName: wxid
                 - nickName: 昵称（可能为空）
                 - content: 最新消息内容
                 - nTime: 最新消息时间（ISO 8601 格式）
                 - UnreadCount: 未读消息数
        :raises ChatlogError: API 调用失败时抛出
        """
        params = {}
        if has_unread is not None:
            params['HasUnreadCount'] = str(has_unread)
        if ignore_usernames:
            params['IgnoreUsernames'] = ignore_usernames
        return self._request('/api/v1/session', params)

    def get_chatroom(self, keyword=None):
        """
        获取群聊列表

        :param keyword: 关键词搜索（可选）
        :return: dict，含 'items' 列表，每项包含群聊信息（userName, nickName 等）
        :raises ChatlogError: API 调用失败时抛出
        """
        params = {}
        if keyword:
            params['keyword'] = keyword
        return self._request('/api/v1/chatroom', params)

    def search_contact(self, keyword=None, is_friend=None):
        """
        搜索联系人

        :param keyword: 关键词（wxid、昵称、备注均可匹配）
        :param is_friend: 是否仅搜索好友（1=是好友, None=全部）
        :return: dict，含 'items' 列表，每项包含：
                 - userName: wxid
                 - alias: 微信号
                 - remark: 备注名
                 - nickName: 昵称
                 - isFriend: 是否好友（bool）
        :raises ChatlogError: API 调用失败时抛出
        """
        params = {}
        if keyword:
            params['keyword'] = keyword
        if is_friend is not None:
            params['isFriend'] = str(is_friend)
        return self._request('/api/v1/contact', params)

    def get_chatlog(self, talker, time=None, sender=None, keyword=None, limit=None, offset=None):
        """
        获取指定聊天对象的历史消息记录

        :param talker: 聊天对象标识（支持 wxid、昵称、备注名）
        :param time: 时间范围（如 '2026-01-01' 或 '2026-01-01~2026-01-31'）
        :param sender: 指定发送者（可选）
        :param keyword: 消息内容关键词搜索（可选）
        :param limit: 返回数量限制（可选）
        :param offset: 偏移量（可选）
        :return: list[dict]，每项包含：
                 - seq: 消息序号（唯一标识，递增）
                 - time: 消息时间（ISO 8601 格式）
                 - talker: 聊天对象 wxid
                 - talkerName: 聊天对象名称
                 - isChatRoom: 是否群聊（bool）
                 - sender: 发送者 wxid
                 - senderName: 发送者名称（可能为空）
                 - isSelf: 是否自己发送（bool）
                 - type: 消息类型（1=文本, 3=图片）
                 - subType: 子类型（通常为 0）
                 - content: 文本内容（图片消息时为空）
                 - contents: 图片消息的文件信息（含 imgfile、md5、thumb）
        :raises ChatlogError: API 调用失败时抛出
        """
        params = {'talker': talker}
        if time:
            params['time'] = time
        if sender:
            params['sender'] = sender
        if keyword:
            params['keyword'] = keyword
        if limit:
            params['limit'] = str(limit)
        if offset:
            params['offset'] = str(offset)
        return self._request('/api/v1/chatlog', params)

    def health_check(self):
        """
        健康检查：验证 Chatlog 服务是否可达

        :return: True 表示服务可达，False 表示不可达
        """
        try:
            self._request('/api/v1/session', {'limit': '1'})
            return True
        except Exception:
            return False
