import threading
import traceback
from queue import Queue
from typing import Callable, Optional

from logger import log


class AIWorker:
    """
    AI 回复工作线程。

    将「AI 生成 + 发送提交」这类耗时任务从监听主线程挪到独立 daemon 线程，
    使主循环永不阻塞在 AI 网络调用上。单 worker 串行执行（方案 A），
    避免多个线程同时驱动同一微信客户端 UI 造成的踩踏。

    入队对象为一个可调用对象（closure），捕获所需上下文（chat_name/message/msg_id 等），
    由 worker 顺序执行。任务内自行处理业务异常；worker 层兜底捕获，绝不中断循环。
    """

    def __init__(self, name: str = "ai-worker"):
        self._queue: "Queue[Optional[tuple]]" = Queue()
        self._name = name
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动 worker 线程（幂等）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
        self._thread.start()
        log(message=f"AI worker ({self._name}) 已启动")

    def stop(self) -> None:
        """停止 worker 线程（幂等，排队任务自然排空）"""
        if not self._running:
            return
        self._running = False
        try:
            self._queue.put_nowait((None, None))
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log(message=f"AI worker ({self._name}) 已停止")

    def enqueue(self, job: Callable[[], None], context: str = "") -> None:
        """
        非阻塞入队一个任务。

        :param job:     可调用对象，无参，由 worker 顺序执行
        :param context: 任务描述（会话名/消息片段），用于错误日志定位
        """
        self.start()
        self._queue.put((job, context))

    def _loop(self) -> None:
        while self._running:
            try:
                item = self._queue.get(timeout=1)
            except Exception:
                continue
            if item is None:
                break
            job, context = item
            if job is None:
                continue
            try:
                job()
            except Exception as e:
                log(level="ERROR", message=f"AI worker 任务异常 [{context}]: {e}\n{traceback.format_exc()}")
