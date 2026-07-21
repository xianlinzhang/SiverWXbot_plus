# Chatlog 监听模式联系人匹配增强 - Product Requirement Document

## Overview
- **Summary**: 增强 Chatlog 监听模式下的联系人匹配能力，支持 remark（备注名）、userName（wxid）、alias（微信号）、nickName（昵称）四种方式的匹配
- **Purpose**: 当前实现中，`listen_list` 的匹配仅基于 `chat_name`，当用户使用备注名或微信号添加联系人时会匹配失败
- **Target Users**: 使用 Chatlog 监听模式的 SiverWXbot_plus 用户

## Goals
- [ ] 扩展 `refresh_chatlog_contacts()` 方法，存储 remark 和 alias 的映射
- [ ] 创建辅助方法 `_is_contact_in_listen_list()` 支持多种匹配方式
- [ ] 修改 `chatlog_listen_loop()` 中的 `is_monitored` 判断逻辑

## Non-Goals (Out of Scope)
- [ ] 不修改 wxautox4 库的核心代码
- [ ] 不改变原有 UI 监听模式的匹配逻辑

## Background & Context
- 当前 `chatlog_contact_map` 只存储 `{wxid: nickname, nickname: wxid}` 的双向映射
- 用户在 Web 面板添加监听用户时，可以输入备注名、微信号或昵称
- Chatlog API 返回的联系人信息包含 userName、nickName、alias、remark 字段
- 需要扩展映射以支持所有可能的匹配方式

## Functional Requirements
- **FR-1**: `refresh_chatlog_contacts()` 方法应存储 userName、nickName、alias、remark 的双向映射
- **FR-2**: 创建 `_is_contact_in_listen_list()` 方法，支持通过任一标识匹配
- **FR-3**: `chatlog_listen_loop()` 中的 `is_monitored` 判断应使用增强的匹配方法

## Non-Functional Requirements
- **NFR-1**: 修改应最小化，不影响现有功能
- **NFR-2**: 确保向后兼容性

## Constraints
- **Technical**: 基于 Chatlog API 返回的联系人字段
- **Dependencies**: 依赖 Chatlog 的 `search_contact()` API

## Assumptions
- [ ] Chatlog API 返回的联系人包含 userName、nickName、alias、remark 字段
- [ ] remark 和 alias 可能为空字符串

## Acceptance Criteria

### AC-1: 联系人映射包含所有字段
- **Given**: 调用 `refresh_chatlog_contacts()`
- **When**: Chatlog API 返回联系人列表
- **Then**: `chatlog_contact_map` 包含 userName、nickName、alias、remark 的双向映射
- **Verification**: `programmatic`

### AC-2: 支持多种方式匹配
- **Given**: `listen_list` 中包含备注名、微信号或昵称
- **When**: `_is_contact_in_listen_list()` 判断联系人是否在列表中
- **Then**: 正确匹配返回 True
- **Verification**: `programmatic`

### AC-3: is_monitored 判断使用增强匹配
- **Given**: `chatlog_listen_switch=True`
- **When**: `chatlog_listen_loop()` 处理会话
- **Then**: `is_monitored` 判断使用增强的匹配方法
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要处理重复映射的冲突？（例如两个联系人有相同的昵称）