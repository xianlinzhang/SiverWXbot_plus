# Spec: AI 回复异步解耦

能力路径：`ai-reply-async`（delta spec，随 change 归档后可并入主 specs）

## 目的

将「AI 生成」从监听主线程移除，使 AI 接口的延迟/超时不再冻结整个 bot。
消息结构、关键字应答、发送链路等既有语义保持不变。

## ADDED Requirements

### Requirement: 主线程不触碰 AI 网络调用
系统 SHALL 只在收到需要 AI 回复的消息时，将生成任务入队返回（非阻塞），
主循环照常按 `chatlog_polling_interval` tick；任何 AI 调用 MUST NOT 在监听主线程内执行。

#### Scenario: 需要 AI 回复的私聊消息不阻塞主线程
- GIVEN 一个需要 AI 回复的私聊消息
- WHEN 主线程处理该消息
- THEN 主线程立即返回，不等待 AI 响应
- AND AI 生成由独立 worker 异步执行

### Requirement: 单条失败不影响整体
AI worker 处理单条任务失败（异常 / 超时 / 返回空清洗后为空）时，SHALL 只记录错误并落入既有
固定回复（`api_error_reply`）路径，MUST NOT 中断队列其余任务，也不应影响其它模块。

#### Scenario: 一条超时不阻塞队列其余任务
- GIVEN 队列中有任务 A（接口超时）和任务 B（正常）
- WHEN worker 处理 A 失败
- THEN A 记入错误日志并按固定回复处理
- AND B 随后正常处理

### Requirement: 关键字与跳过逻辑仍在派发侧快速短路
系统 SHALL 将无需调 AI 的分支在入队前于派发侧直接处理：
- 关键字命中 → 直接 `task_queue.submit(send)`，不进 AI worker；
- `chat_listen_only` → 直接标记处理完成；
- `chat_reply_confirm_switch` → 直接入待确认队列。

#### Scenario: 关键词命中不触发 AI worker
- GIVEN 消息命中 `keyword_dict` 中的关键词
- WHEN 该消息被接收
- THEN 复用现有关键字回复逻辑
- AND AI worker 不参与
- AND 回复行为与当前一致

### Requirement: worker 内仍走既有发送与回写链路
AI 生成后，拆分（`split_long_text` / 分段回调链）、`task_queue.submit(send_msg)`、
`bind_reply` / `set_message_status` / `msg_replied_count` 计数 SHALL 全部在 worker 内原样执行，
语义与当前一致。

#### Scenario: 完成生成后沿用既有发送链路
- GIVEN 一条消息完成 AI 生成
- WHEN worker 准备发送
- THEN 走既有 task_queue 发送
- AND 成功后 `bind_reply` 回写，`msg_replied_count` 递增

### Requirement: 线程安全
多个模块对象可能被主线程与 worker 线程并行触碰；统计计数更新 SHALL 加锁或单点原子更新，
`message_store` / `memory_manager` 共享访问 MUST 确认其锁覆盖，不足则补齐。

#### Scenario: 双线程并发更新计数不丢计数
- GIVEN 主线程派发消息的同时 worker 线程返回 AI 结果
- WHEN 两者都更新 `msg_replied_count` / `msg_received_count`
- THEN 计数更新具有原子性，无丢失或错乱

## MODIFIED Requirements

无（本 change 不改既有对外协议，只改执行线程模型）。

## 未覆盖（后续 phase）

- task_queue Redis 全量扫描（P1）
- message_store 双写简化（P1）
- web_server 拆 blueprint（P2）
- wxbot_core 转发层精简（P2）
- 版本号一处化 / 测试框架（P3）