# Chatlog 监听模式下停止 wxautox4 UI 监听 - Implementation Plan

## [x] Task 1: 修改 init_wx_listeners() 方法
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `init_wx_listeners()` 方法中添加条件判断，当 `chatlog_listen_switch=True` 时跳过所有 `wx.AddListenChat()` 调用
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: 当 `chatlog_listen_switch=True` 时，`init_wx_listeners()` 不调用 `wx.AddListenChat()`
  - `human-judgement` TR-1.2: 代码逻辑清晰，条件判断位置合理

## [x] Task 2: 在 Chatlog 模式下停止 UI 监听线程
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 在 `_init_chatlog_client()` 方法中，当成功启用 Chatlog 监听模式时，调用 `wx.StopListening()` 停止 wxautox4 的监听线程
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: 当 `chatlog_listen_switch=True` 且 Chatlog 服务可用时，调用 `wx.StopListening()`
  - `human-judgement` TR-2.2: 调用时机合理，不会影响其他功能

## [ ] Task 3: 验证正常模式下的恢复行为
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 确保当 `chatlog_listen_switch=False` 时，所有原有功能正常工作
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: 当 `chatlog_listen_switch=False` 时，`init_wx_listeners()` 正常注册所有监听器
  - `human-judgement` TR-3.2: 原有 UI 监听功能不受影响