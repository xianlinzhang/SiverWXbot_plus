# Tasks

> 全部改动跑 `python web_server.py` → 面板「启动机器人」验证（无 pytest）。

## 1. 新增 AIWorker（core/ai_worker.py）

- [x] 创建 `core/ai_worker.py`，`AIWorker` 类：带 `queue.Queue` + daemon worker 线程。
- [x] 提供 `enqueue(job)`（非阻塞入队）与 worker 内部 `_loop` / `_process`。
- [x] `_process` 内对 AI 调用包通用超时语义（先确认 `ai_api` 层是否已内置超时；若无，signature 覆盖或 requests/join 超时），超时/异常落入既有 `api_error_reply` 路径。
  - 实测：`ai_api` 各 SDK 已在 requests 层设 `timeout`（OpenAI 30s、Dus/GPT 600s、Claude/GPT stream 600s）；仅 Dify `requests.post` 无超时，已补 `timeout=120`。
- [x] worker 单条异常只记日志，不中断循环。

## 2. 将 AI 生成从监听线程解耦（core/message_handler.py + core/chatlog_manager.py）

- [x] 定位所有同步 `api.chat(...)` 调用点
      （message_handler.py:232/241/248/251、chatlog_manager.py:352/361/369/372、message_handler 中群组路径）。
- [x] 重构 `_chatlog_send_ai`：把「关键字 / chat_listen_only / chat_reply_confirm」这些**无需调 AI** 的分支保留在派发侧（主线程）快速处理；仅真正需要"调模型"的生成部分改为 `enqueue(...)`。
- [x] 确认群聊路径同样走 AIWorker（chatlog_manager 群组分支 + message_handler 非 chatlog 群组分支）。
- [x] 拆分（split_long_text / 分段回调链）与发送提交移入 worker 内执行。

## 3. 线程安全加固

- [x] 核对 `WXBot.msg_replied_count`、`msg_received_count` 等计数器在多线程下改为加锁更新或 worker 内单点更新。
  - 新增 `WXBot._incr_replied()` / `_incr_received()`（`_count_lock`）；`core/message_handler.py`、`chatlog_manager.py` 中所有计数自增已改用这些方法。
- [x] 核对 `message_store` / `reply_count_store` / `memory_manager` 共享访问的锁覆盖；缺锁则补。
  - 这些模块均已自带锁（message_store `_locks`/`_pending_lock`、reply_count_store 各自锁）；AI 生成在 worker 单线程内顺次执行，未新增并发写 UI。

## 4. 超时/降级兜底

- [x] 确保 AI 超时/异常不会卡死 worker，且回到固定回复语义。
- [x] 错误日志含 task/chat 上下文，便于定位（P0 的错误可见性基础）。
  - AIWorker 每任务带 `context`（会话名），异常日志含 context + traceback。

## 5. 验证

- [ ] `python web_server.py` 启动，面板启动机器人，正常聊天回归：关键字应答、chat_listen_only、图片识别、拆分回复、memory 增强均不回退。
  - 已做：模块导入 smoke、AIWorker FIFO/非阻塞/stop 行为测试、`_send_reply_segments` 分段提交 + 计数测试均通过。
  - 待真机：需真实微信登录 + 面板手动跑（本环境无微信）。
- [ ] 构造「慢 AI」场景（指向故意延迟/不通接口），确认主循环 tick 不被拖长、离线/新好友/定时照常、慢接口只影响对应会话。
- [ ] 观察面板日志无异常堆栈、`msg_replied_count` 语义正确。