# Chatlog 服务集成 - 产品需求文档

## Why

当前 SiverWXbot\_plus 的消息监听完全依赖 `wxautox4` 的 UI 自动化回调机制（`AddListenChat` + `message_handle_callback`），存在以下痛点：

1. **强依赖微信主窗口焦点**：UI 自动化要求微信窗口可见且未被遮挡，窗口失焦或被遮挡时容易漏消息。
2. **历史上下文有限**：`MemoryManager` 仅保存运行期间收到的消息（默认上限 3000 条），冷启动后无法获取历史对话。
3. **群聊/联系人信息查询不便**：现有方案无统一的通讯录 API，新增监听对象、群成员解析等都需要 UI 操作。
4. **UI 操作易失败**：搜索切换、子窗口注册等流程在微信版本变化或系统负载高时不稳定，已有大量重试容错代码。

`http://127.0.0.1:5030` 是本地部署的 **Chatlog** 服务（[github.com/sjzar/chatlog](https://github.com/sjzar/chatlog)），通过 HTTP API 提供以下能力：

* `GET /api/v1/session` — 最近会话列表（含未读数、wxid、昵称等）

* `GET /api/v1/chatroom` — 群聊列表（支持关键词搜索）

* `GET /api/v1/contact` — 联系人列表（支持关键词搜索、是否好友过滤）

* `GET /api/v1/chatlog` — 指定聊天对象的历史消息记录（支持时间范围、关键词、分页等）

* `/sse` — MCP SSE 端点（暂不在本规划范围内）

### 已验证的 API 响应结构

**`/api/v1/session?format=json`**
```json
{"items": [{"userName": "wxid_d9dbjmdoorug22", "nOrder": 1784213703, "nickName": "", "content": "你好", "nTime": "2026-07-16T22:55:03+08:00", "UnreadCount": 0}]}
```

**`/api/v1/contact?keyword=文件传输&format=json`**
```json
{"items": [{"userName": "filehelper", "alias": "", "remark": "", "nickName": "文件传输助手", "isFriend": false}]}
```

**`/api/v1/chatlog?talker=文件传输助手&format=json&limit=5`**
```json
[{"seq": 1772172683000, "time": "2026-02-27T14:11:23+08:00", "talker": "filehelper", "talkerName": "", "isChatRoom": false, "sender": "wxid_mertt4k5z7j429", "senderName": "", "isSelf": true, "type": 1, "subType": 0, "content": "Qt51514QWindowlcon"}, {"seq": 1772172658000, "time": "2026-02-27T14:10:58+08:00", "talker": "filehelper", "talkerName": "", "isChatRoom": false, "sender": "wxid_mertt4k5z7j429", "senderName": "", "isSelf": true, "type": 3, "subType": 0, "content": "", "contents": {"imgfile": "msg\\attach\\...\\Img\\xxx.dat", "md5": "ea7e981e3e3ddee2acab493a686bacb0", "thumb": "msg\\attach\\...\\Img\\xxx_t.dat"}}]
```

**关键发现**：
- `talker` 参数支持中文名（如"文件传输助手"）和 wxid（如"filehelper"）
- 时间格式：ISO 8601（`2026-07-16T22:55:03+08:00`）
- 消息类型：`type=1` 文本，`type=3` 图片
- 图片消息：`content` 为空，`contents` 对象包含 `imgfile`、`md5`、`thumb`
- `isSelf` 字段存在，用于判断是否自己发送
- `sender` 是 wxid，`senderName` 字段为空（需要通过 contact 接口映射昵称）

将 Chatlog 集成到本项目后，可在保留现有 UI 自动化发送能力的前提下，**用 HTTP 轮询替代或补充 UI 回调监听**，并**用历史聊天记录丰富 AI 上下文**，从而提升消息监听的稳定性和 AI 回复的相关性。

## What Changes

* **新增** `ChatlogClient` 客户端模块，封装 Chatlog HTTP API（session / chatroom / contact / chatlog 四个接口），支持超时、重试、错误降级。

* **新增** `chatlog_listen_switch` 监听模式开关：开启后由 Chatlog 轮询驱动 `process_message`，与现有 `wxautox4` 回调监听互斥（同一时间仅启用一种监听源），避免重复处理。

* **新增** `chatlog_context_switch` 上下文增强开关：开启后 AI 调用前从 Chatlog 拉取最近 N 条真实历史消息，与 `MemoryManager` 短期记忆合并后作为 `history` 传入。

* **新增** `chatlog_contact_lookup_switch` 联系人查询开关：开启后通过 Chatlog 校验监听对象是否存在、解析 wxid 与昵称映射，减少 UI 搜索次数。

* **新增** 配置项：`chatlog_url`、`chatlog_polling_interval`、`chatlog_context_count`、`chatlog_request_timeout` 等，统一写入 `config.json`。

* **新增** Web 面板（`web_server.py` + `templates/dashboard.html`）配置入口与状态展示。

* **修改** `WXBot.main()` 主循环：在 `chatlog_listen_switch` 开启时跳过 `listen_mode()` / `ALLListen_mode()`，改为调用新的 `chatlog_listen_loop()`。

* **修改** `process_message()`：在调用 AI 前根据 `chatlog_context_switch` 注入 Chatlog 历史上下文。

* **修改** `WXBotConfig`：加载/保存 chatlog 相关配置字段。

* **保留** 现有 `wxautox4` 发送链路（`chat.SendMsg`）不变，Chatlog 只读不写。

## Impact

* **Affected specs**:

  * `humanize-operations`（拟人化操作不受影响，仍作用于发送链路）

  * `wxautox4-missing-methods`（Chatlog 不替代 `wxautox4` 方法实现，二者互补）

* **Affected code**:

  * `wxbot_core.py`：`WXBot`、`WXBotConfig`、`MemoryManager`、`process_message`、`main`

  * `web_server.py`：新增 chatlog 配置接口与状态字段

  * `templates/dashboard.html`：新增 chatlog 配置面板

  * 新增 `chatlog_client.py`：Chatlog HTTP 客户端模块

## ADDED Requirements

### Requirement: Chatlog HTTP 客户端

系统 SHALL 提供独立的 `ChatlogClient` 类，封装 Chatlog 服务的四个核心 HTTP 接口，支持超时、错误重试与降级。所有接口默认使用 `format=json` 参数获取结构化数据。

#### Scenario: 正常查询聊天记录

* **WHEN** 调用 `client.get_chatlog(talker="张三", limit=20)`

* **THEN** 返回 list\[dict]，每项含 `seq`（消息序号）、`time`（ISO 8601 时间）、`talker`（聊天对象 wxid）、`talkerName`（聊天对象名称）、`isChatRoom`（是否群聊）、`sender`（发送者 wxid）、`senderName`（发送者名称）、`isSelf`（是否自己发送）、`type`（消息类型：1=文本，3=图片）、`content`（文本内容）、`contents`（图片消息的文件信息）等字段；HTTP 非 2xx 时抛出 `ChatlogError`。

#### Scenario: 正常查询会话列表

* **WHEN** 调用 `client.get_session()`

* **THEN** 返回 dict，含 `items` 列表，每项含 `userName`（wxid）、`nOrder`（排序序号）、`nickName`（昵称）、`content`（最新消息内容）、`nTime`（最新消息时间）、`UnreadCount`（未读数）。

#### Scenario: 正常查询联系人

* **WHEN** 调用 `client.search_contact(keyword="文件传输")`

* **THEN** 返回 dict，含 `items` 列表，每项含 `userName`（wxid）、`alias`（微信号）、`remark`（备注）、`nickName`（昵称）、`isFriend`（是否好友）。

#### Scenario: 服务不可达时降级

* **WHEN** Chatlog 服务未启动或网络异常

* **THEN** 客户端在 `chatlog_request_timeout`（默认 5s）后返回空结果或抛出可捕获异常，调用方据此跳过本次 Chatlog 增强，不影响主流程。

### Requirement: Chatlog 轮询监听模式

系统 SHALL 支持通过 Chatlog API 轮询获取新消息并触发自动回复，作为 `wxautox4` 回调监听的替代方案。

#### Scenario: 开启 Chatlog 监听后跳过 UI 监听

* **WHEN** `chatlog_listen_switch = True` 且主循环进入消息处理阶段

* **THEN** 跳过 `listen_mode()` 与 `ALLListen_mode()`，改为调用 `chatlog_listen_loop()`；UI 回调监听仍可保持注册（用于发送），但回调内不再触发 `process_message`。

#### Scenario: 增量消息拉取（带未读预过滤）

* **WHEN** `chatlog_listen_loop()` 执行

* **THEN** 
  1. 先调用 `get_session()` 获取所有会话列表，筛选出 `UnreadCount > 0` 的会话
  2. 对每个有未读消息的监听对象（白名单/黑名单逻辑与现有模式一致）调用 `get_chatlog(talker, time=last_pull_time)`，仅处理 `time` 晚于本地已处理时间戳的消息
  3. 首次启动以当前时间为基准，避免回放全量历史
  4. 使用 `seq`（消息序号）而非时间作为去重依据，避免同一消息被多次处理

#### Scenario: 消息类型转换

* **WHEN** Chatlog 返回消息需要转换为 `wxautox4` 兼容格式

* **THEN** 将 Chatlog 消息 dict 转换为轻量消息对象，映射规则：
  - `type`：`1` → `'text'`，`3` → `'image'`，其他 → `'unknown'`
  - `attr`：`isSelf=True` → `'self'`，`isChatRoom=True` → `'group'`，其他 → `'friend'`
  - `sender`：优先使用 `senderName`，为空时使用 `sender`（wxid）
  - `content`：文本消息直接使用；图片消息使用 `contents.md5` 作为标识；语音消息暂不处理
  - `id`：使用 `seq` 字段

#### Scenario: 与发送链路解耦

* **WHEN** Chatlog 监听到新消息需要回复

* **THEN** 通过 `wxautox4` 的 `GetSubWindow` / `SendMsg` 发送回复；若子窗口未注册则先调用 `AddListenChat` 注册（仅注册不触发回调处理）。

### Requirement: AI 上下文增强

系统 SHALL 支持在调用 AI 前从 Chatlog 拉取真实历史消息，与 `MemoryManager` 短期记忆合并后作为 `history` 传入。

#### Scenario: 上下文增强开启

* **WHEN** `chatlog_context_switch = True` 且收到需要 AI 回复的消息

* **THEN** 调用 `client.get_chatlog(talker=chat.who, limit=chatlog_context_count)` 拉取历史；按 `is_self` 字段映射为 `Self`/`friend` 属性；与 `MemoryManager` 记忆去重合并（按时间排序，保留最近 N 条）后传入 `api.chat()`。

#### Scenario: 上下文增强关闭或失败

* **WHEN** `chatlog_context_switch = False` 或 Chatlog 拉取失败

* **THEN** 退化为仅使用 `MemoryManager` 记忆，不影响主流程。

### Requirement: 联系人查询增强

系统 SHALL 支持通过 Chatlog 校验监听对象是否存在并解析 wxid/昵称映射。

#### Scenario: 监听列表初始化时校验

* **WHEN** `chatlog_contact_lookup_switch = True` 且 `init_wx_listeners()` 执行

* **THEN** 通过 `client.search_contact(keyword=nickname)` 校验 `listen_list` 与 `group` 中的对象是否存在；不存在则在日志中告警并跳过 UI 注册，减少无效的 UI 搜索操作。

### Requirement: 配置与面板集成

系统 SHALL 在 `config.json` 与 Web 面板中提供 Chatlog 相关配置项与状态展示。

#### Scenario: 配置加载

* **WHEN** `WXBotConfig.load_config()` 执行

* **THEN** 加载 `chatlog_url`、`chatlog_listen_switch`、`chatlog_context_switch`、`chatlog_contact_lookup_switch`、`chatlog_polling_interval`、`chatlog_context_count`、`chatlog_request_timeout` 字段；缺失字段使用默认值。

#### Scenario: 面板状态展示

* **WHEN** 用户访问 `dashboard.html`

* **THEN** 在状态区显示 Chatlog 连接状态（已连接/未连接）、当前监听模式、轮询间隔；在配置区提供开关与 URL 输入框，保存后通过 `web_server.py` 接口写入 `config.json` 并热更新。

## MODIFIED Requirements

### Requirement: WXBot 主循环

`WXBot.main()` 主循环 SHALL 根据 `chatlog_listen_switch` 选择消息源：

* 开启时：调用 `chatlog_listen_loop()`，跳过 `listen_mode()` / `ALLListen_mode()`

* 关闭时：维持现有行为不变（白名单走 `listen_mode()`，黑名单走 `ALLListen_mode()`）
  其他模块（离线检测、新好友检测、定时任务）行为不变。

### Requirement: process\_message 上下文构建

`process_message()` 在调用 `api.chat()` 前 SHALL 检查 `chatlog_context_switch`：

* 开启且 Chatlog 可用：合并 Chatlog 历史 + MemoryManager 记忆

* 关闭或 Chatlog 不可用：仅使用 MemoryManager 记忆（现有行为）
  合并逻辑需去重（按 `time` + `content` 哈希）、按时间升序排序、截断至 `memory_context_count` 条。

## REMOVED Requirements

无移除项。本规划为增量集成，不破坏现有 `wxautox4` 监听链路。

## Non-Goals (Out of Scope)

* 不实现 Chatlog 服务的安装与部署（由用户自行启动 `chatlog` 命令）

* 不接入 Chatlog 的 MCP SSE 端点（`/sse`），仅使用同步 HTTP API

* 不替换 `wxautox4` 的消息发送能力（Chatlog 是只读 API，无法发送）

* 不修改 `wxautox4` 内部实现

* 不实现 Chatlog 离线消息的本地持久化缓存（运行期内存即可）

* 不重构现有 `MemoryManager`（仅在使用侧合并调用）

## Constraints

* **Technical**: 必须保持与现有 `wxautox4` 发送链路兼容；Chatlog 调用必须可降级，单点故障不能阻塞主循环

* **Dependencies**: 依赖 `requests` 库（已在 `requirements.txt`）；依赖用户本地已启动 Chatlog 服务

* **Performance**: Chatlog 轮询间隔默认 3 秒，最小 1 秒；HTTP 超时默认 5 秒；上下文拉取仅对当前正在回复的会话执行，避免批量拉取

* **Compatibility**: 配置项必须向后兼容，旧 `config.json` 缺失字段时使用默认值

## Assumptions

* 用户已在本地启动 Chatlog 服务（默认 `http://127.0.0.1:5030`）并完成微信数据库解密授权

* Chatlog 返回的时间字段为可解析的字符串（ISO 或 `YYYY-MM-DD HH:MM:SS`）

* Chatlog 的 `talker` 参数支持 wxid、群 ID、备注名、昵称，与现有 `listen_list` 中的昵称可互通

* 同一会话在 Chatlog 与 `wxautox4` 中可对应（通过昵称或 wxid 关联）

## Open Questions

* [ ] Chatlog 监听模式下，是否需要保留 `wxautox4` 的 `AddListenChat` 注册（用于发送）？当前规划是保留注册但回调内跳过处理。

* [ ] 上下文合并时，若 Chatlog 历史与 MemoryManager 记忆存在冲突（内容相同但时间不同），以哪一方为准？建议以 Chatlog 为准（数据库来源更权威）。

* [ ] 是否需要支持 Chatlog 多实例（如多个微信号）？当前规划仅支持单实例。

* [ ] 群聊场景下 Chatlog 的 `sender` 字段是否可解析为群成员昵称？需要实际测试确认。

