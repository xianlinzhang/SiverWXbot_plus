## Purpose

消费 we-mp-rss 推送的同城信息（顺风车/招聘）Redis 队列，经人工确认后发布到微信朋友圈，并按契约回报发布回执给生产者。

## ADDED Requirements

### Requirement: 消费远程推送队列
系统 SHALL 按配置轮询远程 Redis 队列 `wemp:deal:push:queue`，取出消息并解析为 JSON，识别 `source`（`shun_fen_che` / `recruitment`）。仅在总开关开启时消费。

#### Scenario: 队列中有消息
- **WHEN** 远程队列存在待消费消息且总开关开启
- **THEN** 系统取出消息并进入待发布流程，远程回执保持 `QUEUED`

#### Scenario: 队列为空
- **WHEN** 远程队列为空
- **THEN** 系统不消费，按轮询间隔等待下一次

#### Scenario: 能力未启用
- **WHEN** 总开关关闭
- **THEN** 系统不访问远程队列

### Requirement: 渲染纯文本朋友圈文案
系统 SHALL 将顺风车/招聘消息渲染为纯文本朋友圈文案。顺风车文案包含出发地、目的地、时间、车型、人数、电话；招聘文案包含标题、类型、公司、地点、薪资、联系人、电话。空字段跳过，忽略图片字段，可配置前缀，超长按上限截断。

#### Scenario: 顺风车消息渲染
- **WHEN** 消息 `source` 为 `shun_fen_che` 且含出发地与目的地
- **THEN** 文案包含出发地、目的地与联系电话

#### Scenario: 招聘消息渲染
- **WHEN** 消息 `source` 为 `recruitment`
- **THEN** 文案包含标题与公司等招聘信息

#### Scenario: 空字段处理
- **WHEN** 记录某可选字段为空
- **THEN** 文案中跳过该字段，不输出空行

#### Scenario: 超长截断
- **WHEN** 渲染后文案超过配置上限
- **THEN** 文案被截断到配置上限长度

#### Scenario: 前缀
- **WHEN** 配置了文案前缀
- **THEN** 前缀出现在文案开头

### Requirement: 待发布池持久化与状态机
系统 SHALL 将待发布消息持久化到本地存储，每条记录带四态状态：`pending`（待发布）、`publishing`（发布中）、`published`（已发布）、`failed`（发布失败）。bot 重启后待发布记录不丢失。

#### Scenario: 新消息入池
- **WHEN** 消费到一条新消息
- **THEN** 记录以 `pending` 状态写入待发布池

#### Scenario: 重启恢复
- **WHEN** bot 重启且存在待发布记录
- **THEN** 面板仍能列出这些记录

#### Scenario: 状态流转发布中
- **WHEN** 用户触发发布且发送任务正在执行
- **THEN** 记录状态为 `publishing`

#### Scenario: 状态流转成功
- **WHEN** 发送任务成功
- **THEN** 记录状态为 `published` 并从待发布列表移除

#### Scenario: 状态流转失败
- **WHEN** 发送任务最终失败
- **THEN** 记录状态为 `failed` 且保留在待发布列表

### Requirement: 人工发布与回执回报
系统 SHALL 在用户确认发布后提交朋友圈发送任务，且仅在发送成功后把远程回执 `wemp:deal:push:status` 对应 field 写为 `PUBLISHED`。发布前若远程回执已是 `PUBLISHED`，则拒绝本次发布并提示。

#### Scenario: 发布成功回报回执
- **WHEN** 用户点击发布且朋友圈发送成功
- **THEN** 系统将远程回执 field 写为 `PUBLISHED`

#### Scenario: 已发布记录拒绝重复
- **WHEN** 用户点击发布但远程回执 field 已是 `PUBLISHED`
- **THEN** 系统拒绝本次发布并提示该记录已发布

#### Scenario: 发送失败不回执
- **WHEN** 用户点击发布但朋友圈发送最终失败
- **THEN** 远程回执保持 `QUEUED`

### Requirement: 人工丢弃
系统 SHALL 支持"丢弃"动作：直接把远程回执 field 写为 `PUBLISHED`（放弃发布），并从待发布池移除该记录。

#### Scenario: 丢弃记录
- **WHEN** 用户点击丢弃
- **THEN** 远程回执写为 `PUBLISHED` 且本地记录从待发布列表移除

### Requirement: 人工重推
系统 SHALL 支持"重推"动作：删除远程回执 field，生产者下次轮询将重新入队，该记录会再次进入待发布池。系统 SHALL NOT 对待发布记录做本地去重。

#### Scenario: 重推记录
- **WHEN** 用户点击重推
- **THEN** 远程回执 field 被删除，本地记录从待发布列表移除

#### Scenario: 重推后重新入池
- **WHEN** 重推的记录被生产者重新推送入队
- **THEN** 系统再次将其写入待发布池

### Requirement: 待发布池容量上限
系统 SHALL 支持配置待发布池上限；达到上限时停止从远程拉取新消息并记录告警。

#### Scenario: 达到池上限
- **WHEN** 待发布池记录数达到配置上限
- **THEN** 系统暂停拉取新消息并记录告警

### Requirement: 远程连接独立性与容错
系统 SHALL 使用独立于本地 Redis 的远程连接，且不允许回退到本地文件存储；远程连接失败时仅记录日志并重试，不影响 bot 其他功能。

#### Scenario: 远程连接不可用
- **WHEN** 远程 Redis 无法连接
- **THEN** 系统记录错误日志并持续重试，bot 其余功能不受影响

### Requirement: 配置项
系统 SHALL 提供以下可配置项：总开关、远程主机、远程端口、远程 db、远程密码、轮询间隔、朋友圈可见范围、文案前缀、文案截断长度、待发布池上限。配置修改后热重载生效。

#### Scenario: 配置热重载生效
- **WHEN** 用户修改配置并保存
- **THEN** 消费者按新配置生效（连接参数、轮询间隔、可见范围、上限等）
