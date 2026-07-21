# Chatlog 监听模式下停止 wxautox4 UI 监听 - Product Requirement Document

## Overview
- **Summary**: 当启用 Chatlog 监听模式时，停止 wxautox4 的 UI 消息监听线程，避免资源浪费和潜在冲突
- **Purpose**: 当前实现中，即使启用了 Chatlog 监听模式，wxautox4 的 UI 监听线程仍在后台运行并通过界面获取新消息，这会导致资源浪费和潜在的性能问题
- **Target Users**: 使用 Chatlog 监听模式的 SiverWXbot_plus 用户

## Goals
- [ ] 当 `chatlog_listen_switch=True` 时，停止 wxautox4 的 UI 消息监听线程
- [ ] 当 `chatlog_listen_switch=True` 时，不注册 wxautox4 的消息监听器
- [ ] 确保 Chatlog 监听模式下完全不依赖 UI 自动化获取消息

## Non-Goals (Out of Scope)
- [ ] 不修改 wxautox4 库的核心代码
- [ ] 不改变 Chatlog 监听模式的其他功能

## Background & Context
- 当前实现中，`wxautox4.wx.Listener` 类会启动一个后台线程，每隔一段时间调用 `_get_listen_messages()`
- `_get_listen_messages()` 会遍历所有监听对象，调用 `chat.GetNewMessage()` 通过界面获取新消息
- 当 `chatlog_listen_switch=True` 时，`message_handle_callback` 会立即返回，不处理消息
- 但 wxautox4 的 UI 监听线程仍然在运行，仍然在通过界面获取新消息
- 这导致资源浪费和潜在的性能问题

## Functional Requirements
- **FR-1**: 当 `chatlog_listen_switch=True` 时，在初始化阶段不注册 wxautox4 的消息监听器
- **FR-2**: 当 `chatlog_listen_switch=True` 时，停止已运行的 wxautox4 UI 监听线程
- **FR-3**: 当 `chatlog_listen_switch=False` 时，恢复正常的 wxautox4 UI 监听

## Non-Functional Requirements
- **NFR-1**: 修改应最小化，不影响现有功能
- **NFR-2**: 确保向后兼容性，不破坏现有配置

## Constraints
- **Technical**: 不能修改 wxautox4 库的核心代码，只能在 SiverWXbot_plus 层面进行控制
- **Dependencies**: 依赖 wxautox4 的 `StopListening()` 方法和 `AddListenChat()`/`RemoveListenChat()` 方法

## Assumptions
- [ ] wxautox4 的 `StopListening()` 方法可以停止监听线程
- [ ] wxautox4 的 `RemoveListenChat()` 方法可以移除监听器
- [ ] `WXBot.init_wx_listeners()` 方法负责注册所有监听器

## Acceptance Criteria

### AC-1: Chatlog 模式下不注册 UI 监听器
- **Given**: `chatlog_listen_switch=True`
- **When**: 初始化微信监听器 (`init_wx_listeners`)
- **Then**: 不调用 `wx.AddListenChat()` 注册任何消息监听器
- **Verification**: `programmatic`
- **Notes**: 通过检查日志或代码逻辑验证

### AC-2: Chatlog 模式下停止 UI 监听线程
- **Given**: `chatlog_listen_switch=True`
- **When**: 机器人启动
- **Then**: 调用 `wx.StopListening()` 停止 wxautox4 的监听线程
- **Verification**: `programmatic`
- **Notes**: 通过检查监听线程状态验证

### AC-3: 正常模式下恢复 UI 监听
- **Given**: `chatlog_listen_switch=False`
- **When**: 初始化微信监听器 (`init_wx_listeners`)
- **Then**: 正常注册所有消息监听器，wxautox4 监听线程正常运行
- **Verification**: `programmatic`

## Open Questions
- [ ] wxautox4 的 `StopListening()` 方法是否会完全停止监听线程？
- [ ] 是否需要在 Chatlog 模式下禁用 `KeepRunning()` 方法？