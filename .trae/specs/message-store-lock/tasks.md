# SiverWXbot 消息存储与标注层优化 - 实现计划

## [ ] Task 1: 创建消息存储模块 core/message_store.py
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 实现 `MessageRecord` 类（数据模型）
  - 实现 `MessageStore` 类（存储管理）
  - 实现文件持久化逻辑（JSON 文件存储）
  - 实现线程安全锁机制
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: 消息存储文件正确生成，包含完整消息数据
  - `programmatic` TR-1.2: 消息查询功能返回正确的消息列表
  - `programmatic` TR-1.3: 消息状态更新功能正确工作
  - `human-judgement` TR-1.4: 代码结构清晰，符合项目风格，函数有详细注释
- **Notes**: 参考 memory_manager.py 的存储模式

## [ ] Task 2: 创建微信界面操作锁模块 core/wx_lock.py
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 实现 `WXLock` 类（锁管理）
  - 实现 `acquire()`、`release()`、`try_acquire()` 方法
  - 实现 `force_release()` 强制释放方法
  - 实现锁超时检测机制
  - 实现锁状态查询方法
- **Acceptance Criteria Addressed**: AC-6, AC-7, AC-8
- **Test Requirements**:
  - `programmatic` TR-2.1: 锁获取和释放功能正确工作
  - `programmatic` TR-2.2: 锁被占用时，其他任务等待直到获取锁
  - `programmatic` TR-2.3: 锁超时自动释放功能正确工作
  - `programmatic` TR-2.4: 强制释放功能正确工作
  - `human-judgement` TR-2.5: 代码结构清晰，函数有详细注释
- **Notes**: 使用 threading.Lock 作为基础锁，实现超时保护

## [ ] Task 3: 修改配置管理 core/config_manager.py
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `__init__` 中添加新配置属性（含微信锁配置）
  - 在 `create_new_config_file()` 中添加默认值
  - 在 `update_global_config()` 中添加配置同步逻辑
- **Acceptance Criteria Addressed**: AC-3, AC-6, AC-8
- **Test Requirements**:
  - `programmatic` TR-3.1: 新配置项正确加载到内存
  - `programmatic` TR-3.2: 配置文件中包含新配置项的默认值
  - `human-judgement` TR-3.3: 配置同步逻辑正确，代码风格一致
- **Notes**: 添加配置项：chat_reply_confirm_switch, chat_reply_confirm_wait_timeout, message_store_max_count, wx_lock_enabled, wx_lock_timeout

## [ ] Task 4: 集成消息存储和微信锁到消息处理 core/message_handler.py
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3
- **Description**: 
  - 修改 `wx_send_ai()` 添加消息存储逻辑和微信锁
  - 修改 `_chatlog_send_ai()` 添加消息存储逻辑和微信锁
  - 添加回复确认检查逻辑
- **Acceptance Criteria Addressed**: AC-1, AC-3, AC-4, AC-5, AC-6
- **Test Requirements**:
  - `programmatic` TR-4.1: 消息处理前正确保存到存储层
  - `programmatic` TR-4.2: 回复发送后正确绑定到消息记录
  - `programmatic` TR-4.3: 开启回复确认时，消息进入待确认队列
  - `programmatic` TR-4.4: 微信界面操作前正确获取和释放锁
  - `human-judgement` TR-4.5: 修改逻辑清晰，不影响现有功能
- **Notes**: 需要在发送消息前获取锁，发送完成后释放锁

## [ ] Task 5: 集成消息存储和微信锁到 Chatlog 监听 core/chatlog_manager.py
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3
- **Description**: 
  - 在 `chatlog_process_message()` 中集成消息存储和微信锁
  - 添加私聊回复确认支持
- **Acceptance Criteria Addressed**: AC-1, AC-3, AC-4, AC-5, AC-6
- **Test Requirements**:
  - `programmatic` TR-5.1: Chatlog 消息处理前正确保存到存储层
  - `programmatic` TR-5.2: Chatlog 模式下回复确认机制正确工作
  - `programmatic` TR-5.3: Chatlog 模式下微信锁机制正确工作
  - `human-judgement` TR-5.4: 修改逻辑清晰，不影响现有功能
- **Notes**: 注意 Chatlog 模式下不直接操作微信界面，锁主要用于发送消息时

## [ ] Task 6: 集成微信锁到监听管理器 core/listen_manager.py
- **Priority**: medium
- **Depends On**: Task 2, Task 3
- **Description**: 
  - 在 `listen_mode()` 中添加微信锁获取/释放
  - 在 `ALLListen_mode()` 中添加微信锁获取/释放
  - 在 `next_message_handle()` 中添加微信锁获取/释放
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-6.1: 监听模式下微信锁正确获取和释放
  - `programmatic` TR-6.2: 全局监听模式下微信锁正确获取和释放
  - `human-judgement` TR-6.3: 修改逻辑清晰，不影响现有功能
- **Notes**: 获取消息时需要操作微信界面，需要加锁

## [ ] Task 7: 集成微信锁到微信工具模块 core/wx_utils.py
- **Priority**: medium
- **Depends On**: Task 2, Task 3
- **Description**: 
  - 在 `send_group_welcome_msg()` 中添加微信锁
  - 在 `Pass_New_Friends()` 中添加微信锁
  - 在 `send_scheduled_msg()` 中添加微信锁
  - 在 `send_scheduled_moments()` 中添加微信锁
  - 在 `_do_moments_like()` 中添加微信锁
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-7.1: 群欢迎语发送前正确获取锁
  - `programmatic` TR-7.2: 新好友处理前正确获取锁
  - `programmatic` TR-7.3: 定时消息发送前正确获取锁
  - `programmatic` TR-7.4: 朋友圈操作前正确获取锁
  - `human-judgement` TR-7.5: 修改逻辑清晰，不影响现有功能
- **Notes**: 所有微信界面操作都需要加锁

## [ ] Task 8: 添加管理命令 core/command_handler.py
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3
- **Description**: 
  - 添加 `/确认回复` 命令（支持指定消息 ID）
  - 添加 `/拒绝回复` 命令（支持指定消息 ID）
  - 添加 `/查看待确认` 命令（列出待确认消息）
  - 添加 `/查看未读消息` 命令
  - 添加 `/占用微信锁` 命令（手动占用）
  - 添加 `/释放微信锁` 命令（手动释放）
  - 添加 `/查看微信锁状态` 命令（查看锁状态）
- **Acceptance Criteria Addressed**: AC-2, AC-4, AC-7
- **Test Requirements**:
  - `programmatic` TR-8.1: `/确认回复` 命令正确触发回复发送
  - `programmatic` TR-8.2: `/拒绝回复` 命令正确标记消息为拒绝
  - `programmatic` TR-8.3: `/查看待确认` 命令正确显示待确认列表
  - `programmatic` TR-8.4: `/查看未读消息` 命令正确显示未读列表
  - `programmatic` TR-8.5: `/占用微信锁` 和 `/释放微信锁` 命令正确工作
  - `programmatic` TR-8.6: `/查看微信锁状态` 命令正确显示锁状态
  - `human-judgement` TR-8.7: 命令逻辑清晰，符合现有命令风格
- **Notes**: 命令需要支持消息 ID 参数

## [ ] Task 9: 初始化消息存储和微信锁 wxbot_core.py
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3
- **Description**: 
  - 在 `WXBot.__init__` 中初始化 `MessageStore`
  - 在 `WXBot.__init__` 中初始化 `WXLock`
  - 在 `get_status()` 中添加待确认消息数量统计和锁状态
- **Acceptance Criteria Addressed**: AC-1, AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-9.1: `MessageStore` 实例正确初始化
  - `programmatic` TR-9.2: `WXLock` 实例正确初始化
  - `programmatic` TR-9.3: `get_status()` 返回包含待确认数量和锁状态
  - `human-judgement` TR-9.4: 初始化逻辑清晰，符合现有代码风格
- **Notes**: 需要在初始化时创建必要的目录结构
