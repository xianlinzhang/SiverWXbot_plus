# Proposal

## Why

现有 `core/ai_api.py:DifyAPI` 用裸 `requests` 直打 `/chat-messages`：只支持 chat 型 app、
`conversation_id` 恒为空（多轮靠本地 history 拼进 query）、无 workflow 支持、无流式/类型化响应。
仓库已新加入官方 `core/dify_client/`（httpx + pydantic 类型化客户端，未提交、未接线），支持
chat / workflow / completion 三种 app 与 blocking / streaming 两种模式。自部署 Dify 同实例下
常有多个 app，需要一个能按 app 区分会话、支持 workflow 的接入层。

## What Changes

- **重写 `core/ai_api.py:DifyAPI`**：从 `base_url` 自动 strip 出 `api_base`（去 `/chat-messages` 尾缀、
  尾斜杠、query），构造 `core/dify_client.Client`；按 `app_type` 分发 `chat_messages()` / `run_workflows()`。
- **面板配置（`dashboard.html` + `config_manager.py` 迁移）**：每个 `api_configs[i]` 新增 3 个字段：
  `app_type`（chat/workflow）、`workflow_input_key`（入参变量映射，支持多键键值对，如
  `msgs=$message,prompt=$prompt`）、`workflow_output_key`（输出变量名）。旧配置自动迁移默认值。
  Dify 的 app 由 `api_key`（`app-xxx`）直接标识，无需额外 App Key 字段。
- **真实会话**：chatflow 型复用 Dify 服务端 `conversation_id`，存 Redis，key =
  `dify:conv:{hash(api_base|api_key)}:{user_key}`；`user` 字段用 `wxbot_{hash(user_key)}`。
- **调用方契约扩展**：所有 API 类的 `chat()` 增加可选参数 `user_key=None`（OpenAI/Coze/Dus 忽略），
  `message_handler` / `chatlog_manager` 传入 `chat_name`。向后兼容，不改既有必填签名。
- **本地 history 做法不变**：history 仍拼接进 query（chat 型）作为上下文前缀。
- **依赖入 `requirements.txt`**：新增 `httpx` / `httpx-sse` / `pydantic` / `strenum`。
- `web_server._TempAPIConfig` / `wxbot_core._ApiProxy` 同步带出新字段，接口测试路由兼容。

## Capabilities

### New Capabilities

- `dify-integration`: 用官方 `core/dify_client` 重构 Dify API 接入，支持自部署 Dify 的
  chatflow（真实服务端会话）与 workflow（入参/出参变量可配）两类 app，按
  `{api_base, api_key, user_key}` 隔离会话。

### Modified Capabilities

- 无（本 change 不改既有对外行为协议；本地 history 拼接、`chat()` 字符串返回契约均保持不变，
  新增能力独立成新 spec）。

## Impact

- **代码**：`core/ai_api.py`（重写 `DifyAPI`）、`core/config_manager.py`（迁移/派生新字段）、
  `wxbot_core.py`（`_ApiProxy`）、`web_server.py`（`_TempAPIConfig`、`_build_test_api_client`）、
  `core/message_handler.py` + `core/chatlog_manager.py`（调用传 `user_key`）。
- **前端**：`templates/dashboard.html`（接口配置项渲染模板、新增模板、`getApiConfigFromItem`、
  `saveConfig` 采集新字段，仅 `sdk==Dify` 显示，workflow 字段仅 `app_type==workflow` 显示）。
- **依赖**：`requirements.txt` 新增 `httpx` / `httpx-sse` / `pydantic` / `strenum`
  （本机 `httpx`、`pydantic` 已装；`httpx-sse`、`strenum` 缺失需安装）。
- **数据**：Redis 新增 `dify:conv:*` 会话键（不可用时随 `RedisManager` 降级到 `fallback_redis.json`）。
- **行为**：Dify SDK 从裸 `requests` 切到 `core/dify_client`；`chat()` 返回文本契约不变。
