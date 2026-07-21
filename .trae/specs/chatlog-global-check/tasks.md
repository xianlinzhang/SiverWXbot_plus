# Chatlog 监听模式全局检查 - Implementation Plan

## [x] Task 1: 修改 ALLListen_mode() 方法
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `ALLListen_mode()` 方法开头添加条件判断，当 `chatlog_listen_switch=True` 时直接返回 `last_time`
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-1.1: 当 `chatlog_listen_switch=True` 时，`ALLListen_mode()` 直接返回，不调用任何界面消息获取方法
  - `human-judgement` TR-1.2: 代码逻辑清晰，条件判断位置合理

## [x] Task 2: 修改 new_msg_get() 方法
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `new_msg_get()` 方法开头添加条件判断，当 `chatlog_listen_switch=True` 时直接返回空列表
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-2.1: 当 `chatlog_listen_switch=True` 时，`new_msg_get()` 直接返回空列表，不调用 `wx.GetAllMessage()`
  - `human-judgement` TR-2.2: 代码逻辑清晰，条件判断位置合理

## [x] Task 3: 修改 add_chat_to_listen() 方法
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 在 `add_chat_to_listen()` 方法中，当 `chatlog_listen_switch=True` 时，跳过 `wx.AddListenChat()` 调用，只获取子窗口
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-3.1: 当 `chatlog_listen_switch=True` 时，`add_chat_to_listen()` 不调用 `wx.AddListenChat()`
  - `human-judgement` TR-3.2: 代码逻辑清晰，不影响消息发送功能

## [x] Task 4: 验证所有修改
- **Priority**: medium
- **Depends On**: Task 1, Task 2, Task 3
- **Description**: 
  - 运行 Python 语法检查
  - 验证端到端功能
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: Python 语法检查通过
  - `programmatic` TR-4.2: 端到端测试通过