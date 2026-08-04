## 1. 依赖与配置迁移

- [x] 1.1 `requirements.txt` 追加 `httpx` / `httpx-sse` / `pydantic` / `strenum`，并安装缺失项（conda env `SiverWXbot_plus` 补 `httpx-sse`、`strenum`）
- [x] 1.2 `core/config_manager.py` 对 `api_configs[i]` 迁移新增字段：`app_type`(chat)、`workflow_input_key`("query")、`workflow_output_key`("text")，并派生 `self.app_type` 等兼容属性（Dify app 由 `api_key` 标识，无独立 App Key 字段）

## 2. 面板与代理对象字段

- [x] 2.1 `templates/dashboard.html` 接口项渲染模板（~1136）加「应用类型」下拉与「入参变量」（动态多行键值对）「输出变量名」输入控件（Dify 才显示，入参/输出仅 workflow 显示）
- [x] 2.2 `templates/dashboard.html` 新增接口 JS 模板（~3240）同步加上述控件
- [x] 2.3 `templates/dashboard.html` `collectWorkflowInputKey` + `getApiConfigFromItem`（~3110）与 `saveConfig`（~4100）采集/拼接入参映射
- [x] 2.4 `web_server.py` `_TempAPIConfig` 带出 `app_type` / `workflow_input_key` / `workflow_output_key`
- [x] 2.5 `wxbot_core.py` `_ApiProxy` 带出上述 3 字段

## 3. DifyAPI 重写

- [x] 3.1 `core/ai_api.py:DifyAPI.__init__` 解析 `base_url` → `api_base`（去端点尾缀/尾斜杠/query），构造 `core.dify_client.Client`
- [x] 3.2 惰性创建 `RedisManager`（`message_store` 模式，受 `redis_enabled` 开关）用于会话存储
- [x] 3.3 实现 `_resolve_conv_id` / `_save_conv_id`：Redis key = `dify:conv:{md5(api_base|api_key)}:{user_key}`，`user` 字段 = `wxbot_{md5(user_key)[:12]}`
- [x] 3.4 实现 `_chat_chatflow`：`client.chat_messages(ChatRequest(query, conversation_id, user, BLOCKING))`，返回 `answer` 并回存 `conversation_id`
- [x] 3.5 实现 `_chat_workflow`：`client.run_workflows(WorkflowsRunRequest(inputs, user, BLOCKING))`，回复取 `data.outputs[workflow_output_key]`
- [x] 3.7 实现 `_build_workflow_inputs` 多键映射：解析 `workflow_input_key`（`msgs=$message,prompt=$prompt` 格式），占位符含 `$message`/`$prompt`/`$model`/`$user_key`/`$history`/`$time`/`$date`，解析为空时退化为 `{workflow_input_key: message}`
- [x] 3.8 移除 `dify_app_key` 概念：会话隔离改用 `api_key`（Dify app 密钥 `app-xxx` 即 app 标识），面板/代理/配置层同步删除该字段
- [x] 3.9 `_chat_workflow`/`chat()` 把 `model`、`history` 透传给入参占位符替换
- [x] 3.6 `chat()` 按 `app_type` 分发，捕获 `DifyAPIError` 等异常并统一返回固定错误文案；本地 history 拼接逻辑原样保留

## 4. 调用方契约扩展

- [x] 4.1 所有 API 类（OpenAIAPI/CozeAPI/DusAPI/DifyAPI）`chat()` 增加可选参数 `user_key=None`（非 Dify 忽略）
- [x] 4.2 `core/message_handler.py` 私聊路径 `chat(..., user_key=chat_name)`（含图片识别分支）
- [x] 4.3 `core/chatlog_manager.py` 私聊/群聊路径 `chat(..., user_key=...)`

## 5. 验证

- [x] 5.1 安装依赖后 `python -c "import core.dify_client"` 确认导入链无错
- [x] 5.4 多键映射 mock 验证：`workflow_input_key="msgs=$message,prompt=$prompt"` 时请求 `inputs` 含 `msgs`+`prompt` 且值正确（本地 mock server 已验）
- [ ] 5.2 `python web_server.py` 面板冒烟：接口配置项显示新字段、保存/加载不丢、测试可用性路由对 Dify chat/workflow 各验一次
- [ ] 5.3 面板启动机器人，对自部署 Dify 的 chatflow 与 workflow 各发一条消息，验证回复与（chat 型）多轮会话延续
