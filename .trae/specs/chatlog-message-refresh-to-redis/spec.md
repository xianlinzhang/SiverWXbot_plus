# Chatlog 消息刷新到 Redis Spec

## Why
当前 Chatlog 监听模式下，`chatlog_listen_loop` 每次轮询虽然调用了 `get_chatlog(limit=500)` 拉取最近 30 天消息，但只把过滤后的"新消息"（`seq > last_seq` 且非 self）存入 Redis，其余历史消息被丢弃。导致：
- 仪表盘点击联系人查看消息时，Redis 中只有触发过自动回复的新消息，历史消息缺失；
- `/api/contacts/messages` 端点只读 Redis，无法展示完整对话历史；
- 没有任何机制可主动触发"从 Chatlog 拉取并写入 Redis"。

需要一个统一的刷新机制，将 Chatlog 历史消息去重后同步到 Redis，支持自动与手动两种触发方式。

## What Changes
- 在 `MessageStore` 中新增统一刷新方法 `refresh_messages_from_chatlog(chat_name, days=None, limit=None)`，调用 Chatlog API 拉取消息后**基于 `seq` 去重**批量写入 Redis（Redis 不可用时降级写入本地文件）。
- 在 `MessageStore` 中新增内部方法 `_save_messages_bulk_dedup(chat_name, record_dicts)`，基于 `seq` 去重批量保存，避免重复 `lpush` 产生重复记录。
- **改造自动通道**：`ChatlogManager.chatlog_listen_loop` 在拉取 500 条消息后，调用 `refresh_messages_from_chatlog` 把全部消息入库（含 self 与已读历史），再继续走原有"过滤新消息 → AI 回复"流程。
- **新增手动通道**：在 `web_server.py` 新增 `POST /api/contacts/messages/refresh` 端点，接收 `chat_name` 参数，调用 `refresh_messages_from_chatlog`，返回新增条数。
- 前端 `dashboard.html` 在联系人消息面板增加"刷新消息"按钮，调用上述端点；点击联系人查看消息时按冷却时间自动触发一次刷新。
- 新增配置项：`chatlog_message_refresh_days`（默认 30）、`chatlog_message_refresh_limit`（默认 500）、`chatlog_message_auto_refresh`（默认 True，控制自动通道开关）、`chatlog_message_manual_refresh_cooldown`（默认 60 秒，手动刷新冷却）。
- **BREAKING**：无。所有新行为受 `chatlog_message_auto_refresh` 开关控制，默认开启但可关闭。

## Impact
- Affected specs: 无现存相关 spec（现有 `chatlog-integration`、`chatlog_process_message` 不涉及消息刷新入库）。
- Affected code:
  - `core/message_store.py`：新增 `refresh_messages_from_chatlog`、`_save_messages_bulk_dedup`，新增冷却时间内存记录。
  - `core/chatlog_manager.py`：改造 `chatlog_listen_loop`，在拉取消息后调用统一刷新方法。
  - `core/config_manager.py`：新增 4 个 `chatlog_message_refresh_*` 配置项及默认值。
  - `web_server.py`：新增 `POST /api/contacts/messages/refresh` 端点。
  - `templates/dashboard.html`：新增"刷新消息"按钮 + 自动刷新逻辑 + 冷却时间提示。
  - `config.json`：新增对应配置项（由 config_manager 默认值兜底，不强制写入）。

## ADDED Requirements

### Requirement: 统一消息刷新方法
系统 SHALL 提供一个统一的 `refresh_messages_from_chatlog(chat_name, days=None, limit=None)` 方法，从 Chatlog API 拉取指定会话最近 N 天的消息（最多 M 条作为安全上限），去重后写入 Redis/文件存储。

#### Scenario: 正常刷新
- **WHEN** 调用 `refresh_messages_from_chatlog(chat_name="张三")`
- **THEN** 系统调用 Chatlog API 拉取最近 `chatlog_message_refresh_days` 天、最多 `chatlog_message_refresh_limit` 条消息
- **AND** 对每条消息转换为 `MessageRecord`（含正确的 msg_type、msg_attr、sender、content、seq、receive_time）
- **AND** 基于 `seq` 与 Redis 中已有消息去重，仅保存新增消息
- **AND** 返回 `(total_fetched, new_saved)` 元组，表示拉取总数与新增入库数

#### Scenario: 去重保护
- **WHEN** Chatlog 返回的消息中存在 `seq` 已存在于 Redis 的消息
- **THEN** 系统跳过这些消息，不重复写入
- **AND** 不影响已有消息的 status、reply_content 等字段

#### Scenario: seq 缺失兜底
- **WHEN** 某条消息 `seq` 为 0 或缺失
- **THEN** 系统使用 `(sender, content, receive_time)` 组合的 sha256 hash 作为去重键
- **AND** 该 hash 同样参与去重比对

#### Scenario: Redis 不可用降级
- **WHEN** Redis 不可用
- **THEN** 系统降级到本地文件存储，同样执行去重逻辑（基于已加载的消息列表）
- **AND** 不抛出异常，返回降级后的 `(total_fetched, new_saved)`

#### Scenario: Chatlog API 失败
- **WHEN** Chatlog API 调用失败或返回空
- **THEN** 系统记录 WARNING 日志，返回 `(0, 0)`，不抛出异常

### Requirement: 自动刷新通道
系统 SHALL 在 `chatlog_listen_loop` 检测到有未读消息的会话时，将该会话最近 N 天的全部消息（含 self 与已读历史）同步到 Redis，再继续原有的"过滤新消息 → AI 回复"流程。

#### Scenario: 自动刷新开启
- **WHEN** `chatlog_message_auto_refresh=True` 且 `chatlog_listen_switch=True`
- **AND** `chatlog_listen_loop` 检测到某会话有未读消息
- **THEN** 在调用 `chatlog_process_message` 之前，先调用 `refresh_messages_from_chatlog(chat_name)` 把本次 `get_chatlog(limit=500)` 拉取的全部消息去重入库
- **AND** 继续走原有新消息过滤与 AI 回复流程
- **AND** 记录 INFO 日志：`自动刷新会话 [chat_name] 消息：拉取 X 条，新增 Y 条`

#### Scenario: 自动刷新关闭
- **WHEN** `chatlog_message_auto_refresh=False`
- **THEN** `chatlog_listen_loop` 不调用 `refresh_messages_from_chatlog`，仅保留原有行为（只存新消息）
- **AND** 不影响其他功能

#### Scenario: 自动刷新失败不阻断主流程
- **WHEN** 自动刷新方法抛出异常
- **THEN** 捕获异常并记录 ERROR 日志，继续执行原有新消息处理流程
- **AND** 不阻断该会话后续消息处理

### Requirement: 手动刷新 API 端点
系统 SHALL 提供 `POST /api/contacts/messages/refresh` 端点，支持前端手动触发指定会话的消息刷新。

#### Scenario: 手动刷新成功
- **WHEN** 已登录用户 POST `/api/contacts/messages/refresh`，body 包含 `chat_name`
- **THEN** 系统校验 `chat_name` 非空
- **AND** 调用 `refresh_messages_from_chatlog(chat_name)`
- **AND** 返回 `{"code": 0, "message": "刷新成功", "data": {"total_fetched": X, "new_saved": Y}}`

#### Scenario: 缺少参数
- **WHEN** 请求未提供 `chat_name`
- **THEN** 返回 `{"code": 400, "message": "chat_name 参数不能为空"}`

#### Scenario: 冷却时间限制
- **WHEN** 同一 `chat_name` 在 `chatlog_message_manual_refresh_cooldown` 秒内重复请求
- **THEN** 返回 `{"code": 429, "message": "刷新冷却中，请 X 秒后重试", "data": {"retry_after": X}}`
- **AND** 不执行实际刷新

#### Scenario: 机器人未启动
- **WHEN** bot 或 message_store 未初始化
- **THEN** 返回 `{"code": 400, "message": "机器人未启动"}`

### Requirement: 前端刷新按钮与自动触发
系统 SHALL 在仪表盘联系人消息面板提供"刷新消息"按钮，并在点击联系人查看消息时按冷却时间自动触发一次刷新。

#### Scenario: 点击刷新按钮
- **WHEN** 用户在联系人消息面板点击"刷新消息"按钮
- **THEN** 按钮置为 loading 状态，调用 `POST /api/contacts/messages/refresh`
- **AND** 成功后显示提示：`刷新成功：拉取 X 条，新增 Y 条`
- **AND** 自动重新加载该联系人消息列表
- **AND** 失败（含冷却）时显示对应错误提示

#### Scenario: 切换联系人自动刷新
- **WHEN** 用户点击联系人列表中的某联系人查看消息
- **AND** 该会话距上次自动刷新超过 `chatlog_message_manual_refresh_cooldown` 秒
- **THEN** 前端自动调用刷新端点（静默，不弹提示）
- **AND** 刷新完成后展示最新消息列表
- **AND** 若在冷却时间内则跳过自动刷新，直接展示 Redis 现有消息

### Requirement: 新增配置项
系统 SHALL 在 `WXBotConfig` 中新增 4 个配置项控制刷新行为，并在 `config.json` 中提供默认值。

#### Scenario: 配置项默认值
- **WHEN** 配置文件未显式设置这些项
- **THEN** 使用默认值：
  - `chatlog_message_refresh_days` = 30
  - `chatlog_message_refresh_limit` = 500
  - `chatlog_message_auto_refresh` = True
  - `chatlog_message_manual_refresh_cooldown` = 60

#### Scenario: 配置项可被界面修改
- **WHEN** 用户在配置界面修改任一配置项
- **THEN** 修改后立即生效（下一次刷新使用新值），无需重启

## MODIFIED Requirements

### Requirement: chatlog_listen_loop 消息处理流程
原流程：拉取 500 条 → 过滤新消息（seq > last_seq 且非 self）→ 逐条 `chatlog_process_message`（含 save_message）→ 更新 last_seq。

修改后流程：拉取 500 条 → **若 `chatlog_message_auto_refresh=True`，调用 `refresh_messages_from_chatlog` 把全部消息去重入库** → 过滤新消息 → 逐条 `chatlog_process_message`（save_message 因去重会跳过已入库的，不产生重复）→ 更新 last_seq。

#### Scenario: 自动刷新开启时的新消息处理
- **WHEN** `chatlog_message_auto_refresh=True`
- **AND** `chatlog_listen_loop` 拉取到 500 条消息
- **THEN** 先调用 `refresh_messages_from_chatlog(chat_name)` 把 500 条全部去重入库
- **AND** `chatlog_process_message` 内部调用 `save_message` 时，因去重逻辑自动跳过已入库消息（基于 seq）
- **AND** AI 回复流程不受影响，仍然只对新消息（seq > last_seq 且非 self）回复

#### Scenario: 自动刷新关闭时保留原行为
- **WHEN** `chatlog_message_auto_refresh=False`
- **THEN** `chatlog_listen_loop` 完全保留原有行为，仅对新消息调用 `save_message`
- **AND** 不调用 `refresh_messages_from_chatlog`

## REMOVED Requirements
无。
