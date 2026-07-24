# wxbot_core.py 文件拆分 - Product Requirement Document

## Overview
- **Summary**: 将 `wxbot_core.py`（4915+行）拆分为多个职责单一的模块文件，提高代码可维护性和可读性
- **Purpose**: 解决单文件过大导致的开发效率低下、代码复用困难、测试复杂度高等问题
- **Target Users**: 开发维护人员

## Goals
- 将单个巨型文件拆分为多个小型、职责单一的模块
- 保持所有功能不变，确保拆分后系统行为与原系统完全一致
- 建立清晰的模块间依赖关系
- 每个文件不超过 500 行代码

## Non-Goals (Out of Scope)
- 不修改现有业务逻辑和功能实现
- 不进行代码重构或性能优化
- 不添加新功能或删除现有功能
- 不改变外部 API 接口

## Background & Context
- 当前 `wxbot_core.py` 包含 9 个类和 100+ 个函数，代码量超过 4900 行
- 模块间职责不清，维护困难
- 代码复用性差，难以进行单元测试

## Functional Requirements
- **FR-1**: 将工具函数和常量提取到独立模块
- **FR-2**: 将配置管理类 `WXBotConfig` 提取到独立模块
- **FR-3**: 将记忆管理类 `MemoryManager` 和 `ReplyCountStore` 提取到独立模块
- **FR-4**: 将 AI API 封装类（`OpenAIAPI`, `DifyAPI`, `CozeAPI`, `DusAPI`）提取到独立模块
- **FR-5**: 将主机器人类 `WXBot` 按功能域拆分到多个模块
- **FR-6**: 保持模块间导入关系正确，确保系统正常运行

## Non-Functional Requirements
- **NFR-1**: 每个拆分后的文件不超过 500 行
- **NFR-2**: 模块间依赖关系清晰，避免循环依赖
- **NFR-3**: 代码风格与原文件保持一致
- **NFR-4**: 拆分后不引入新的语法错误或运行时错误

## Constraints
- **Technical**: Python 3.x，必须保持与 wxautox4 的兼容性
- **Dependencies**: 依赖 `wxautox4`, `requests`, `openai`, `cozepy` 等第三方库
- **File Structure**: 保持现有项目结构，新增模块放置在 `core/` 目录

## Assumptions
- 拆分后的模块仅通过导入关系交互，不直接修改其他模块的内部状态
- 所有类和函数的公共接口保持不变

## Acceptance Criteria

### AC-1: 工具函数模块拆分
- **Given**: `wxbot_core.py` 包含工具函数和常量定义
- **When**: 将工具函数和常量提取到 `core/utils.py`
- **Then**: `core/utils.py` 包含所有工具函数和常量，`wxbot_core.py` 通过导入使用它们
- **Verification**: `programmatic`

### AC-2: 配置管理模块拆分
- **Given**: `wxbot_core.py` 包含 `WXBotConfig` 类
- **When**: 将 `WXBotConfig` 提取到 `core/config_manager.py`
- **Then**: `core/config_manager.py` 包含完整的配置管理功能，其他模块通过导入使用
- **Verification**: `programmatic`

### AC-3: 记忆管理模块拆分
- **Given**: `wxbot_core.py` 包含 `MemoryManager` 和 `ReplyCountStore` 类
- **When**: 将这两个类提取到 `core/memory_manager.py`
- **Then**: `core/memory_manager.py` 包含完整的记忆和计数管理功能
- **Verification**: `programmatic`

### AC-4: AI API 模块拆分
- **Given**: `wxbot_core.py` 包含 4 个 AI API 封装类
- **When**: 将这些类提取到 `core/ai_api.py`
- **Then**: `core/ai_api.py` 包含所有 AI API 封装类，提供统一的接口
- **Verification**: `programmatic`

### AC-5: WXBot 主类拆分
- **Given**: `wxbot_core.py` 包含 `WXBot` 主类（约 3200 行）
- **When**: 将 `WXBot` 按功能域拆分为多个模块
- **Then**: 每个子模块职责单一，不超过 500 行，通过组合方式重构 `WXBot`
- **Verification**: `programmatic`

### AC-6: 系统完整性验证
- **Given**: 所有模块已拆分完成
- **When**: 启动机器人并运行测试用例
- **Then**: 机器人正常运行，所有功能与拆分前一致
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要创建 `__init__.py` 作为包的入口？
- [ ] `WXBot` 类的拆分方式：使用 Mixin 模式还是组合模式？
