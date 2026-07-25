import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .redis_manager import RedisManager


@dataclass
class WXTask:
    id: str
    type: str
    priority: int
    status: str
    params: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    create_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    callback: Optional[Callable] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WXTask':
        return cls(**data)


class TaskQueue:
    TASK_TYPES = ['send_msg', 'send_moments', 'like_moments', 'pass_friend', 'send_file']

    def __init__(self, bot):
        self.bot = bot
        self.redis: RedisManager = bot.redis_manager
        self.wx_id = getattr(getattr(bot, 'wx', None), 'nickname', None) or 'default'
        self._logger = logging.getLogger(__name__)
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.RLock()
        self._callbacks: Dict[str, Callable] = {}

        self._pending_key = f'wxbot:{self.wx_id}:tasks:pending'
        self._detail_prefix = f'wxbot:{self.wx_id}:tasks:'
        self._history_key = f'wxbot:{self.wx_id}:tasks:history'
        self._current_key = f'wxbot:{self.wx_id}:tasks:current'

        self._task_handlers = {
            'send_msg': self._handle_send_msg,
            'send_moments': self._handle_send_moments,
            'like_moments': self._handle_like_moments,
            'pass_friend': self._handle_pass_friend,
            'send_file': self._handle_send_file,
        }

        self._start_worker()

    def _start_worker(self) -> None:
        """启动工作线程"""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        self._logger.info("Task queue worker started")

    def _stop_worker(self) -> None:
        """停止工作线程"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
            self._logger.info("Task queue worker stopped")

    def stop(self) -> None:
        """停止任务队列，终止工作线程"""
        self._stop_worker()

    def submit(self, task_type: str, params: Dict[str, Any], priority: int = 5, callback: Optional[Callable] = None) -> str:
        """
        提交任务到队列

        Args:
            task_type: 任务类型，必须是 TASK_TYPES 之一
            params: 任务参数
            priority: 优先级，数值越小优先级越高，默认5
            callback: 任务完成后的回调函数，签名为 callback(success: bool, result: Any, params: Dict[str, Any])

        Returns:
            str: 任务ID

        Raises:
            ValueError: 任务类型不合法
        """
        if task_type not in self.TASK_TYPES:
            raise ValueError(f"Invalid task type: {task_type}, must be one of {self.TASK_TYPES}")

        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        task = WXTask(
            id=task_id,
            type=task_type,
            priority=priority,
            status='pending',
            params=params,
            create_time=now,
        )

        task_data = task.to_dict()

        self.redis.set(f'{self._detail_prefix}{task_id}', task_data)

        if callback:
            with self._lock:
                self._callbacks[task_id] = callback

        priority_data = {'task_id': task_id, 'priority': priority, 'create_time': now}
        self.redis.lpush(self._pending_key, priority_data)

        self._logger.info(f"Task submitted: {task_id} ({task_type}), priority={priority}")
        return task_id

    def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态

        Returns:
            Dict[str, Any]: 队列状态信息，包含待执行数、当前任务、历史统计
        """
        pending_count = len(self.get_pending_tasks())
        current_task = self._get_current_task()
        history = self.get_history(limit=0)
        total_executed = len(history)

        success_count = 0
        fail_count = 0
        for task in history:
            if task.get('status') == 'completed':
                success_count += 1
            elif task.get('status') == 'failed':
                fail_count += 1

        return {
            'pending_count': pending_count,
            'current_task': current_task.to_dict() if current_task else None,
            'history_stats': {
                'total': total_executed,
                'success': success_count,
                'failed': fail_count,
            },
        }

    def get_pending_tasks(self) -> List[WXTask]:
        """
        获取待执行任务列表

        Returns:
            List[WXTask]: 待执行任务列表，按优先级排序（高优先级在前）
        """
        pending_raw = self.redis.get(self._pending_key) or []
        if not isinstance(pending_raw, list):
            pending_raw = []

        tasks = []
        for item in pending_raw:
            task_id = item.get('task_id')
            if task_id:
                task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
                if task_data and task_data.get('status') == 'pending':
                    tasks.append(WXTask.from_dict(task_data))

        tasks.sort(key=lambda t: t.priority)
        return tasks

    def get_history(self, limit: int = 50) -> List[WXTask]:
        """
        获取历史任务

        Args:
            limit: 返回数量限制，默认50

        Returns:
            List[WXTask]: 历史任务列表，按时间倒序排列
        """
        history_raw = self.redis.zrange(self._history_key, start=0, end=-1, withscores=True)
        history_raw = sorted(history_raw, key=lambda x: x[1], reverse=True)

        if limit > 0:
            history_raw = history_raw[:limit]

        tasks = []
        for task_id, _ in history_raw:
            task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
            if task_data:
                tasks.append(WXTask.from_dict(task_data))

        return tasks

    def cancel_task(self, task_id: str) -> bool:
        """
        取消指定待执行任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否取消成功
        """
        task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
        if not task_data or task_data.get('status') != 'pending':
            return False

        task_data['status'] = 'cancelled'
        task_data['end_time'] = datetime.now().isoformat()
        self.redis.set(f'{self._detail_prefix}{task_id}', task_data)

        pending_raw = self.redis.get(self._pending_key) or []
        if isinstance(pending_raw, list):
            new_pending = [item for item in pending_raw if item.get('task_id') != task_id]
            self.redis.set(self._pending_key, new_pending)

        self._logger.info(f"Task cancelled: {task_id}")
        return True

    def clear_queue(self) -> int:
        """
        清空队列，移除所有待执行任务

        Returns:
            int: 移除的任务数量
        """
        pending_tasks = self.get_pending_tasks()
        count = len(pending_tasks)

        for task in pending_tasks:
            task.status = 'cancelled'
            task.end_time = datetime.now().isoformat()
            self.redis.set(f'{self._detail_prefix}{task.id}', task.to_dict())

        self.redis.delete(self._pending_key)
        self._logger.info(f"Queue cleared, {count} tasks cancelled")
        return count

    def _worker_loop(self) -> None:
        """工作线程主循环，单线程串行执行任务"""
        while self._running:
            try:
                task = self._fetch_next_task()
                if task:
                    self._execute_task(task)
                else:
                    time.sleep(1)
            except Exception as e:
                self._logger.error(f"Worker loop error: {e}")
                time.sleep(5)

    def _fetch_next_task(self) -> Optional[WXTask]:
        """获取下一个待执行任务"""
        pending_raw = self.redis.get(self._pending_key) or []
        if not isinstance(pending_raw, list) or not pending_raw:
            return None

        pending_with_tasks = []
        for item in pending_raw:
            task_id = item.get('task_id')
            if task_id:
                task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
                if task_data and task_data.get('status') == 'pending':
                    pending_with_tasks.append((item['priority'], task_data))

        if not pending_with_tasks:
            return None

        pending_with_tasks.sort(key=lambda x: x[0])
        task_data = pending_with_tasks[0][1]

        new_pending = [item for item in pending_raw if item.get('task_id') != task_data['id']]
        self.redis.set(self._pending_key, new_pending)

        return WXTask.from_dict(task_data)

    def _execute_task(self, task: WXTask) -> None:
        """执行任务"""
        task.start_time = datetime.now().isoformat()
        task.status = 'running'
        self._update_task(task)
        self.redis.set(self._current_key, task.id)

        self._logger.info(f"Starting task: {task.id} ({task.type})")

        try:
            handler = self._task_handlers.get(task.type)
            if not handler:
                raise ValueError(f"No handler for task type: {task.type}")

            result = handler(task.params)
            task.result = result
            task.status = 'completed'
            self._logger.info(f"Task completed: {task.id}")
        except Exception as e:
            task.error = str(e)
            task.status = 'failed'
            self._logger.error(f"Task failed: {task.id} - {e}")
        finally:
            task.end_time = datetime.now().isoformat()
            self._update_task(task)
            self.redis.delete(self._current_key)
            self._add_to_history(task)

        callback = None
        with self._lock:
            callback = self._callbacks.pop(task.id, None)

        if callback:
            try:
                success = task.status == 'completed'
                callback(success, task.result, task.params)
            except Exception as e:
                self._logger.error(f"Callback error for task {task.id}: {e}")

    def _update_task(self, task: WXTask) -> None:
        """更新任务详情"""
        self.redis.set(f'{self._detail_prefix}{task.id}', task.to_dict())

    def _add_to_history(self, task: WXTask) -> None:
        """将任务添加到历史记录"""
        timestamp = datetime.now().timestamp()
        self.redis.zadd(self._history_key, {task.id: timestamp})

    def _get_current_task(self) -> Optional[WXTask]:
        """获取当前正在执行的任务"""
        task_id = self.redis.get(self._current_key)
        if not task_id:
            return None
        task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
        if task_data:
            return WXTask.from_dict(task_data)
        return None

    def _handle_send_msg(self, params: Dict[str, Any]) -> Any:
        """处理发送消息任务"""
        who = params.get('who')
        msg = params.get('msg')
        if not who or not msg:
            raise ValueError("send_msg requires 'who' and 'msg' params")
        return self.bot.wx.SendMsg(who=who, msg=msg)

    def _handle_send_moments(self, params: Dict[str, Any]) -> Any:
        """处理发送朋友圈任务"""
        text = params.get('text', '')
        images = params.get('images', [])
        privacy = params.get('privacy', 'public')
        tags = params.get('tags', [])
        return self.bot.wx.SendMoments(text=text, images=images, privacy=privacy, tags=tags)

    def _handle_like_moments(self, params: Dict[str, Any]) -> Any:
        """处理点赞朋友圈任务"""
        moment_id = params.get('moment_id')
        if not moment_id:
            raise ValueError("like_moments requires 'moment_id' param")
        return self.bot.wx.LikeMoment(moment_id=moment_id)

    def _handle_pass_friend(self, params: Dict[str, Any]) -> Any:
        """处理通过好友请求任务"""
        friend_name = params.get('name')
        remark = params.get('remark', '')
        tags = params.get('tags')
        if not friend_name:
            raise ValueError("pass_friend requires 'name' param")

        NewFriends = self.bot.wx.GetNewFriends(acceptable=True)
        for new in NewFriends:
            if new.name == friend_name:
                return new.accept(remark=remark, tags=tags)
        raise ValueError(f"Friend request not found: {friend_name}")

    def _handle_send_file(self, params: Dict[str, Any]) -> Any:
        """处理发送文件任务"""
        who = params.get('who')
        filepath = params.get('filepath')
        if not who or not filepath:
            raise ValueError("send_file requires 'who' and 'filepath' params")
        return self.bot.wx.SendFiles(who=who, filepath=filepath)