# AGENTS.md

微信自动化客服机器人（SiverWXbot_plus V4.7.27）。集成 `wxautox4`（UI 自动化）+ `Chatlog`（稳定消息源）+ 多 AI 平台，实现：AI 智能回复 + 关键词自动应答 + 同城信息数据搜集（提供车/出售/出租/招聘/求职等）。Windows-only，Python 3.9~3.13。

## 启动与入口

- **真正的入口是 `python web_server.py`**（Flask 管理面板，端口自动选 10001~11000 首个可用，自动开浏览器）。`wxbot_core.py` 可单独 `python wxbot_core.py` 跑，但部署走面板。
- 面板登录后点「启动机器人」→ `/start_bot` 路由在线程中 `pythoncom.CoInitialize()` 后创建 `WXBot().run()`（daemon 线程）。改代码后测试 = 跑 web_server + 面板启动。Bot 主循环在 `wxbot_core.py:main()`。
- 浏览器默认账密：`admin` / `123456`（存 `config/admin.json`）。

## 架构地图

- `web_server.py`（~2900 行单文件）— 面板全部路由/配置/启停。改 UI/配置接口都在这里。
- `wxbot_core.py` — `WXBot` 主类，逻辑大多**委托**给 `core/` 模块（薄转发层）。
- `core/` — 实际业务代码：`config_manager`（配置）、`message_handler`（AI 回复/关键词/转发）、`command_handler`（微信管理命令）、`listen_manager`（白/黑名单监听）、`chatlog_manager`（Chatlog 轮询）、`ai_api`（OpenAI/Dify/Coze/Dus）、`memory_manager`+`message_store`（记忆/消息存储）、`redis_manager`、`task_queue`、`wx_utils`（朋友圈/新好友/定时任务）。
- `wxautox4/` — **随仓内嵌的授权内核库（非 pip 依赖，需授权激活）**。正常开发别改这里；改业务逻辑去 `core/`。
- `templates/` — 面板前端（`dashboard.html` 等）。

## 配置与敏感数据

- `config/` 和 `memory/` 已被 `.gitignore` 忽略——内含**真实 API Key、面板密码、聊天记录**。切勿提交。
- `config/config.json`：全部业务配置，`keyword_dict` 是同城信息关键词应答表（提供车/求车/招聘/求职/出售/出租 → 固定回复）。配置支持运行时热重载（面板保存或 `/更新配置`）。
- Prompt 存 `config/prompt/*.md`，文件名即 Prompt 名；用户/群可通过 `chat_prompt_map`/`group_prompt_map` 单独绑定（本部署：主号 → `客服助手`，API 索引 0）。
- 当前部署关键开关：`chatlog_listen_switch=true`（Chatlog 监听）、`redis_enabled=true`、`memory_switch=true`、`chat_keyword_switch=true`。
- 版本号在**两处**同步修改：`wxbot_core.py` 顶部 `version`/`version_log` + `docs/version.json`（web_server 从 wxbot_core 导入）。

## 运行前置（改代码前先确认环境）

- Windows + 微信 PC `4.1.9.35`（README/docs/version.json 均提示版本匹配是首要排错项）。
- `chatlog_listen_switch=true` 时需本地 `http://127.0.0.1:5030` 的 Chatlog 服务（[sjzar/chatlog](https://github.com/sjzar/chatlog)）在跑；API 结构与消息字段定义见 `.trae/specs/chatlog-integration/spec.md` 和 `chatlog_client.py`。
- Redis `127.0.0.1:6379`，不可用时自动降级到 `fallback_redis.json`。
- wxautox4 授权：`check_license` 校验，未激活会失败。

## 测试

- **无 pytest 等框架**，无 lint/typecheck 命令。`requirements.txt` 只有运行依赖。
- 现有脚本需真实登录微信才能跑：`demo.py`（wxautox4 API 演示）、`test_moment.py`（朋友圈功能测试，mock 掉 redis）、`test_account.py`、`wxautox4/tests/`。
- 手动验证方式：改完跑 `python web_server.py`，面板看日志（`panel_logs/log_YYMMDD.txt`）。

## 文档与规范

- `docs/tech_doc.md` 架构/模块文档，`README.md` 全量配置字段表——新配置项改动要同步这里。
- `.trae/specs/` 是近期功能的设计规格（chatlog 集成、task_queue redis、朋友圈拟人化等），新功能前先看有没有对应 spec。
- 仓库启用了 OpenSpec 工作流（`openspec/` + `.opencode/skills/openspec-*`），重大改动走 propose/apply/archive。

## 杂项

- 所有源码 UTF-8。PowerShell 控制台输出中文可能乱码（`�ͷ�����.md` 这种），是显示问题，文件内容正常。
- 微信 UI 操作（发消息/朋友圈/切窗口）均走 wxautox4，改动涉及微信交互时先在 `demo.py`/`test_moment.py` 验证，避免直接改内核库。
