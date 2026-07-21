# Chatlog 消息处理优化 - Implementation Plan

## [x] Task 1: 新建 chatlog_process_message 方法
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `wxbot_core.py` 中新建 `chatlog_process_message` 方法
  - 方法参数：`chat_name`（会话名称）、`msg_dict`（消息字典）
  - 实现消息转换（调用 `_convert_chatlog_msg`）
  - 实现消息处理逻辑：群聊处理、管理员命令、私聊 AI 回复
  - 使用 `self.wx.SendMsg(who=chat_name, msg=msg)` 发送消息
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-1.1: 方法被正确定义，语法检查通过
  - `programmatic` TR-1.2: 方法内部不调用 `_get_verified_subwindow` 或 `add_chat_to_listen`
  - `human-judgement` TR-1.3: 代码逻辑与 `process_message` 保持一致，结构清晰
- **Notes**: 群聊的 `@` 回复功能需要使用 `self.wx.SendMsg(who=chat_name, msg=msg, at=sender)` 格式

## [x] Task 2: 修改 chatlog_listen_loop 调用新方法
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 修改 `chatlog_listen_loop` 方法中的消息处理部分（第3241-3261行）
  - 移除获取子窗口对象的逻辑（`_get_verified_subwindow`、`add_chat_to_listen`）
  - 移除调用 `process_message` 的逻辑
  - 添加调用 `chatlog_process_message` 的逻辑
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: `chatlog_listen_loop` 方法中不再调用 `_get_verified_subwindow` 或 `add_chat_to_listen`
  - `programmatic` TR-2.2: `chatlog_listen_loop` 方法中调用 `chatlog_process_message`
  - `human-judgement` TR-2.3: 修改后的代码结构清晰，逻辑正确
- **Notes**: 需要保留消息转换和异常处理逻辑

## [x] Task 3: 验证代码语法正确性
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 运行语法检查，确保代码没有语法错误
  - 检查导入语句是否完整
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-3.1: Python 语法检查通过
  - `programmatic` TR-3.2: VS Code 诊断无错误
- **Notes**: 使用 `GetDiagnostics` 工具检查
