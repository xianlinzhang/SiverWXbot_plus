# Proposal

## Problem

P1 聚焦两条「每条消息成本」过重的路径：

### 1) message_store 读路径存在 O(n) 扫描与多层回退

`MessageStore`（`core/message_store.py`, 1304 行）同一个会话的消息存在**两个后端**：
- Redis（主）：消息列表 key + 每消息 status key（`_redis_save_message` / `_redis_get_messages`）
- 文件（`_get_message_path` 下的 JSON，降级时用）

但实际写入是「二选一」而非「双写」：`save_message`（:624）Redis 成功就走 Redis，失败才落文件。
问题是**读路径的开销**：

- `_redis_update_message`（:495）：用 `lindex(key, i)` 从 0..length 逐条扫列表找 id，O(n)。
- `_redis_like` etc 多个读 API 都依赖 `get_all_messages` → 先 lrange 全量，未命中再落文件。
- `get_all_messages_with_fallback`（:709）会按 chat_name / wxid / remark / userName 枚举
  多个可能的 key 逐条探测（`_get_all_possible_keys` :683），Key 探测次数随会话别名数量线性膨胀。

2) RedisManager（`core/redis_manager.py`）在 Redis 不可用时已自动降级到 `fallback_redis.json`
   （内存 dict + 文件）。**这层 fallback 与 message_store 的文件层功能重叠**，形成「双 fallback，
   谁在管」的混乱：消息可能落在 Redis、Redis-manager fallback 文件、message_store 文件三处之一，
   读回退链难以证明正确。

### 2) task_queue 用 List 当队列，但每次都全量扫描 + 手动排序

`TaskQueue`（`core/task_queue.py`）把待办存成 Redis List，work loop 每 tick：
`lrange(pending, 0, -1)` 拉**全量**（:287），对每条**再 get detail**（:295），再 `sort` 按 priority
（:302），选中最低的一条 `lrem`。这等于把 priority queue 用「List + 每轮扫描重排」实现：

```
每 tick:  lrange 全量 + n× GET detail + sort + lrem
= 取一条任务要做 O(n) 次 Redis round-trip, 队列越大越慢, 高频场景积压放大
```

`get_pending_tasks`（:186）同样全量扫描用于状态面板轮询。

## 目标

1. `message_store` 读路径消灭 O(n) 的 Redis 更新扫描，回退语义收敛到单一清晰来源。
2. `task_queue` 用**真优先级队列语义**（如 Redis ZSET score=priority）替代「List+全量重扫」，
   取一条任务成本从 O(n) 降到 O(log n)。
3. 保持对外行为不变：`save_message` 返回值、消息状态、pending confirm、get_history 等接口语义不回退。

## 非目标

- 不在本 change 做 AI worker（那是 P0 `async-ai-reply-worker`）。
- 不把 message_store 改成纯 SQLite 等其他存储（若有此想法是单独 change/arch 决策）。
- 不拆 web_server / wxbot_core 转发层（P2）。
- 不处理 siver_panel（用户明确排除）。

## 验收

- 单独跑 `python web_server.py` 面板启动机器人，正常私聊/群聊/定时任务回归。
- 高频场景（同会话多消息 + 对 busy 微信）不积压，`get_pending_tasks` / 面板任务状态正确。
- Redis 故障模拟（停 Redis）时，消息读写仍可用且语义正确（走收敛后的单一回退源）。