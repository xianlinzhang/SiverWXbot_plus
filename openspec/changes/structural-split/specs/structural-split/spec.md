# Spec: 结构拆分（web_server 模块化 + wxbot_core 转发收敛）

能力：`structural-split`

## 目的

把「大而黏」的单文件/转发样板拆成有边界的模块，提升可维护性；对外行为完全不变。

## ADDED Requirements

### Requirement: web_server 按职责拆 blueprint/模块
系统 SHALL 将 `web_server.py` 的路由按域拆分为多个 blueprint / 模块，通过 `create_app()` 组装；
所有既有 URL 与路由签名 MUST NOT 变更。

#### Scenario: 启动后既有路由仍可达
- GIVEN 重构后应用通过 `create_app()` 启动
- WHEN 依次访问既有路由（`/dashboard`、`/save_config`、`/api/tasks`、`/memory/list` 等）
- THEN 响应与拆分前一致
- AND 无路由缺失或 URL 变更

### Requirement: 配置字段强制器收敛为集中表
系统 SHALL 将 `_coerce_*_fields` 字段强制逻辑抽为集中的 schema 表，新增配置字段只需在该
集中表登记，MUST NOT 散落在单文件不同位置手写多处。

#### Scenario: 新增配置字段只改一处
- GIVEN 需要新增一个面板配置开关字段
- WHEN 开发者在集中表登记该字段
- THEN 该字段的加载/保存/强制在统一入口处理，无需在 web_server 多处游走

### Requirement: wxbot_core 纯机械转发不再手抄膨胀
系统 SHALL 让 `WXBot` 的 77 个纯透传转发通过组合+聚合对象暴露（或生成式转发表）收敛，
MUST NOT 要求每个新增 `core` 方法都在 `wxbot_core` 手抄一次。

#### Scenario: 新功能无需再抄转发
- GIVEN 未来新增一个 `message_handler` 方法
- WHEN 需要从外部调用
- THEN 通过聚合对象直接访问或生成式转发获得
- AND 无需手工在 `wxbot_core` 追加一行转发

## MODIFIED Requirements

无（对外协议、URL、配置结构、登录鉴权均不变）。

## Scenario: 重构不改运行行为
- GIVEN 拆分完成后启动 `python web_server.py`
- THEN 面板登录、配置保存、prompt、备份、任务/消息/记忆/统计/联系人/redis/远程面板 API
      行为均与拆分前一致