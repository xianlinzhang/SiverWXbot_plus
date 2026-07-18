# wxautox4 拟人化操作 - 产品需求文档

## Overview
- **Summary**: 为 wxautox4 微信自动化工具添加拟人化操作层，使模拟操作更加接近真实人类行为，降低被微信客户端监控检测的风险。
- **Purpose**: 解决当前自动化操作过于机械、规律性强、容易被识别的问题，通过引入随机性和自然行为模式，使操作特征与真人用户更接近。
- **Target Users**: 使用 wxautox4 进行微信自动化操作的开发者和运维人员。

## Goals
- 实现自然的鼠标移动轨迹（贝塞尔曲线），替代瞬间跳转
- 实现点击位置随机化，不再总是点击控件中心
- 实现逐字输入模式，支持随机按键间隔
- 实现可变时间延迟，替代固定的 time.sleep()
- 添加随机噪声行为，模拟用户空闲时的微小动作

## Non-Goals (Out of Scope)
- 修改底层 uiautomation 库的核心实现
- 实现浏览器级别的指纹伪装
- 实现硬件级别的设备伪装
- 绕过微信的协议级反作弊检测
- 实现 AI 级别的语义理解和回复生成

## Background & Context
当前 wxautox4 基于 Windows UIAutomation 技术模拟用户操作，存在以下可检测特征：
1. 鼠标点击使用 `SetCursorPos` 瞬间移动，无移动轨迹
2. 点击位置始终精确居中（ratioX=0.5, ratioY=0.5）
3. 文本输入完全依赖剪贴板粘贴（Ctrl+V）
4. 所有时间延迟使用固定值（0.1s、0.5s、1s）
5. 无任何随机行为或空闲状态模拟

微信客户端会通过多种方式检测异常操作：
- 鼠标移动轨迹分析
- 按键频率和间隔分析
- 操作模式规律性检测
- 剪贴板使用模式分析

## Functional Requirements
- **FR-1**: 创建拟人化工具模块 `human.py`，提供自然鼠标移动和点击功能
- **FR-2**: 实现可变时间延迟函数，支持范围参数和正态分布随机
- **FR-3**: 实现逐字输入模式，支持自定义按键间隔范围
- **FR-4**: 修改消息发送逻辑，支持"粘贴"和"输入"两种模式
- **FR-5**: 修改搜索和切换聊天逻辑，添加随机延迟和自然鼠标移动
- **FR-6**: 在监听循环中添加随机噪声行为

## Non-Functional Requirements
- **NFR-1**: 拟人化操作不应显著降低性能（额外延迟 < 200ms/操作）
- **NFR-2**: 所有随机行为应可配置，支持关闭或调整参数
- **NFR-3**: 保持向后兼容性，原有 API 接口不变
- **NFR-4**: 代码应易于维护，随机逻辑集中在单一模块

## Constraints
- **Technical**: 基于 Windows UIAutomation，无法直接修改微信客户端行为
- **Dependencies**: 依赖现有 uiautomation 库和 win32api
- **Performance**: 随机延迟应合理，避免过度等待

## Assumptions
- 用户已安装 Python 3.8+ 和必要的依赖库（pywin32, Pillow 等）
- 用户了解并接受拟人化操作会增加少量延迟
- 微信客户端主要通过操作模式而非协议检测自动化

## Acceptance Criteria

### AC-1: 自然鼠标移动
- **Given**: 调用 `human_move_to(x, y)` 函数
- **When**: 鼠标从当前位置移动到目标位置
- **Then**: 鼠标沿贝塞尔曲线移动，轨迹平滑自然，移动时间在 200-800ms 随机
- **Verification**: `human-judgment`（观察鼠标移动轨迹）

### AC-2: 随机点击位置
- **Given**: 调用 `human_click(control)` 函数
- **When**: 点击指定控件
- **Then**: 点击位置在控件边界内随机偏移（±3-15px），非固定中心
- **Verification**: `programmatic`（验证点击坐标在控件范围内且非固定中心）

### AC-3: 逐字输入模式
- **Given**: 调用 `human_type_text(text)` 函数
- **When**: 输入文本内容
- **Then**: 每个字符间隔 50-200ms 随机延迟，模拟真实打字速度
- **Verification**: `programmatic`（验证按键间隔在指定范围内）

### AC-4: 可变时间延迟
- **Given**: 调用 `human_sleep(min, max)` 函数
- **When**: 程序等待指定时间
- **Then**: 实际等待时间在 [min, max] 范围内服从正态分布
- **Verification**: `programmatic`（验证等待时间在指定范围内）

### AC-5: 消息发送支持两种模式
- **Given**: 调用 `SendMsg()` 方法
- **When**: 发送短消息（<50字符）
- **Then**: 默认使用逐字输入模式；发送长消息时使用粘贴模式，并添加随机延迟
- **Verification**: `programmatic`（验证短消息使用键盘输入，长消息使用剪贴板）

### AC-6: 搜索操作添加随机延迟
- **Given**: 调用 `search()` 或 `switch_chat()` 方法
- **When**: 输入搜索关键词
- **Then**: 每个字符之间有 30-100ms 随机延迟，点击结果前有 200-500ms 随机延迟
- **Verification**: `programmatic`（验证操作间隔在指定范围内）

### AC-7: 监听循环噪声行为
- **Given**: 监听器正在运行
- **When**: 每轮监听循环执行
- **Then**: 有 5-15% 概率执行随机噪声行为（微小鼠标移动、滚动等）
- **Verification**: `programmatic`（验证噪声行为按概率执行）

## Open Questions
- [ ] 是否需要为不同操作类型设置不同的随机参数范围？
- [ ] 是否需要添加配置开关，允许用户在性能和隐蔽性之间权衡？
- [ ] 是否需要记录操作特征用于调试和优化？
