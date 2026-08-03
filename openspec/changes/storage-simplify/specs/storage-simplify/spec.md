# Spec: 存储路径简化

能力：`storage-simplify`（task_queue 队列语义 + message_store 读回退收敛）

## 目的

把「取一条待办任务」从 O(n) 全量扫描降为 O(log n)，并把消息读写回退链收敛为单一清晰
来源，降低每条消息成本，缓解高频/多会话积压。

## ADDED Requirements

### Requirement: task_queue 待办用优先级队列语义
系统 SHALL 用 Redis ZSET（score=优先级+提交序）承载待办任务，取一条任务 MUST 通过
`ZRANGEBYSCORE` + `ZREM`，而不得再对 List 做 `lrange(0,-1)` 全量扫描 + 手动 sort。

#### Scenario: 从待办取最高优任务
- GIVEN 待办队列中有任务 A(prio 1)、B(prio 5)、C(prio 9)
- WHEN worker 取下一条任务
- THEN 返回 A 并从队列原子移除
- AND 本次只返回最高优一条，成本为 O(log n)

#### Scenario: 取消与清空仍有效
- GIVEN 待办中有任务 X
- WHEN `cancel_task(X)` 被调用
- THEN X 从待办移除并标记 cancelled
- WHEN `clear_queue()` 被调用
- THEN 全部待办移除并标记

### Requirement: 同优先级保持先到先服务
当多条任务优先级相同时，系统 SHALL 按提交先后顺序处理，MUST NOT 因 ZSET 同 score 而相互覆盖丢失。

#### Scenario: 同优先级不乱序
- GIVEN 待办队列有 prio 相同的 A 与 B（A 先提交）
- WHEN worker 依次取任务
- THEN 先取到 A 再取到 B

### Requirement: message_store 读回退收敛到单一来源
系统 SHALL 让所有读路径经由一个 `_read_source()` 判定入口读取，同一逻辑会话数据有确定的
primary 存储位置；同一 `chat_name/wxid` MUST 解析为权威 key 一次读取，不得为查找别名而在
多个 key 上逐条枚举探测。

#### Scenario: 读会话消息只读权威位置
- GIVEN 会话存在备注名/微信号等别名
- WHEN `get_all_messages_with_fallback` 被调用
- THEN 解析出该会话权威 key 并一次读取
- AND 不在多个别名 key 上逐一探测

#### Requirement: 消息可变域更新非 O(n)
系统 SHALL 让状态/回复内容等可变域的更新不经列表 `lindex` 全量扫描，MUST 使用索引或独立
key/hash 承载可变域，列表本体仅追加。

#### Scenario: 状态更新不扫全列表
- GIVEN 会话列表有 M 条消息
- WHEN `set_message_status(msg_id)` 被调用
- THEN 只更新 msg_id 对应条目，无 O(M) 逐条扫描

## MODIFIED Requirements

无（仅改内部实现与 key 结构，对外协议不变）。

## Scenario: Redis 不可用仍可读写
- GIVEN Redis 服务不可用
- WHEN 保存或读取消息
- THEN 走收敛后的单一回退源，读写语义不回退