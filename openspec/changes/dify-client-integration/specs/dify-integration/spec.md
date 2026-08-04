# Spec: Dify 客户端接入（dify-integration）

能力路径：`dify-integration`（delta spec，随 change 归档后可并入主 specs）

## Purpose

用仓库内官方 `core/dify_client` 重构 Dify API 接入，使自部署 Dify 下的 chatflow
（真实服务端会话）与 workflow（入参/出参变量名可配）两类 app 都能被机器人调用，
并按 `{api_base, api_key, user_key}` 隔离会话，避免同实例多 app 串号。

## ADDED Requirements

### Requirement: base_url 自动解析出 api_base 并走官方客户端

DifyAPI SHALL 从配置的 `base_url`（可能带 `/chat-messages` 尾缀、尾斜杠、query）自动解析出
Dify 服务根地址 `api_base`，并基于 `core/dify_client.Client` 发起请求；不得再使用裸 `requests` 直打端点。

#### Scenario: 尾缀自动剥离
- **WHEN** 配置 `base_url` 为 `http://127.0.0.1:8088/v1/chat-messages`
- **THEN** 解析出的 `api_base` 为 `http://127.0.0.1:8088/v1`
- **AND** 请求由 `core/dify_client.Client` 发出

#### Scenario: 已是服务根地址直接使用
- **WHEN** 配置 `base_url` 为 `http://127.0.0.1:8088/v1/`
- **THEN** 解析出的 `api_base` 为 `http://127.0.0.1:8088/v1`，不带尾斜杠

### Requirement: 按 app_type 分发 chat / workflow

DifyAPI SHALL 依据配置的 `app_type` 选择调用方式：
- `chat`（chatflow / Chat App）→ 调 `/chat-messages`；
- `workflow`（Workflow App）→ 调 `/workflows/run`。

未配置或未知 `app_type` 时 SHALL 按 `chat` 处理。

#### Scenario: chat 型走聊天接口
- **WHEN** `app_type` 为 `chat` 且收到用户消息
- **THEN** 调用 Dify 聊天消息接口
- **AND** 返回文本为 Dify 聊天回复

#### Scenario: workflow 型走工作流接口
- **WHEN** `app_type` 为 `workflow` 且收到用户消息
- **THEN** 调用 Dify 工作流运行接口
- **AND** 用户消息作为入参变量传入

### Requirement: chat 型真实服务端会话

chat 型 SHALL 复用 Dify 服务端 `conversation_id` 实现多轮会话：首次会话无 id 时由响应携带的
`conversation_id` 记录，后续请求携带同一 id 继续会话。会话标识 SHALL 满足三要素隔离：
`dify:conv:{hash(api_base|api_key)}:{user_key}`，其中 `api_key` 为 Dify 的 app 密钥（`app-xxx`，
天然区分同实例下不同 app），`user_key` 为调用方传入的会话身份
（如微信 `chat_name`），Dify 请求的 `user` 字段 SHALL 由 `user_key` 派生的稳定标识（如
`wxbot_{hash(user_key)}`）构成。Redis 不可用时 SHALL 随 `RedisManager` 降级到本地 fallback 存储，
不得因存储失败而中断回复。

#### Scenario: 首次对话建立会话
- **WHEN** 某会话尚无 `conversation_id`
- **THEN** 请求不携带旧会话 id
- **AND** 响应携带 `conversation_id` 后被持久化

#### Scenario: 后续对话延续会话
- **WHEN** 同一 `{api_base, api_key, user_key}` 已有 `conversation_id`
- **THEN** 请求携带该 id
- **AND** 响应更新后的 `conversation_id` 覆盖持久化

#### Scenario: 不同 app 会话互不串号
- **WHEN** 同一自部署实例下有 app A 与 app B，且 `api_key`（app 密钥）不同
- **THEN** 两 app 的 `conversation_id` 存储相互隔离
- **AND** 互不混用会话

#### Scenario: Redis 不可用仍能回复
- **WHEN** Redis 不可用且启用 fallback
- **THEN** 会话 id 存至本地 fallback 存储
- **AND** AI 回复照常返回

### Requirement: workflow 型入参与出参

workflow 型 SHALL 将用户消息按配置的 `workflow_input_key` 映射写入工作流入参 `inputs`（默认
`query` 时退化为 `{"query": <用户消息>}`），并把工作流响应 `outputs` 中 `workflow_output_key`
对应的值作为回复文本返回（默认 `text`）。目标键缺失或值为非文本时 SHALL 返回固定错误回复，
不得抛未捕获异常。

`workflow_input_key` SHALL 支持多键映射：以逗号分隔的 `key=value` 对，value 可含占位符
`$message`（=chat() 的 message 实参）、`$prompt`（=chat() 的 prompt 实参）、`$model`（模型名）、
`$user_key`（会话身份）、`$history`（历史消息渲染文本）、`$time`/`$date`（当前时间/日期）；
未用占位符的 value 按常量原样传入。例 `msgs=$message,prompt=$prompt` →
`inputs={"msgs": 用户消息, "prompt": 提示词}`。解析结果为空时 SHALL 退化为单键
`{workflow_input_key: message}`。

#### Scenario: 入参映射到配置变量
- **WHEN** `workflow_input_key` 为 `query` 且用户消息为 `你好`
- **THEN** 工作流入参 `inputs` 包含 `{"query": "你好"}`

#### Scenario: 多键入参映射
- **WHEN** `workflow_input_key` 为 `msgs=$message,prompt=$prompt`，`chat()` 收到消息 `你好` 且 `prompt` 为 `你是客服`
- **THEN** 工作流入参 `inputs` 包含 `{"msgs": "你好", "prompt": "你是客服"}`

#### Scenario: 扩展占位符替换
- **WHEN** `workflow_input_key` 为 `u=$user_key,d=$date`，传入 `user_key=user1`
- **THEN** `inputs` 包含 `{"u": "user1", "d": <当前日期>}`

#### Scenario: 出参提取为回复
- **WHEN** `workflow_output_key` 为 `text` 且工作流返回 `outputs={"text": "回复内容"}`
- **THEN** 机器人回复文本为 `回复内容`

#### Scenario: 出参键缺失返回固定错误
- **WHEN** 工作流 `outputs` 中不存在配置的 `workflow_output_key`
- **THEN** 返回固定错误回复（`api_error_reply` 语义）

### Requirement: 本地 history 语义保持不变

无论 chat 还是 workflow 型，本地 `history`（memory + chatlog 增强上下文）SHALL 维持既有的
拼接进请求上下文（chat 型拼入 query 前缀）的做法，行为与重构前一致；`chat()` 仍返回纯文本字符串。

#### Scenario: chat 型 history 仍拼入 query
- **WHEN** 传入 `history` 且 `app_type` 为 `chat`
- **THEN** 请求中的上下文包含拼接后的历史
- **AND** 与重构前行为一致

### Requirement: 调用方契约向后兼容

所有 AI 接口类的 `chat()` SHALL 接受可选参数 `user_key=None`；既有必填参数与返回类型
（纯文本字符串）MUST NOT 改变。Dify 的会话身份取自 `user_key`，未传入时按无会话处理。

#### Scenario: 不传 user_key 不报错
- **WHEN** 以既有参数调用 `chat(message, prompt, history)` 且不传 `user_key`
- **THEN** 调用正常返回文本
- **AND** Dify 按无会话模式处理

#### Scenario: 传入 user_key 激活会话隔离
- **WHEN** 调用方传入 `user_key=chat_name`
- **THEN** 会话按该 key 隔离存储
- **AND** 同一 `chat_name` 多轮延续会话

## MODIFIED Requirements

无（本 change 不修改既有 spec 定义的行为协议）。

## 未覆盖（后续 phase）

- Dify 流式（streaming）回复接入（客户端已支持，本 change 仅用 blocking）。
- 图片/文件上传到 Dify（`upload_files`）。
- 消息反馈（feedback）与停止任务（stop）管理。
- workflow 型服务端会话（`conversation_id` 语义以 chat 型为准）。
