# SiverWXbot 消息存储与标注层优化 - 产品需求文档

## Overview
- **Summary**: 在现有微信机器人架构中增加消息存储与标注层，实现消息未读设置、私聊回复确认机制、消息与回复的对应关系，并添加微信界面操作锁以避免并发操作混乱。
- **Purpose**: 解决当前消息处理同步直接回复、无中间存储层、消息与回复无对应关系、多任务并发操作微信界面导致混乱的问题。
- **Target Users**: 微信机器人管理员、消息审核人员、普通用户

## Goals
- 在 Chatlog 监听和消息发送之间增加一层数据存储和标注
- 支持消息未读状态设置
- 实现私聊自动回复前确认机制（自动和人工都支持）
- 建立消息与回复的对应关系
- 添加微信界面操作锁机制，支持手动占用和释放

## Non-Goals (Out of Scope)
- 不修改现有的 AI 接口逻辑
- 不改变现有的监听模式（白名单/黑名单）
- 不新增 Web UI 界面
- 不实现消息队列的持久化重试机制

## Background & Context
- 当前消息处理流程：消息监听 → MessageHandler → AI API → 发送消息
- 现有模块：chatlog_manager.py、message_handler.py、listen_manager.py、memory_manager.py
- 约束：拆分出来的文件必须放到 core 目录

## Functional Requirements

### FR-1: 消息存储层
- **FR-1.1**: 所有接收的消息必须先保存到消息存储层
- **FR-1.2**: 消息存储支持按会话分文件存储
- **FR-1.3**: 支持消息记录的持久化和加载

### FR-2: 消息未读设置
- **FR-2.1**: 支持将消息标记为未读状态
- **FR-2.2**: 支持查询未读消息列表

### FR-3: 私聊回复确认
- **FR-3.1**: 支持开启/关闭私聊回复确认开关
- **FR-3.2**: 开启后，私聊消息进入待确认队列
- **FR-3.3**: 支持通过命令手动确认或拒绝回复
- **FR-3.4**: 支持设置确认等待超时时间

### FR-4: 消息回复对应关系
- **FR-4.1**: 每条消息记录必须关联其回复消息（如果有）
- **FR-4.2**: 支持查询某条消息的回复内容

### FR-5: 微信界面操作锁
- **FR-5.1**: 所有微信界面操作必须先获取锁
- **FR-5.2**: 支持手动占用和释放锁
- **FR-5.3**: 未获取锁的任务延迟执行
- **FR-5.4**: 支持锁超时自动释放
- **FR-5.5**: 支持查看锁状态

## Non-Functional Requirements

### NFR-1: 性能
- 消息存储写入延迟 < 100ms
- 锁获取/释放操作延迟 < 10ms

### NFR-2: 可靠性
- 锁机制具备超时保护，防止死锁
- 消息存储采用事务性写入，保证数据一致性

### NFR-3: 可维护性
- 代码符合项目现有风格和约定
- 所有函数添加函数级注释
- 保持向后兼容性

## Constraints

### Technical
- 所有新增文件必须放到 core 目录
- Python 3.x 语法兼容
- 不新增第三方依赖

### Dependencies
- 依赖 wxautox4 库进行微信操作
- 依赖现有 logger 模块进行日志记录

## Assumptions
- 微信机器人运行在单进程环境
- 消息存储使用 JSON 文件格式
- 锁机制基于 threading.Lock 实现

## Acceptance Criteria

### AC-1: 消息存储功能
- **Given**: 机器人收到一条新消息
- **When**: 消息处理流程启动
- **Then**: 消息先保存到消息存储层，生成唯一消息 ID
- **Verification**: `programmatic`

### AC-2: 消息未读设置
- **Given**: 存在已处理的消息
- **When**: 执行设置未读命令
- **Then**: 消息状态变为未读，可通过查询命令查看
- **Verification**: `programmatic`

### AC-3: 私聊回复确认开启
- **Given**: 私聊回复确认开关已开启
- **When**: 收到私聊消息
- **Then**: 消息进入待确认队列，不自动回复
- **Verification**: `programmatic`

### AC-4: 回复确认与拒绝
- **Given**: 存在待确认消息
- **When**: 执行确认/拒绝命令
- **Then**: 确认后自动发送回复，拒绝后不回复
- **Verification**: `programmatic`

### AC-5: 消息回复对应关系
- **Given**: 消息已回复
- **When**: 查询消息记录
- **Then**: 消息记录包含关联的回复内容和回复时间
- **Verification**: `programmatic`

### AC-6: 微信界面操作锁
- **Given**: 锁已被占用
- **When**: 另一个任务尝试操作微信界面
- **Then**: 任务等待直到获取到锁后才执行操作
- **Verification**: `programmatic`

### AC-7: 锁手动控制
- **Given**: 锁状态为空闲
- **When**: 执行占用/释放锁命令
- **Then**: 锁状态正确更新，可通过状态命令查看
- **Verification**: `programmatic`

### AC-8: 锁超时释放
- **Given**: 锁已被占用超过超时时间
- **When**: 检查锁状态
- **Then**: 锁自动释放，状态变为空闲
- **Verification**: `programmatic`

## Open Questions
- [ ] 消息存储是否需要支持导出功能？
- [ ] 是否需要支持批量确认/拒绝操作？
