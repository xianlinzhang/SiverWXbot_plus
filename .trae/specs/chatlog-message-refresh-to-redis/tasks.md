# Tasks

- [x] Task 1: 在 `core/config_manager.py` 新增 4 个 `chatlog_message_refresh_*` 配置项
  - [x] SubTask 1.1: 新增 `chatlog_message_refresh_days`（默认 30）
  - [x] SubTask 1.2: 新增 `chatlog_message_refresh_limit`（默认 500）
  - [x] SubTask 1.3: 新增 `chatlog_message_auto_refresh`（默认 True）
  - [x] SubTask 1.4: 新增 `chatlog_message_manual_refresh_cooldown`（默认 60）
  - [x] SubTask 1.5: 在 `_chatlog_defaults` 字典中补充对应配置项（config.json 自动补全）

- [x] Task 2: 在 `core/message_store.py` 新增去重批量保存方法 `_save_messages_bulk_dedup`
  - [x] SubTask 2.1: 实现基于 `seq` 的去重逻辑（seq > 0 时用 seq，否则用 sender+content+receive_time 的 sha256 hash）
  - [x] SubTask 2.2: 实现 Redis 路径：先 `lrange` 取已有消息的 seq 集合，过滤后批量 `lpush`，超限时 `ltrim`
  - [x] SubTask 2.3: 实现文件降级路径：加载已有消息列表，去重后追加并截断到 `max_count`，事务性写回
  - [x] SubTask 2.4: 返回 `(total_input, new_saved)` 统计

- [x] Task 3: 在 `core/message_store.py` 新增统一刷新方法 `refresh_messages_from_chatlog`
  - [x] SubTask 3.1: 校验 `bot.chatlog_client` 可用性，不可用时返回 `(0, 0)`
  - [x] SubTask 3.2: 通过 `chatlog_contact_map` 把 `chat_name`（备注名）解析为 `userName` 作为 talker
  - [x] SubTask 3.3: 调用 `chatlog_client.get_chatlog(talker, time="N天前~今天", limit=M)`
  - [x] SubTask 3.4: 把每条 Chatlog 消息字典转换为 `MessageRecord`（复用 `ChatlogManager._convert_chatlog_msg` 的逻辑，但直接构造 record 字段）
  - [x] SubTask 3.5: 调用 `_save_messages_bulk_dedup` 批量入库
  - [x] SubTask 3.6: 异常时记录 WARNING 日志并返回 `(0, 0)`，不抛出

- [x] Task 4: 改造 `core/chatlog_manager.py` 的 `chatlog_listen_loop` 接入自动刷新
  - [x] SubTask 4.1: 在 `get_chatlog(limit=500)` 拉取成功后、过滤新消息之前，检查 `chatlog_message_auto_refresh`
  - [x] SubTask 4.2: 若开启，调用 `self.message_store.refresh_messages_from_chatlog(chat_name)`，传入已拉取的 msgs（避免重复请求 API）或由方法内部重新拉取（二选一，推荐前者以节省 API 调用）
  - [x] SubTask 4.3: 异常捕获包裹自动刷新调用，失败时记录 ERROR 但不阻断后续流程
  - [x] SubTask 4.4: 记录 INFO 日志：`自动刷新会话 [chat_name] 消息：拉取 X 条，新增 Y 条`

- [x] Task 5: 在 `web_server.py` 新增 `POST /api/contacts/messages/refresh` 端点
  - [x] SubTask 5.1: 端点接收 JSON body `{chat_name}`，校验非空
  - [x] SubTask 5.2: 校验 bot 与 message_store 已初始化
  - [x] SubTask 5.3: 实现冷却时间检查（基于内存字典 `{chat_name: last_refresh_ts}`），冷却内返回 429 + retry_after
  - [x] SubTask 5.4: 调用 `bot.message_store.refresh_messages_from_chatlog(chat_name)`
  - [x] SubTask 5.5: 更新冷却时间戳，返回 `{code:0, data:{total_fetched, new_saved}}`

- [x] Task 6: 在 `templates/dashboard.html` 前端接入手动刷新
  - [x] SubTask 6.1: 在联系人消息面板顶部工具栏新增"刷新消息"按钮（图标+文字）
  - [x] SubTask 6.2: 实现按钮点击：loading 状态 → 调用 `POST /api/contacts/messages/refresh` → 成功/失败 toast 提示 → 重新加载消息列表
  - [x] SubTask 6.3: 实现切换联系人自动刷新：点击联系人查看消息时，记录上次刷新时间，超过冷却时间则静默调用刷新端点，完成后渲染消息
  - [x] SubTask 6.4: 冷却时间内或刷新失败时不阻断消息列表展示（展示 Redis 现有数据）

- [x] Task 7: 验证与测试
  - [x] SubTask 7.1: 验证自动刷新开启时，`chatlog_listen_loop` 触发后 Redis 中该会话消息数接近 500（去重后）
  - [x] SubTask 7.2: 验证自动刷新关闭时，行为与改造前一致（仅新消息入库）
  - [x] SubTask 7.3: 验证手动刷新端点：首次成功返回 new_saved，冷却内再次请求返回 429
  - [x] SubTask 7.4: 验证重复刷新不产生重复记录（seq 相同的消息被跳过）
  - [x] SubTask 7.5: 验证 Redis 不可用时降级到文件存储，功能不中断
  - [x] SubTask 7.6: 验证前端按钮 loading、toast、自动刷新冷却均正常

# Task Dependencies
- Task 2 依赖 Task 1（需要 `chatlog_message_refresh_limit` 配置）
- Task 3 依赖 Task 2（需要 `_save_messages_bulk_dedup`）
- Task 4 依赖 Task 3（需要 `refresh_messages_from_chatlog`）
- Task 5 依赖 Task 3（需要 `refresh_messages_from_chatlog`）
- Task 6 依赖 Task 5（需要后端端点）
- Task 7 依赖 Task 1-6 全部完成
- Task 1、Task 2 可并行启动（Task 2 内部先用 `getattr` 兜底默认值）
