# 微信界面操作任务队列与 Redis 集成改造 - 产品需求文档

## Overview
- **Summary**: 将微信机器人的界面操作（发送消息、朋友圈、点赞等）统一纳入任务队列管理，并引入 Redis 作为持久化存储层，替代现有的 WXLock 同步锁机制和本地 JSON 文件存储。同时在管理界面中添加任务队列、消息管理、联系人管理的可视化操作界面。
- **Purpose**: 解决当前同步锁机制的阻塞问题，实现任务排队执行；通过 Redis 实现数据持久化，确保重启后数据不丢失；提供可视化界面方便管理员查看和操作队列、消息、联系人数据。
- **Target Users**: 微信机器人管理员，需要管理任务队列、查看消息状态、管理联系人的运维人员。

## Goals
- 将所有界面操作（发送消息、朋友圈、点赞、好友申请等）统一提交到任务队列，单线程串行执行
- 任务队列支持 Redis 持久化，重启后未完成任务不丢失
- 消息存储迁移到 Redis，支持状态管理和待确认队列
- 联系人数据缓存到 Redis，减少 Chatlog API 调用
- 在管理界面中添加任务队列、消息管理、联系人管理三个标签页
- Redis 不可用时自动降级到本地存储

## Non-Goals (Out of Scope)
- 不实现多机器人集群管理
- 不实现消息推送通知功能
- 不实现复杂的任务调度（如 cron 表达式）
- 不实现联系人分组管理功能

## Background & Context
- 当前系统使用 `threading.Lock` 实现界面操作互斥，存在阻塞问题
- 消息存储使用本地 JSON 文件，性能低且重启后数据丢失
- 联系人数据存储在内存字典中，每次重启需重新获取
- MemoryManager 和 MessageStore 存在数据重叠
- 用户需要在界面上查看和操作任务队列、消息、联系人

## Functional Requirements
- **FR-1**: 创建 RedisManager 模块，统一管理 Redis 连接和操作，支持降级到本地存储
- **FR-2**: 创建 TaskQueue 模块，实现任务队列管理，支持任务提交、执行、取消、历史记录
- **FR-3**: 重构 MessageStore 模块，将存储后端从 JSON 文件改为 Redis，支持状态管理和待确认队列
- **FR-4**: 合并 MemoryManager 到 MessageStore，保留 API 兼容性
- **FR-5**: 迁移联系人数据到 Redis，支持启动时从 Redis 加载
- **FR-6**: 将所有界面操作改为提交任务到队列
- **FR-7**: 添加任务队列、消息管理、联系人管理相关的管理员命令
- **FR-8**: 添加任务队列、消息管理、联系人管理相关的 Web API 接口
- **FR-9**: 在管理界面中添加任务队列、消息管理、联系人管理三个标签页

## Non-Functional Requirements
- **NFR-1**: Redis 默认禁用，不影响现有用户使用
- **NFR-2**: Redis 连接失败时自动降级到本地存储，系统继续运行
- **NFR-3**: 任务队列支持优先级排序，高优先级任务优先执行
- **NFR-4**: 界面操作响应时间 < 500ms
- **NFR-5**: 任务队列历史保留最近 500 条记录

## Constraints
- **Technical**: Python 3.x，Windows 系统，Redis 5.0+（可选）
- **Business**: 需保持与现有 API 的兼容性，不破坏现有功能
- **Dependencies**: 依赖 redis-py 库（可选安装）

## Assumptions
- 用户可根据需要选择是否启用 Redis
- Redis 不可用时用户接受使用本地存储降级
- 任务队列单线程执行满足性能需求

## Acceptance Criteria

### AC-1: RedisManager 模块创建
- **Given**: 系统配置文件中已添加 Redis 相关配置项
- **When**: 系统启动并初始化 RedisManager
- **Then**: RedisManager 成功连接到 Redis（如果启用）或自动降级到本地存储
- **Verification**: `programmatic`

### AC-2: TaskQueue 模块创建
- **Given**: TaskQueue 已初始化
- **When**: 提交多个任务到队列
- **Then**: 任务按优先级顺序串行执行，执行结果正确存储
- **Verification**: `programmatic`

### AC-3: MessageStore 重构
- **Given**: MessageStore 已重构为 Redis 后端
- **When**: 保存消息、设置状态、添加待确认消息
- **Then**: 数据正确存储到 Redis，重启后数据不丢失
- **Verification**: `programmatic`

### AC-4: MemoryManager 合并
- **Given**: MemoryManager 已改为代理模式
- **When**: 调用 MemoryManager 的 get_messages 方法
- **Then**: 返回与之前相同格式的消息历史
- **Verification**: `programmatic`

### AC-5: 联系人数据迁移
- **Given**: Redis 已启用且有联系人缓存
- **When**: 系统启动
- **Then**: 联系人数据从 Redis 加载，无需重新调用 Chatlog API
- **Verification**: `programmatic`

### AC-6: 界面操作任务化
- **Given**: 任务队列已启用
- **When**: 发送消息、发送朋友圈等界面操作
- **Then**: 操作以任务形式提交到队列，不阻塞调用线程
- **Verification**: `programmatic`

### AC-7: 管理员命令
- **Given**: 管理员发送任务队列相关命令
- **When**: 发送 `/任务队列`、`/任务列表`、`/任务历史`、`/清空队列`、`/取消任务`、`/Redis状态`、`/Redis测试`、`/联系人缓存` 命令
- **Then**: 命令正确执行并返回结果
- **Verification**: `human-judgment`

### AC-8: Web API 接口
- **Given**: Web 服务器已启动
- **When**: 调用任务队列、消息管理、联系人管理相关 API
- **Then**: 返回正确的 JSON 响应
- **Verification**: `programmatic`

### AC-9: 界面标签页
- **Given**: 管理界面已打开
- **When**: 点击任务队列、消息管理、联系人管理标签页
- **Then**: 页面正确显示数据，操作按钮可正常使用
- **Verification**: `human-judgment`

## Open Questions
- [ ] Redis 降级时，本地存储的数据是否需要同步到 Redis（当 Redis 恢复后）？
- [ ] 任务队列是否需要支持任务优先级动态调整？
- [ ] 界面是否需要实时推送任务状态变化？