# 朋友圈拟人化操作 - 产品需求文档

## Overview
- **Summary**: 为 `moment.py` 模块添加拟人化操作支持，使朋友圈相关操作（点赞、评论、发布）更接近真实人类行为模式。
- **Purpose**: 降低自动化操作被检测的风险，提升操作的自然度和安全性。
- **Target Users**: 使用朋友圈自动化功能的机器人用户。

## Goals
- 朋友圈点赞操作支持拟人化（贝塞尔曲线鼠标移动+随机点击位置+随机延迟）
- 朋友圈评论操作支持拟人化（短消息逐字输入，长消息粘贴）
- 朋友圈发布操作支持拟人化（随机延迟、拟人化点击、逐字输入）
- 所有拟人化操作可通过 `ENABLE_HUMANIZATION` 配置项关闭

## Non-Goals (Out of Scope)
- 不修改朋友圈数据解析逻辑
- 不新增朋友圈接口功能
- 不修改其他模块的拟人化实现

## Background & Context
- 项目已在 `wxautox4/utils/human.py` 中实现了完整的拟人化操作工具函数
- `wxautox4/param.py` 中定义了 `ENABLE_HUMANIZATION` 配置项及相关参数
- 其他模块（如 `wx.py`、`sessionbox.py`）已实现拟人化操作，可作为参考

## Functional Requirements
- **FR-1**: 朋友圈点赞操作支持拟人化，包括贝塞尔曲线鼠标移动、随机点击位置和随机延迟
- **FR-2**: 朋友圈评论操作支持拟人化输入，短消息（默认50字符以下）使用逐字输入，长消息使用粘贴
- **FR-3**: 朋友圈发布操作支持拟人化，包括发布按钮点击、图片添加、文本输入和发表按钮点击
- **FR-4**: 拟人化操作可通过 `WxParam.ENABLE_HUMANIZATION` 配置项全局关闭

## Non-Functional Requirements
- **NFR-1**: 拟人化操作需使用正态分布随机延迟，符合人类行为模式
- **NFR-2**: 鼠标移动轨迹需使用贝塞尔曲线模拟人类自然移动
- **NFR-3**: 点击操作需在控件范围内随机位置执行

## Constraints
- **Technical**: 必须使用项目已有的 `human.py` 工具函数，禁止重复实现
- **Technical**: 必须遵循项目已有的拟人化操作模式和配置项
- **Dependencies**: 依赖 `wxautox4/utils/human.py` 和 `wxautox4/param.py`

## Assumptions
- `human.py` 中的工具函数已正确实现并可用
- `WxParam.ENABLE_HUMANIZATION` 配置项已正确定义
- 现有代码中的控件定位逻辑正确无误

## Acceptance Criteria

### AC-1: 拟人化点赞操作
- **Given**: `WxParam.ENABLE_HUMANIZATION=True`
- **When**: 调用 `Moment.Like()` 方法
- **Then**: 鼠标沿贝塞尔曲线移动到点赞按钮，在控件范围内随机位置点击，点击前有随机延迟
- **Verification**: `human-judgment`

### AC-2: 非拟人化点赞操作
- **Given**: `WxParam.ENABLE_HUMANIZATION=False`
- **When**: 调用 `Moment.Like()` 方法
- **Then**: 使用原始的 `Click()` 方法直接点击，无额外延迟
- **Verification**: `programmatic`

### AC-3: 拟人化评论操作（短消息）
- **Given**: `WxParam.ENABLE_HUMANIZATION=True`，评论内容少于50字符
- **When**: 调用 `Moment.Comment()` 方法
- **Then**: 评论内容逐字输入，每个字符间有随机间隔
- **Verification**: `human-judgment`

### AC-4: 拟人化评论操作（长消息）
- **Given**: `WxParam.ENABLE_HUMANIZATION=True`，评论内容多于50字符
- **When**: 调用 `Moment.Comment()` 方法
- **Then**: 评论内容使用粘贴方式输入，粘贴前后有随机延迟
- **Verification**: `human-judgment`

### AC-5: 拟人化发布操作
- **Given**: `WxParam.ENABLE_HUMANIZATION=True`
- **When**: 调用 `Moment.Publish()` 方法
- **Then**: 所有点击操作使用拟人化方式，延迟使用正态分布随机延迟，短消息逐字输入
- **Verification**: `human-judgment`

### AC-6: 配置项控制
- **Given**: `WxParam.ENABLE_HUMANIZATION` 可配置
- **When**: 将其设置为 `False`
- **Then**: 所有朋友圈操作使用原始方式，无拟人化效果
- **Verification**: `programmatic`

## Open Questions
- [ ] 暂无未解决问题