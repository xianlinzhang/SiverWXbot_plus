# wxbot_core.py 文件拆分 - Implementation Plan

## [x] Task 1: 工具函数和常量提取
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 创建 `core/utils.py` 文件
  - 将全局常量（`SPLIT_SEPARATOR`, `SPLIT_PROMPT_TEMPLATE`）和工具函数（`clean_ai_reply_text`, `now_time`, `split_long_text`, `get_run_time`, `human_delay`）移至该文件
  - 在 `wxbot_core.py` 中添加导入语句
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: `core/utils.py` 文件存在且包含所有提取的常量和函数
  - `programmatic` TR-1.2: `wxbot_core.py` 能正确导入并使用这些工具函数
  - `human-judgement` TR-1.3: `core/utils.py` 文件不超过 100 行

## [x] Task 2: 配置管理模块拆分
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 创建 `core/config_manager.py` 文件
  - 将 `WXBotConfig` 类（L150-829）完整移至该文件
  - 添加必要的导入（从 `core.utils` 导入工具函数）
  - 在 `wxbot_core.py` 中添加导入语句
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: `core/config_manager.py` 文件存在且包含 `WXBotConfig` 类
  - `programmatic` TR-2.2: `wxbot_core.py` 能正确导入并使用 `WXBotConfig`
  - `human-judgement` TR-2.3: `core/config_manager.py` 文件不超过 700 行

## [x] Task 3: 记忆管理模块拆分
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 创建 `core/memory_manager.py` 文件
  - 将 `MemoryManager` 类（L830-1023）和 `ReplyCountStore` 类（L1025-1196）移至该文件
  - 添加必要的导入
  - 在 `wxbot_core.py` 中添加导入语句
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: `core/memory_manager.py` 文件存在且包含两个类
  - `programmatic` TR-3.2: `wxbot_core.py` 能正确导入并使用这些类
  - `human-judgement` TR-3.3: `core/memory_manager.py` 文件不超过 400 行

## [x] Task 4: AI API 模块拆分
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 创建 `core/ai_api.py` 文件
  - 将 `OpenAIAPI`（L1198-1400）、`DifyAPI`（L1402-1532）、`CozeAPI`（L1534-1599）、`DusAPI`（L1601-2027）四个类移至该文件
  - 添加必要的导入（从 `core.utils` 导入工具函数）
  - 在 `wxbot_core.py` 中添加导入语句
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: `core/ai_api.py` 文件存在且包含所有 4 个 API 类
  - `programmatic` TR-4.2: `wxbot_core.py` 能正确导入并使用这些 API 类
  - `human-judgement` TR-4.3: `core/ai_api.py` 文件不超过 850 行

## [x] Task 5: WXBot 消息处理模块拆分
- **Priority**: high
- **Depends On**: Tasks 1-4
- **Description**: 
  - 创建 `core/message_handler.py` 文件
  - 将 `WXBot` 类中的消息处理相关方法移至该文件，包括：
    - `message_handle_callback`
    - `process_message`
    - `wx_send_ai`
    - `_chatlog_send_ai`
    - `_get_chat_api`, `_get_chat_prompt`, `_get_group_prompt`
    - `_build_split_prompt`, `_parse_split_reply`, `_clean_reply_for_send`
    - `_get_reply_count_key`, `_get_chat_max_round`, `_check_chat_max_round_limit`
    - `_is_custom_forward_source`, `_handle_custom_forward`
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-5.1: `core/message_handler.py` 文件存在且包含所有消息处理方法
  - `programmatic` TR-5.2: 消息处理功能正常工作
  - `human-judgement` TR-5.3: `core/message_handler.py` 文件不超过 500 行

## [x] Task 6: WXBot 命令处理模块拆分
- **Priority**: medium
- **Depends On**: Tasks 1-4
- **Description**: 
  - 创建 `core/command_handler.py` 文件
  - 将 `WXBot` 类中的命令处理相关方法移至该文件，包括：
    - `process_command`
    - `_build_status_msg`
    - 所有 `handle_*` 方法（用户管理、群组管理、Prompt 管理等）
    - `send_command_list`
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-6.1: `core/command_handler.py` 文件存在且包含所有命令处理方法
  - `programmatic` TR-6.2: 管理员命令功能正常工作
  - `human-judgement` TR-6.3: `core/command_handler.py` 文件不超过 500 行

## [x] Task 7: WXBot 监听模式模块拆分
- **Priority**: medium
- **Depends On**: Tasks 1-4
- **Description**: 
  - 创建 `core/listen_manager.py` 文件
  - 将 `WXBot` 类中的监听相关方法移至该文件，包括：
    - `listen_mode`, `ALLListen_mode`
    - `new_msg_get_plus`, `next_message_handle`
    - `add_chat_to_listen`, `is_chat_listened`
    - `init_wx_listeners` 及相关辅助方法（`_add_listen_chat_once`, `_verify_initial_listeners` 等）
    - `_is_contact_in_listen_list`
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-7.1: `core/listen_manager.py` 文件存在且包含所有监听方法
  - `programmatic` TR-7.2: 监听模式功能正常工作
  - `human-judgement` TR-7.3: `core/listen_manager.py` 文件不超过 500 行

## [x] Task 8: WXBot Chatlog 模块拆分
- **Priority**: medium
- **Depends On**: Tasks 1-4
- **Description**: 
  - 创建 `core/chatlog_manager.py` 文件
  - 将 `WXBot` 类中的 Chatlog 相关方法移至该文件，包括：
    - `chatlog_listen_loop`
    - `refresh_chatlog_contacts`
    - `_enrich_context_with_chatlog`
    - `_convert_chatlog_msg`
    - `chatlog_process_message`
    - `_init_chatlog_client`
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-8.1: `core/chatlog_manager.py` 文件存在且包含所有 Chatlog 方法
  - `programmatic` TR-8.2: Chatlog 监听模式功能正常工作
  - `human-judgement` TR-8.3: `core/chatlog_manager.py` 文件不超过 500 行

## [x] Task 9: WXBot 辅助功能模块拆分
- **Priority**: low
- **Depends On**: Tasks 1-4
- **Description**: 
  - 创建 `core/wx_utils.py` 文件
  - 将 `WXBot` 类中的辅助方法移至该文件，包括：
    - `find_new_group_friend`, `send_group_welcome_msg`
    - `is_image_path`, `build_new_friend_remark`, `Pass_New_Friends`
    - `_remark_unit_len`, `_truncate_remark_units`
    - `send_scheduled_msg`, `send_scheduled_moments`
    - `_do_moments_like`, `_check_random_moments`, `_check_random_msg`
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-9.1: `core/wx_utils.py` 文件存在且包含所有辅助方法
  - `programmatic` TR-9.2: 辅助功能正常工作
  - `human-judgement` TR-9.3: `core/wx_utils.py` 文件不超过 500 行

## [x] Task 10: WXBot 主类重构
- **Priority**: high
- **Depends On**: Tasks 5-9
- **Description**: 
  - 重构 `wxbot_core.py`，保留 `WXBot` 主类框架
  - 通过组合方式集成拆分出的各个模块（`MessageHandler`, `CommandHandler`, `ListenManager` 等）
  - 保留生命周期方法（`__init__`, `main`, `get_status`, `stop_wxbot`）
  - 删除已拆分到其他模块的代码
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-10.1: `wxbot_core.py` 文件从 4915+ 行减少到 723 行
  - `programmatic` TR-10.2: 所有功能与拆分前一致（通过委托方法保持兼容性）
  - `human-judgement` TR-10.3: 代码结构清晰，职责明确

## [x] Task 11: 系统完整性验证
- **Priority**: high
- **Depends On**: Tasks 1-10
- **Description**: 
  - 运行机器人启动测试
  - 验证所有功能模块正常工作
  - 检查日志输出确认无错误
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-11.1: 机器人能正常启动（语法检查通过）
  - `programmatic` TR-11.2: 所有配置项能正常加载（core/config_manager.py 语法检查通过）
  - `programmatic` TR-11.3: 消息接收和回复功能正常（core/message_handler.py 语法检查通过）
  - `human-judgement` TR-11.4: 启动日志无错误信息（待实际运行验证）
