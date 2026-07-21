# Chatlog 监听模式全局检查 - Product Requirement Document

## Overview
- **Summary**: 全局检查并修复当 `chatlog_listen_switch=True` 时，所有消息获取应通过 Chatlog API，界面操作（发送消息、获取子窗口等）仍交给 wxauto
- **Purpose**: 当前实现中，虽然 `init_wx_listeners()` 已跳过 UI 监听器注册，但 `ALLListen_mode()` 等方法仍可能通过界面获取消息，需要全面检查并修复
- **Target Users**: 使用 Chatlog 监听模式的 SiverWXbot_plus 用户

## Goals
- [ ] 全局检查所有通过界面获取消息的代码路径
- [ ] 确保 `chatlog_listen_switch=True` 时，所有消息获取通过 Chatlog API
- [ ] 确保界面操作（发送消息、获取子窗口等）仍正常使用 wxauto

## Non-Goals (Out of Scope)
- [ ] 不修改 wxautox4 库的核心代码
- [ ] 不改变消息发送功能

## Background & Context
- 当前已修改 `init_wx_listeners()` 跳过 UI 监听器注册
- 当前已修改 `message_handle_callback()` 在 Chatlog 模式下立即返回
- 当前已修改主循环在 Chatlog 模式下调用 `chatlog_listen_loop()` 而非 `ALLListen_mode()`
- 但仍有其他代码路径可能通过界面获取消息，需要全局检查

## Functional Requirements
- **FR-1**: 当 `chatlog_listen_switch=True` 时，`ALLListen_mode()` 方法应跳过执行
- **FR-2**: 当 `chatlog_listen_switch=True` 时，`get_next_new_message()` 方法应跳过执行
- **FR-3**: 当 `chatlog_listen_switch=True` 时，`new_msg_get()` 方法应跳过执行
- **FR-4**: 当 `chatlog_listen_switch=True` 时，`new_msg_get_plus()` 方法应跳过执行
- **FR-5**: 发送消息、获取子窗口等界面操作仍正常使用 wxauto

## Non-Functional Requirements
- **NFR-1**: 修改应最小化，不影响现有功能
- **NFR-2**: 确保向后兼容性

## Constraints
- **Technical**: 不能修改 wxautox4 库的核心代码
- **Dependencies**: 依赖 wxautox4 的界面操作方法

## Assumptions
- [ ] `ALLListen_mode()` 只在全局监听模式下调用
- [ ] `new_msg_get()` 和 `new_msg_get_plus()` 只在 UI 监听模式下调用

## Acceptance Criteria

### AC-1: Chatlog 模式下 ALLListen_mode() 跳过执行
- **Given**: `chatlog_listen_switch=True`
- **When**: 主循环调用 `ALLListen_mode()`
- **Then**: `ALLListen_mode()` 不执行任何界面消息获取操作
- **Verification**: `programmatic`

### AC-2: Chatlog 模式下 get_next_new_message() 跳过执行
- **Given**: `chatlog_listen_switch=True`
- **When**: `ALLListen_mode()` 内部调用 `get_next_new_message()`
- **Then**: `get_next_new_message()` 不调用 `wx.GetNextNewMessage()`
- **Verification**: `programmatic`

### AC-3: Chatlog 模式下 new_msg_get() 跳过执行
- **Given**: `chatlog_listen_switch=True`
- **When**: 调用 `new_msg_get()`
- **Then**: `new_msg_get()` 不调用 `wx.GetAllMessage()`
- **Verification**: `programmatic`

### AC-4: 发送消息等界面操作正常使用 wxauto
- **Given**: `chatlog_listen_switch=True`
- **When**: 需要发送消息或获取子窗口
- **Then**: 正常调用 wxauto 的界面操作方法
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否还有其他通过界面获取消息的代码路径？
- [ ] `add_chat_to_listen()` 方法是否需要修改？