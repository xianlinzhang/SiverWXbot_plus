# 自部署 Dify Workflow App 接入配置（部署参考）

> 本文档记录本部署实际使用的 Dify workflow app 配置，供后续接入/排障参考。
> 对应改造见 `openspec/changes/dify-client-integration`。

## 应用信息

| 配置项 | 值 |
|---|---|
| Dify 部署 | 自部署（非云端） |
| API Base | `http://dify.liancb.cn/v1` |
| App Key / API Key | `app-pirTXPSboGWKOXCO1zGGiJru`（Dify 的 API Key 即 App Key，填面板的 API Key） |
| 应用类型（app_type） | `workflow` |
| 工作流端点 | `POST /workflows/run` |

## 入参变量（workflow inputs）

| 变量名 | 说明 | 机器人侧来源 |
|---|---|---|
| `msgs` | 用户消息 | 微信消息内容 |
| `prompt` | 提示词 | 机器人当前生效的 prompt（如 `_effective_prompt`） |

> 注意：该 app 有**两个**入参变量。已通过 `dify-client-integration` 的**多键映射**
> 支持：`workflow_input_key` 填写键值对 `msgs=$message,prompt=$prompt`。
> 支持的全部占位符：`$message`（用户消息）、`$prompt`（机器人当前生效的 prompt，如
> `_effective_prompt`）、`$model`（模型名）、`$user_key`（会话身份/chat_name）、
> `$history`（历史消息多行文本）、`$time`/`$date`（当前时间/日期）；未用占位符的值为常量。
> 入参映射实现见 `core/ai_api.py:_build_workflow_inputs`。

## 出参变量（workflow outputs）

| 变量名 | 说明 | 机器人侧处理 |
|---|---|---|
| （回答字符串） | 工作流最终回复文本 | 作为 AI 回复发出；对应 `workflow_output_key` |

## 面板填写示例

在「API 接口配置」中选择 SDK=Dify 时：

- **Base URL**：`http://dify.liancb.cn/v1`（或 `.../workflows/run`，程序会自动剥除端点尾缀）
- **API Key**：该 app 的密钥（`app-xxx`，面板自动掩码；Dify 的 API Key 即 App Key，无需单独填 App Key）
- **应用类型**：Workflow（工作流）
- **入参变量**：两行键值对 —— 变量名 `msgs` 值 `$message`、变量名 `prompt` 值 `$prompt`（占位符见上文，也可填常量）
- **输出变量名**：`text` 或该 app 出参的实际变量名

## 会话说明

workflow 型 app 每次运行相互独立，不依赖 Dify 服务端 `conversation_id` 续会话；
`api_key`（app 密钥）仍用于 Redis 会话 key 的隔离前缀，避免同实例多 app 串号。
