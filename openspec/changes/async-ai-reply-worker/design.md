# Design

## 背景

当前 AI 回复完全嵌入主线程：

```
主线程 main()
  └─ chatlog_listen_loop ── chatlog_process_message
       └─ _chatlog_send_ai
            ├─ 关键字/统计/记忆/上下文    (无阻塞)
            ├─ app.chat(...)            (秒级阻塞 ←这是要移的)
            └─ [task_queue.submit send_msg] (已异步✓)
```

目标：把「`app.chat()` 生成」这一步从主线程挪到独立 worker，
保留「消息发送仍走 task_queue」的现状。

## 并发模型：方案 A（单 worker 顺序 + 每会话超时/降级）

```
主循环(派发线程)                      AI Worker(独立线程)
  收到消息 ──▶ 入 AI 队列 ──────────▶ worker: 顺序取一条
                                             ├─ 读 context/prompt
                                             ├─ app.chat()   ← 超时/降级在 worker 内
                                             ├─ 发送: task_queue.submit(send_msg)
                                             └─ 回写 bind_reply/计数

  ┌──────────────── main() 永不触碰 AI ────────────────┐
  │ 即使 AI 卡 60s，主循环仍在每 chatlog_polling_interval │
  │ 秒 tick，离线检测/新好友/定时/朋友圈照常             │
  └────────────────────────────────────────────────────┘
```

### 为什么选 A 而非 per-会话线程池

wxautox4 驱动的微信是**同一个客户端进程/UI**。如果多个 AI worker 各自并行，
后续 `task_queue` 里 `SendMsg` 仍会集中到同一微信 UI —— 并无并发收益，
反而引入 UI 踩踏和顺序错乱。A 方案的 worker 保持全局单线程串行，
只在「worker 线程」内部做 AI 调用，把阻塞从主线程搬走即可。

局限：多条待回复消息仍是顺序处理，不追求并行吞吐 —— 这是有意为之，
符合 Non-Goals。

## 结构

新增 `core/ai_worker.py`（或在 `message_handler` 内部按单例持有队列），
最贴合现状的做法是加一个薄的 `AIWorker`：

```
class AIWorker:
    def __init__(self, bot):
        self.queue = Queue()
        self.thread = Thread(daemon=True)

    def enqueue(self, job):     # 主线程调用, 非阻塞
        self.queue.put(job)

    def _loop(self):            # worker 线程
        while True:
            job = self.queue.get()
            try: self._process(job)
            except: 记错误日志
```

### job 内容与「跳过条件」前置

由于 AI 之前还会做**关键字应答 / chat_listen_only / 人工确认**这些「根本不用调 AI」的分支，
设计上**把可快速判断的跳过逻辑保留在主线程（派发侧）**，只有真正需要"调模型+生成"的
情况才入队。这样：

- 关键字命中：主线程直接 `task_queue.submit(send)`，不进 AI worker。
- `chat_listen_only`：主线程直接标记处理完成。
- `chat_reply_confirm_switch`：主线程入待确认队列即可。
- 其余（真需要 AI 的）：入队，由 worker 调模型 + 拆分 + 分片提交发送 + 计数。

### 超时/降级语义

- worker 内给 `app.chat()` 套通用 `timeout`（若 api 层未内置超时，则用线程 join/timeout 或
  requests 层超时），超时视为该条失败，落入 `api_error_reply` 固定回复路径
  （沿用现有 `message_handler` 的失败处理语义）。
- 单条失败只记日志 + 计数，不向上抛，不影响队列剩余任务。

### 与既有发送链路的衔接

`app.chat()` 之后的一切（split 分段、`split_long_text`、分段回调链、`task_queue.submit(send_msg)、
`bind_reply`/`set_message_status`/`msg_replied_count`）**原样保留**，只是执行上下文从
「主线程」变为「worker 线程」。需确认这些调用对新线程安全（主要看 `message_store` /
`reply_count_store` 是否线程安全 —— 它们已有锁，见 message_store 的 `_pending_lock` /
`_locks`，基本安全）。

## 关键风险

1. **线程安全**：`bot.msg_replied_count`、`message_store`、`memory_manager` 被两个线程触碰。
   需逐一确认已加锁或改为原子操作；`msg_replied_count` 这类计数器目前直接 `+= 1`，
   在多线程下需加锁或在 worker 内单点更新。
2. **顺序保真**：同一会话内多条消息的顺序。方案 A 靠 worker 串行天然保序，但若主线程
   派发顺序有 jitter 需注意 —— 暂依赖 worker FIFO。
3. **回调上下文**：任务完成的回调（`bind_reply`）现在由 worker 线程触发，需确认与
   task_queue 的线程模型的配合无竞态。

## 暂不做（留给后续 phase）

- task_queue 的 Redis lrange 全量扫描（P1）。
- message_store 双写简化（P1）。
- web_server 拆 blueprint（P2）。
- wxbot_core 转发层精简（P2）。
- 版本号一处化 / 测试框架（P3）。