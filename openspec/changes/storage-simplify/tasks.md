# Tasks

> 全部改动跑 `python web_server.py` → 面板「启动机器人」验证（无 pytest）。

## 1. task_queue 迁移到 ZSET 优先级队列（core/task_queue.py）

- [x] `submit`：由 `lpush(pending, ...)` 改为 `zadd(pending, {task_id: score})`；
      score = `priority * 1e13 + 提交微秒序`（同优先级 FIFO）。
      → 实现 `score = priority * SCORE_PRIO_BASE + self._submit_seq`（进程内单调序号，保证同优先级 FIFO 且同分不覆盖）。
- [x] `_fetch_next_task`：改为 `ZRANGEBYSCORE(pending, 0, +inf, LIMIT 0 1)` 取最高优一条，
     再 `ZREM` 原子移除，随后 `GET` detail 返回；删除原 lrange 全量 + sort + lrem 逻辑。
- [x] `get_pending_tasks`：改用 `ZRANGE`（升序）读取，不再 lrange 全量。
- [x] `cancel_task` / `clear_queue`：改走 `ZREM` / `ZSCAN`+`ZREM`，保留 cancelled 标记语义。
- [x] detail 与 history key（ZSET score=时间）保持不变。
- [x] 启动时对旧 List 结构做一次性迁移（容忍失败从零开始），兼容字段 `_pending_key` 不动。
      → `_migrate_pending_list_to_zset()`，先判 type，List→删建→zadd；失败容忍。
- [x] 保持 `submit` / `get_queue_status` / `cancel_task` / `clear_queue` / handlers 签名不变。

## 2. message_store 读回退收敛（core/message_store.py）

- [x] 新增 `_read_source(chat_name, wxid=None)`：确定会话权威存储位置与权威 key，只读一处。
- [x] `get_all_messages_with_fallback` 改造：先解析权威 key，命中即读；未命中再做一次
      兼容性回退（读历史位置），不再对别名集合逐一探测。
- [x] 明确 Redis 与文件为「同一逻辑数据（primary + 镜像）」而非三份独立副本，写路径统一。
- [x] 与 RedisManager 的 `fallback_redis.json` 层职责理清（设计上收敛，避免三处落盘混乱）。

## 3. 消除 O(n) 更新扫描

- [x] `_redis_update_message`：不再 `lindex` 逐条扫；改用「msg id 自有 status/hash key 承载
      可变域」方案，列表仅追加。
      → 新增 `_get_msg_detail_key`：可变域走独立 detail hash；读路径 `_redis_get_messages`
        overlay detail，最新状态反映到读数。
- [x] `set_message_status` / `bind_reply` / `reject_message` 等可变域写操作改走新索引路径，
      行为与既有 status key 语义一致。
      → bind_reply 的 reply_content/reply_time/reply_id、confirm/reject 的 confirm_status/status 均写入 detail hash。

## 4. 兼容与数据迁移

- [x] 对既有三处落盘（Redis / redis-manager fallback.json / message_store 文件）的历史数据：
      读时尽力兼容命中，不对旧数据做破坏性清理（P1 只收敛，不大动删除）。
      → 兼容性回退保留别名键 + 文件镜像读取；detail hash 未命中时列表本体仍可读（仅可变域可能回退到旧 status key 语义）。

## 5. 验证

- [ ] `python web_server.py` 启动，面板机器人正常私聊/群聊/定时/日志回归（待真机）。
  - 已做：模块导入 / 语法、task_queue FIFO+优先级+取消+清空+迁移 全过（real redis）、message_store 写读更新/绑定回复/确认 unread overlay 全过。
- [ ] Redis 故障模拟（停 Redis）：任务队列与消息读写走 fallback_redis.json，功能可用（待验证，fallback 层已同步新增 zadd/zrem/zrangebyscore/zcard/type 支持）。
- [ ] 回归 `clear_queue` / `cancel_task` / `get_history` / `get_queue_status` 面板表现（tasks 17/18，待真机）。