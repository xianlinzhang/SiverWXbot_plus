# Design

## Context

现状见 `proposal.md`。关键约束：

- 所有 API 类（OpenAI/Coze/Dus/Dify）共用 `chat(message, model, stream, prompt, history) → str`
  契约，调用方集中在 `core/message_handler.py` 与 `core/chatlog_manager.py`，且都持有 `chat_name`。
- 默认 API 实例 `bot.api` 与群组专属实例（`bot.api_cache[idx]`）都是**跨聊天共享**的，一个 `DifyAPI`
  实例服务多个会话 —— 所以会话隔离不能放实例上，必须显式接收 `user_key` 并按 key 隔离。
- `base_url` 当前语义是**完整端点地址**（含 `/chat-messages`），新客户端 `Client.api_base` 要求
  **服务根地址**（`/v1`），需兼容迁移。
- `RedisManager`（`core/redis_manager.py`）已提供 get/set + JSON + fallback 文件降级，`message_store`
  已示范"用 `config.redis_*` 字段惰性自建 `RedisManager`"的模式。
- `core/dify_client/` 依赖 `httpx`、`httpx-sse`、`pydantic`、`strenum`（py<3.11 的 `StrEnum` 回退）。
  本机：`httpx 0.28.1`、`pydantic 2.10.6` 已装；`httpx-sse`、`strenum` 缺失。

## Goals / Non-Goals

**Goals:**

- `DifyAPI` 全面改走 `core/dify_client`，支持 chatflow 与 workflow 两类 app，接口测试路由同步可用。
- 会话按 `{api_base, api_key, user_key}` 三要素隔离，落 Redis（可降级）。`api_key` 即 Dify
  的 app 密钥（`app-xxx`），天然区分同实例下的不同 app，无需额外 App Key 字段。
- `chat()` 契约与本地 history 语义完全不变，其它 SDK 零行为影响。

**Non-Goals:**

- 不接 streaming 回复、文件上传、feedback、stop 任务（spec 已声明为未覆盖）。
- 不改 `core/dify_client` 内部实现（随仓授权内核，只消费其 API）。

## Decisions

### D1. `base_url → api_base` 的解析规则

构造时解析：先 `urlsplit` 去掉 query/fragment，再循环 `rstrip('/')`；若尾缀是已知端点
（`/chat-messages`、`/completion-messages`、`/workflows/run`）则剥掉一段。其余原样作为 `api_base`。

- 备选：要求用户改填 `/v1` 根地址 —— 破坏现有 `api_configs` 存量语义，且面板测试已按完整端点填写，故不选。
- 保留原 `base_url` 供日志展示，不覆写配置。

### D2. `app_type` 分发与 workflow 的入参/出参

`DifyAPI.__init__` 读取 `config.app_type`（缺省 `chat`），并持有 `workflow_input_key`（默认 `query`）、
`workflow_output_key`（默认 `text`）。`chat()` 内：

- `chat` → `client.chat_messages(ChatRequest(query=..., conversation_id=..., user=..., response_mode=BLOCKING))`
- `workflow` → `client.run_workflows(WorkflowsRunRequest(inputs=..., user=..., response_mode=BLOCKING))`，
  回复取 `resp.data.outputs.get(output_key)`；键缺失/非 str → 抛错落入 `api_error_reply` 路径。

`workflow_input_key` 支持**多键映射**（真实 workflow 常有多个入参，如 `msgs` + `prompt`）：
以逗号分隔的 `key=value` 对，value 支持占位符（按序替换）：

- `$message` - 用户消息（chat() 的 message 实参）
- `$prompt` - 提示词（chat() 的 prompt 实参）
- `$model` - 模型名（可能为空）
- `$user_key` - 会话身份（如微信 chat_name，可能为空）
- `$history` - 历史消息（渲染为 `角色: 内容` 多行文本，可能为空）
- `$time` / `$date` - 当前时间/日期（本地时区）

未用占位符的 value 按常量原样传入。例：`msgs=$message,prompt=$prompt` →
`inputs={"msgs": 用户消息, "prompt": 提示词}`。解析空结果时退化为单键 `{input_key: message}`，
保持向后兼容。

备选：自动探测（先打 chat 失败再回退 workflow）——不可靠且增加请求开销，弃；
备选：入参仍单键 —— 无法适配 `msgs`+`prompt` 这类真实双入参 app，弃（见
`docs/dify_deploy_config.md` 真实部署案例）。

### D3. 会话存储与 `user_key` 契约

- 所有 API 类 `chat()` 追加 `user_key=None`（有默认值，向后兼容；非 Dify 类忽略）。
- 调用方（`message_handler` 私聊/群聊、`chatlog_manager`）把 `chat_name` 传给 `rec_api.chat(..., user_key=...)`。
- DifyAPI 内部：`redis_key = "dify:conv:" + hashlib.md5(f"{api_base}|{api_key}").hexdigest() + ":" + user_key`；
  `user` 字段 = `f"wxbot_{md5(user_key)[:12]}"`。`user_key` 为 None 时不读写会话（每次新会话）。
- 首次无 id：`conversation_id=""`，响应后 `set()`；后续 `get()` 出 id 携带，响应再覆盖。
- Redis 访问走 `RedisManager`（按 `message_store` 模式用 `config.redis_*` 惰性建实例，受
  `redis_enabled` 开关；`_ApiProxy` / `_TempAPIConfig` 需带出 redis 字段或用 bot 的实例）。

备选：会话直接存 `memory/` 消息存储 —— 语义耦合、清不清不确定，弃；走 Redis 更贴合既有
`redis_enabled` 开关与 fallback。

### D4. 面板配置与数据流

- `config_manager.py` 迁移：对每个 `api_configs[i]` `setdefault("app_type", "chat")`、
  `setdefault("workflow_input_key", "query")`、`setdefault("workflow_output_key", "text")`；
  并从当前接口派生 `self.app_type` 等兼容属性。Dify 的 app 即 `api_key`（`app-xxx`），
  无需独立的 App Key 字段。
- `dashboard.html`：接口项渲染（`~1136`）与新增 JS 模板（`~3240`）都加「应用类型」下拉
  （chat/workflow，仅 `sdk==Dify` 显示）与「入参变量」「输出变量名」输入控件（仅 Dify 且
  workflow 显示）。「入参变量」为**动态多行键值对**（每行：变量名 + 值，值支持 `$message` /
  `$prompt` 占位符或常量，可增删行），保存时 `collectWorkflowInputKey()` 拼回逗号分隔
  `key=value` 配置串；`getApiConfigFromItem`（`~3100`）与 `saveConfig`（`~4100`）一致采集，
  保证编辑/测试/保存一致。
- `web_server._TempAPIConfig`、`wxbot_core._ApiProxy` 同步带出 `app_type` 等字段，测试路由 `_build_test_api_client`
  无需改分支（仍构造 `DifyAPI`），但 `DifyAPI.__init__` 要从代理对象读新属性。

### D5. 错误与降级

`core/dify_client` 抛 `DifyAPIError`（含 SPEC_CODE_ERRORS 映射）。`DifyAPI.chat()` 对任何异常统一
捕获并 `log(WARN/ERROR)` 后返回 `api_error_reply` 同款固定文案，保持 `chat()` 不抛异常的既有行为。
会话读写失败（Redis 不可用且无 fallback）同样降级为"本次不续会话"，不影响回复。

## Risks / Trade-offs

- [旧存量 `api_configs` 无新字段] → 迁移逻辑 `setdefault` 兜底，默认 chat/query/text，无需人工改配置。
- [同一实例多 app 串号] → `api_key`（app 密钥）进会话 key + `user` 派生，三要素隔离；同 `api_key`
  仅当"用户拿同一个 key 配了多个 app"时才会串（风险面收敛到误配）。
- [`strenum`/`httpx-sse` 缺失导致导入失败] → 写进 `requirements.txt`；本机 3.8 低于项目声明 3.9 下限，
  实现后以 `python web_server.py` 冒烟验证导入链。
- [workflow 出参结构非纯字符串（嵌套 dict）] → 取 `outputs[output_key]`，若 `str()` 后为空则走错误回复，
  日志留原文便于用户调配置。
- [行为回退风险：重构后 Dify 聊天结果差异] → 本地 history 拼接逻辑原样保留；阻塞模式 + 纯文本契约不变，
  面板"测试可用性"路由可先验证连通。

## Migration Plan

1. `requirements.txt` 追加 4 依赖并安装（本机补 `httpx-sse`、`strenum`）。
2. 按 tasks 顺序：config 迁移 → 面板字段 → 代理对象 → `DifyAPI` 重写 → 调用方传 `user_key`。
3. 回滚：`git` 层面还原 `ai_api.py` 的 `DifyAPI` 旧实现即可，配置迁移为纯增量字段，
   旧版本读到多余字段无影响。
