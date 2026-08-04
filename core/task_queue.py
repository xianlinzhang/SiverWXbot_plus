import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .redis_manager import RedisManager

# ZSET score 编码：priority * SCORE_PRIO_BASE + submit 序号，保证同优先级 FIFO、
# 不同优先级按数值小优先，且同分不相互覆盖。
SCORE_PRIO_BASE = 10 ** 13


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
    retry_count: int = 0
    max_retries: Optional[int] = None
    next_retry_at: Optional[float] = None
    dead_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'id': self.id,
            'type': self.type,
            'priority': self.priority,
            'status': self.status,
            'params': self.params,
            'result': self.result,
            'error': self.error,
            'create_time': self.create_time,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'next_retry_at': self.next_retry_at,
            'dead_at': self.dead_at,
        }
        if result['result'] is not None:
            if hasattr(result['result'], 'to_dict'):
                result['result'] = result['result'].to_dict()
            elif isinstance(result['result'], (dict, list)):
                pass
            elif callable(result['result']):
                result['result'] = str(result['result'])
            else:
                result['result'] = str(result['result'])
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WXTask':
        return cls(**data)


class TaskQueue:
    TASK_TYPES = ['send_msg', 'send_moments', 'like_moments', 'pass_friend', 'send_file', 'ai_reply', 'ai_pregenerate']

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
        self._delayed_key = f'wxbot:{self.wx_id}:tasks:delayed'
        self._dead_key = f'wxbot:{self.wx_id}:tasks:dead'

        # 重试配置（来自 config_manager，热重载）
        self._max_retries = 3
        self._retry_interval = 30
        self._retry_factor = 2
        self._reload_retry_config()

        # 提交序号（同一进程内单调递增），用于 ZSET score 唯一化实现同优先级 FIFO
        self._submit_seq = 0

        self._task_handlers = {
            'send_msg': self._handle_send_msg,
            'send_moments': self._handle_send_moments,
            'like_moments': self._handle_like_moments,
            'pass_friend': self._handle_pass_friend,
            'send_file': self._handle_send_file,
            'ai_reply': self._handle_ai_reply,
            'ai_pregenerate': self._handle_ai_pregenerate,
        }

        self._migrate_pending_list_to_zset()
        self._start_worker()

    def _reload_retry_config(self) -> None:
        """从配置管理器加载重试参数（支持运行时热重载）"""
        try:
            cfg = getattr(self.bot, 'config_manager', None)
            if cfg is None:
                cfg = getattr(self.bot, 'config', None)
            if cfg is not None:
                self._max_retries = max(0, int(getattr(cfg, 'task_queue_max_retries', 3)))
                self._retry_interval = max(1, int(getattr(cfg, 'task_queue_retry_interval', 30)))
                self._retry_factor = max(1, float(getattr(cfg, 'task_queue_retry_factor', 2)))
        except Exception as e:
            self._logger.warning(f"Load retry config failed, use defaults: {e}")

    def _enqueue_pending(self, task: WXTask) -> None:
        """将任务按优先级+FIFO 序号写入 pending ZSET"""
        with self._lock:
            self._submit_seq += 1
            score = task.priority * SCORE_PRIO_BASE + self._submit_seq
        self.redis.zadd(self._pending_key, {task.id: score})

    def _migrate_pending_list_to_zset(self) -> None:
        """
        将旧的 List 结构 pending 队列一次性迁移为 ZSET。

        - 兼容字段 `_pending_key` 不变，仅结构迁移。
        - 若 pending key 已是 ZSET / 不存在 / Redis fallback 存储无法判断，则跳过。
        - 迁移失败（如 Redis 不可用）容忍，从零开始。
        """
        try:
            key_type = self.redis.type(self._pending_key)
            if key_type and key_type != 'list':
                return
            if not key_type:
                return
        except Exception as e:
            self._logger.warning(f"Pending queue migration: skip type check ({e})")
            return

        try:
            old_items = self.redis.lrange(self._pending_key, 0, -1) or []
            if not isinstance(old_items, list) or not old_items:
                return
            mapping = {}
            for item in reversed(old_items):
                if not isinstance(item, dict):
                    continue
                task_id = item.get('task_id')
                if not task_id:
                    continue
                priority = item.get('priority', 5)
                try:
                    priority = int(priority)
                except (TypeError, ValueError):
                    priority = 5
                self._submit_seq += 1
                mapping[task_id] = priority * SCORE_PRIO_BASE + self._submit_seq
            if mapping:
                # Redis 不允许对 List 类型 key 直接 zadd，需先删除旧 List
                self.redis.delete(self._pending_key)
                self.redis.zadd(self._pending_key, mapping)
                self._logger.info(f"Pending queue migrated from List to ZSET: {len(mapping)} tasks")
        except Exception as e:
            self._logger.warning(f"Pending queue migration failed, starting fresh: {e}")

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

        self._enqueue_pending(task)

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
            if task.status == 'completed':
                success_count += 1
            elif task.status == 'failed':
                fail_count += 1

        return {
            'pending_count': pending_count,
            'current_task': current_task.to_dict() if current_task else None,
            'dead_count': self.get_dead_tasks_count(),
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
        pending_ids = self.redis.zrange(self._pending_key, 0, -1, withscores=True) or []
        if not isinstance(pending_ids, list):
            pending_ids = []

        tasks = []
        for item in pending_ids:
            task_id = item[0] if isinstance(item, tuple) else item
            if isinstance(task_id, bytes):
                task_id = task_id.decode('utf-8')
            if not task_id:
                continue
            task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
            if task_data and task_data.get('status') == 'pending':
                tasks.append(WXTask.from_dict(task_data))

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
            if isinstance(task_id, bytes):
                task_id = task_id.decode('utf-8')
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

        self.redis.zrem(self._pending_key, task_id)

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
            self.redis.zrem(self._pending_key, task.id)

        self._logger.info(f"Queue cleared, {count} tasks cancelled")
        return count

    def _worker_loop(self) -> None:
        """工作线程主循环，单线程串行执行任务"""
        while self._running:
            try:
                self._reload_retry_config()
                self._promote_due_delayed()
                task = self._fetch_next_task()
                if task:
                    self._execute_task(task)
                else:
                    time.sleep(1)
            except Exception as e:
                self._logger.error(f"Worker loop error: {e}")
                time.sleep(5)

    def _fetch_next_task(self) -> Optional[WXTask]:
        """获取下一个待执行任务（ZSET 取最低 score 一条，即最高优先级）"""
        ids = self.redis.zrangebyscore(self._pending_key, 0, '+inf', start=0, num=1)
        if not ids:
            return None

        task_id = ids[0]
        self.redis.zrem(self._pending_key, task_id)

        task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
        if not task_data or task_data.get('status') != 'pending':
            return None

        return WXTask.from_dict(task_data)

    def _execute_task(self, task: WXTask) -> None:
        """执行任务，失败时按配置重试，重试耗尽进入死信队列"""
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
            task.retry_count += 1
            max_retries = task.max_retries if task.max_retries is not None else self._max_retries
            if max_retries > 0 and task.retry_count <= max_retries:
                task.status = 'pending'
                interval = self._retry_interval * (self._retry_factor ** (task.retry_count - 1))
                task.next_retry_at = time.time() + interval
                self._logger.info(
                    f"Task failed, will retry {task.retry_count}/{max_retries} "
                    f"in {interval}s: {task.id} - {e}"
                )
            else:
                task.status = 'failed'
                task.dead_at = time.time()
                self._logger.error(f"Task failed permanently: {task.id} - {e}")
        finally:
            task.end_time = datetime.now().isoformat()
            self._update_task(task)
            self.redis.delete(self._current_key)
            if task.status == 'pending':
                self._schedule_retry(task)
            else:
                self._add_to_history(task)
                if task.status == 'failed':
                    self._add_to_dead(task)

        if task.status == 'pending':
            return

        callback = None
        with self._lock:
            callback = self._callbacks.pop(task.id, None)

        if callback:
            try:
                success = task.status == 'completed'
                callback(success, task.result, task.params)
            except Exception as e:
                self._logger.error(f"Callback error for task {task.id}: {e}")

    def _schedule_retry(self, task: WXTask) -> None:
        """将待重试任务放入延迟队列（ZSET score=下次执行时间戳）"""
        self.redis.zadd(self._delayed_key, {task.id: task.next_retry_at or time.time()})

    def _promote_due_delayed(self) -> None:
        """将延迟队列中已到期的任务重新加入 pending 队列"""
        now = time.time()
        due_ids = self.redis.zrangebyscore(self._delayed_key, 0, now, start=0, num=50) or []
        for task_id in due_ids:
            if isinstance(task_id, bytes):
                task_id = task_id.decode('utf-8')
            self.redis.zrem(self._delayed_key, task_id)
            task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
            if not task_data or task_data.get('status') != 'pending':
                continue
            task_data['next_retry_at'] = None
            self.redis.set(f'{self._detail_prefix}{task_id}', task_data)
            self._enqueue_pending(WXTask.from_dict(task_data))
            self._logger.info(f"Task retry due, re-enqueued: {task_id}")

    def _add_to_dead(self, task: WXTask) -> None:
        """将耗尽重试次数的失败任务加入死信队列"""
        self.redis.zadd(self._dead_key, {task.id: task.dead_at or time.time()})

    def get_dead_tasks(self, limit: int = 50) -> List[WXTask]:
        """
        获取死信队列任务（重试耗尽后进入，可从面板恢复或丢弃）

        Args:
            limit: 返回数量限制，默认50

        Returns:
            List[WXTask]: 死信任务列表，按进入时间倒序排列
        """
        dead_raw = self.redis.zrange(self._dead_key, 0, -1, withscores=True) or []
        dead_raw = sorted(dead_raw, key=lambda x: x[1], reverse=True)
        if limit > 0:
            dead_raw = dead_raw[:limit]

        tasks = []
        for task_id, _ in dead_raw:
            if isinstance(task_id, bytes):
                task_id = task_id.decode('utf-8')
            task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
            if task_data and task_data.get('status') == 'failed':
                tasks.append(WXTask.from_dict(task_data))
        return tasks

    def get_dead_tasks_count(self) -> int:
        """获取死信队列中的任务数量"""
        return int(self.redis.zcard(self._dead_key) or 0)

    def recover_task(self, task_id: str) -> bool:
        """
        从死信队列恢复任务，重新提交到待执行队列（重试次数清零）

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否恢复成功
        """
        task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
        if not task_data or task_data.get('status') != 'failed':
            return False

        task = WXTask.from_dict(task_data)
        task.status = 'pending'
        task.retry_count = 0
        task.error = None
        task.next_retry_at = None
        task.dead_at = None
        task.start_time = None
        task.end_time = None
        self._update_task(task)

        self.redis.zrem(self._dead_key, task_id)
        self._enqueue_pending(task)
        self._logger.info(f"Task recovered from dead queue: {task_id}")
        return True

    def discard_task(self, task_id: str) -> bool:
        """
        从死信队列丢弃任务（删除死信标记，保留历史记录）

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否丢弃成功
        """
        task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
        if not task_data or task_data.get('status') != 'failed':
            return False

        self.redis.zrem(self._dead_key, task_id)
        self._logger.info(f"Task discarded from dead queue: {task_id}")
        return True

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
        if isinstance(task_id, bytes):
            task_id = task_id.decode('utf-8')
        task_data = self.redis.get(f'{self._detail_prefix}{task_id}')
        if task_data:
            return WXTask.from_dict(task_data)
        return None

    @staticmethod
    def _result_is_success(result) -> bool:
        """判断界面操作结果是否成功。兼容 wxautox4 的 WxResponse(dict, status 成功/失败/错误) 与布尔/历史 dict 格式。"""
        if result is True:
            return True
        if result is False or result is None:
            return False
        if isinstance(result, dict):
            status = str(result.get("status", "")).strip()
            if status in ("成功", "success", "ok", "true", "已完成"):
                return True
            if status in ("失败", "错误", "error", "fail", "failed", "false"):
                return False
            # 兼容旧格式 {"code": 0} 成功 / {"success": bool}
            if result.get("code") == 0:
                return True
            if result.get("success") is True:
                return True
            if result.get("success") is False:
                return False
            # WxResponse.__bool__ 已按 status==成功 判定
            try:
                return bool(result)
            except Exception:
                return True
        return bool(result)

    def _handle_send_msg(self, params: Dict[str, Any]) -> Any:
        """处理发送消息任务；SendMsg 返回失败时抛异常（触发重试 → 死信队列）"""
        who = params.get('who')
        msg = params.get('msg')
        if not who or not msg:
            raise ValueError("send_msg requires 'who' and 'msg' params")
        result = self.bot.wx.SendMsg(who=who, msg=msg)
        if not self._result_is_success(result):
            raise RuntimeError(f"send_msg failed ({who}): {result}")
        return result

    def _handle_send_moments(self, params: Dict[str, Any]) -> Any:
        """处理发送朋友圈任务"""
        text = params.get('text', '')
        images = params.get('images', [])
        privacy = params.get('privacy', 'public')
        tags = params.get('tags', [])
        if not self._wait_mouse_idle():
            return {"status": "失败", "message": "等待鼠标空闲超时，用户仍在操作，已放弃本次发布"}
        try:
            self.bot.wx.Show()
        except Exception:
            pass
        return self.bot.wx.SendMoments(text=text, images=images, privacy=privacy, tags=tags)

    def _wait_mouse_idle(self, max_wait: Optional[float] = None) -> bool:
        """
        发布朋友圈前等待鼠标空闲，避免与真人鼠标操作争抢。

        开启开关时：持续采样鼠标位置，若鼠标在某位置停留 >= idle 秒则视为空闲；
        期间鼠标一旦移动则重置计时；超过 max_wait 秒仍未空闲则放弃等待（返回 False）。

        Returns:
            bool: True=鼠标已空闲可执行操作；False=等待超时（调用方仍可继续，但建议放弃）
        """
        cfg = getattr(self.bot, 'config_manager', None)
        if cfg is None:
            cfg = getattr(self.bot, 'config', None)
        enabled = bool(getattr(cfg, 'moments_wait_mouse_idle_switch', True))
        idle_need = float(getattr(cfg, 'moments_mouse_idle_seconds', 2))
        if max_wait is None:
            max_wait = float(getattr(cfg, 'moments_mouse_max_wait_seconds', 60))
        if not enabled or max_wait <= 0:
            return True

        try:
            from wxautox4 import uia
            get_pos = uia.GetCursorPos
        except Exception:
            return True

        start = time.time()
        last_x, last_y = get_pos()
        last_move = start
        while time.time() - start < max_wait:
            try:
                x, y = get_pos()
            except Exception:
                break
            if (x, y) != (last_x, last_y):
                last_x, last_y = x, y
                last_move = time.time()
            if time.time() - last_move >= idle_need:
                self._logger.info("鼠标已空闲 %.1fs，开始发布朋友圈", time.time() - last_move)
                return True
            time.sleep(0.05)
        self._logger.warning(
            "等待鼠标空闲超时（%.0fs），用户可能仍在操作，放弃本次自动发布", max_wait
        )
        return False

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

    def _handle_ai_reply(self, params: Dict[str, Any]) -> Any:
        """
        处理 AI 回复任务（生成 + 发送）。
        AI 接口失败抛 AIReplyError → 任务重试 → 重试耗尽 → 死信队列。
        """
        return self.bot.message_handler.ai_reply_task(params)

    def _handle_ai_pregenerate(self, params: Dict[str, Any]) -> Any:
        """
        处理 AI 预生成任务（只生成回复写入待确认记录，不发送）。
        AI 接口失败抛 AIReplyError → 任务重试 → 重试耗尽 → 死信队列（面板可人工恢复）。
        """
        return self.bot.message_handler.ai_pregenerate_task(params)