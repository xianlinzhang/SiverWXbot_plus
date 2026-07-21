# Chatlog 消息处理优化 - Product Requirement Document

## Overview
- **Summary**: 新建 `chatlog_process_message` 方法，用于在 Chatlog 监听模式下直接处理消息并发送回复，无需获取子窗口对象。
- **Purpose**: 解决当前 `chatlog_listen_loop` 需要依赖子窗口对象才能发送消息的问题，简化消息处理流程，提高稳定性。
- **Target Users**: 使用 Chatlog 监听模式的机器人用户

## Goals
- 新建 `chatlog_process_message` 方法，支持直接通过 `self.wx.SendMsg(who=chat_name, msg=msg)` 发送消息
- 修改 `chatlog_listen_loop` 方法，调用新方法替代原有的子窗口+`process_message` 逻辑
- 保持与现有功能的兼容性（群聊处理、管理员命令、AI回复等）

## Non-Goals (Out of Scope)
- 修改 `process_message` 和 `wx_send_ai` 方法的现有逻辑
- 支持 `message.quote()` 引用回复功能（需要子窗口支持）

## Background & Context
- 当前 `chatlog_listen_loop` 在处理消息时需要先获取子窗口对象（`_get_verified_subwindow` 或 `add_chat_to_listen`），然后调用 `process_message`
- `process_message` 方法内部使用 `chat.SendMsg()` 发送消息
- 可以通过 `self.wx.SendMsg(who=chat_name, msg=msg)` 直接发送消息，无需子窗口

## Functional Requirements
- **FR-1**: 新建 `chatlog_process_message` 方法，接收 `chat_name`、`msg_dict` 参数
- **FR-2**: 方法内部实现消息处理逻辑（群聊、管理员命令、私聊AI回复）
- **FR-3**: 使用 `self.wx.SendMsg(who=chat_name, msg=msg)` 直接发送消息，无需子窗口
- **FR-4**: 修改 `chatlog_listen_loop` 方法，调用新方法替代原有逻辑

## Non-Functional Requirements
- **NFR-1**: 代码结构清晰，与现有逻辑保持一致
- **NFR-2**: 错误处理完善，单条消息处理失败不影响其他消息

## Constraints
- **Technical**: 需要使用 `self.wx.SendMsg(who=chat_name, msg=msg)` 方式发送消息
- **Dependencies**: 依赖 `_convert_chatlog_msg` 方法转换消息对象

## Assumptions
- `self.wx.SendMsg` 方法支持通过 `who` 参数指定接收者
- `chat_name` 可以作为 `who` 参数的值正确匹配联系人

## Acceptance Criteria

### AC-1: 新方法创建成功
- **Given**: `wxbot_core.py` 文件存在
- **When**: 添加 `chatlog_process_message` 方法
- **Then**: 方法被正确定义，包含必要的参数和逻辑
- **Verification**: `programmatic`

### AC-2: 私聊消息处理
- **Given**: Chatlog 监听模式开启，收到私聊消息
- **When**: `chatlog_process_message` 被调用
- **Then**: AI 回复被正确发送给联系人
- **Verification**: `human-judgment`

### AC-3: 群聊消息处理
- **Given**: Chatlog 监听模式开启，收到群聊消息
- **When**: `chatlog_process_message` 被调用
- **Then**: 群聊关键词回复或 AI 回复被正确发送到群聊
- **Verification**: `human-judgment`

### AC-4: 管理员命令处理
- **Given**: Chatlog 监听模式开启，收到管理员命令
- **When**: `chatlog_process_message` 被调用
- **Then**: 命令被正确解析和执行
- **Verification**: `human-judgment`

### AC-5: 子窗口不再被使用
- **Given**: Chatlog 监听模式开启
- **When**: 处理消息时
- **Then**: 不再调用 `_get_verified_subwindow` 或 `add_chat_to_listen`
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要支持群聊的 `@` 回复功能？（当前使用 `chat.SendMsg(at=...)`，可能需要特殊处理）
