# Design

## 一、task_queue：List + 全量扫描 → Redis ZSET 优先级队列

### 现状

```
pending List  [taskA(prio5), taskB(prio1), taskC(prio9)]
worker 每 tick:
  lrange 全量 → n× GET detail → sort → 取 prio 最小 → lrem
  = O(n) 次 Redis round-trip / 取一条
```

### 目标

用 `ZSET` 天然表达优先级，key 为任务 id，score = priority（数值小优先）。

```
pending ZSET  {taskA:5, taskB:1, taskC:9}
worker 每 tick 取一条:
  ZRANGEBYSCORE 0 -1 LIMIT 0 1  (取最高优先级一条, O(log n))
  再 ZREM task_id               (原子移除)
  然后 GET detail 执行
  = O(log n) 取一条, 不再全量重扫
```

为保证同优先级 FIFO，score 可编码为 `priority + 小时间分量`（如 `priority * 1e13 + microtime`），
或在 ZSET 内并入 `submit 序号`，使 score 唯一化，避免 ZADD 同分覆盖。

### 迁移与兼容

- `pending` key 从 List 迁移为 ZSET。`submit` 改 `zadd`，`cancel_task` 改 `zrem`，
  `clear_queue` 改 `del` + 批量标记，`get_pending_tasks` 改 `zrange`。
- 对外方法签名不变（`submit` / `get_queue_status` / `get_pending_tasks` / `get_history` /
  `cancel_task` / `clear_queue` / 任务 handler 全保留）。
- 历史仍用独立 ZSET（score=时间）不改；detail 仍用独立 key 不改。
- 兼容已有数据：启动时可尝试把旧 List 迁移为 ZSET（一次性），容忍不可迁移时从零开始。

## 二、message_store：收敛读回退 + 消灭 O(n) 更新扫描

### 发现的关键事实

`RedisManager` 自身在 Redis 不可用时已降级 `fallback_redis.json`（内存 dict + 文件）。
因此 message_store 的「文件后端」其实是**第二层冗余**，导致三处可能落盘、读回退链难证。

设计上不主张在 P1 删除全部文件层（那会更动大），而是**收敛与澄清**：

1. **更新 O(n) 扫描消除**：`_redis_update_message`（:495）不再 `lindex` 逐条扫。
   改为「按 id 维护一张 `id → list 序号/引用` 的索引」，或用独立 status key 承载可变域
   （status/`replied_content` 等），列表本体只追加、不经 in-place 修改。
   若消息列表内也要改内容，则用「msg id → detail」的独立 hash 作为权威，列表仅存 id 序列。

2. **回退源收敛**：明确「Redis 与本地文件是**同一逻辑数据的两份镜像（一个 primary）**，
   而非三个互不知情的副本」。实现一个 `_read_source()` 判定，让所有读 API 走同一入口，
   消除 `get_all_messages_with_fallback` 的多 key 逐条探测爆炸（改为一次解析出会话的
   权威 key 再读，而非枚举别名逐一尝试）。

### 结构不变式

- 对外 API 与返回类型（`MessageRecord` / 状态字符串 / pending confirm）不变。
- `set_message_status` / `bind_reply` / `get_replied_messages` / `search_messages` 语义保留。

## 风险

1. **score 唯一性**：ZSET 同 score 会并行覆盖，务必编码 submit 顺序分量。
2. **回退收敛可能影响既有落盘消息**：已存在三处文件里的老数据，访问需尽力兼容读取
   （读时若新位置未命中，回退查历史位置），写时统一走新位置。迁移/兼容属 tasks 内容。
3. **并发**：worker 单线程（P0 后 AI 也在独立 worker），task_queue ZSET 的 ZREM 是原子的；
   但需确认 web 面板与 worker 同时对 task 的操作不竞态（cancel vs running）。

## 不做（后续 phase）

- AI worker（P0）。
- web_server blueprint（P2）。
- 版本号一处化 / 测试框架（P3）。