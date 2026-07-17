# wxautox4 缺失方法实现 - 产品需求文档

## Overview
- **Summary**: 实现 wxbot_core.py 中使用但尚未在 wxauto4 库中实现的 wxautox4 方法，包括消息下载、语音转文字、朋友圈操作、好友请求处理、在线状态检测等功能。
- **Purpose**: 确保 wxbot_core.py 中调用的所有 wxautox4 方法都有完整实现，使机器人能够正常运行所有功能。
- **Target Users**: SiverWXbot_plus 项目开发者和用户

## Goals
- 实现所有缺失的 WeChat 类方法（GetMyInfo、IsOnline、GetNewFriends、GetListenMessage、GetNextNewMessage）
- 实现所有缺失的消息对象方法（download、download_quote_image、to_text）
- 实现所有缺失的 Moment 类方法（Publish、Close）
- 实现所有缺失的 MomentItem 类方法（Like）
- 实现 Friend 对象的 accept 方法
- 添加缺失的 WxParam 属性（CHAT_WINDOW_SIZE）

## Non-Goals (Out of Scope)
- 不修改 wxbot_core.py 中的调用逻辑
- 不实现 wxautox4 中未被 wxbot_core.py 使用的额外方法
- 不优化现有已实现方法的性能
- 不添加新的功能特性

## Background & Context
根据之前的代码分析，wxbot_core.py 作为核心文件使用了大量 wxautox4 方法，但其中有 13 项方法/属性尚未在 wxauto4 目录中实现。这些缺失方法主要影响：
1. 新好友处理（自动通过好友请求）
2. 图片识别（下载图片）
3. 语音转文字
4. 朋友圈发布与点赞
5. 全局监听模式（获取新消息）
6. 记忆管理初始化（获取微信号）
7. 在线状态检测

## Functional Requirements
- **FR-1**: WeChat 类实现 GetMyInfo() 方法，返回当前登录用户的信息（昵称、微信号等）
- **FR-2**: WeChat 类实现 IsOnline() 方法，返回微信是否在线状态
- **FR-3**: WeChat 类实现 GetNewFriends() 方法，返回新好友请求列表
- **FR-4**: WeChat 类实现 GetListenMessage() 方法，返回所有监听消息
- **FR-5**: WeChat 类实现 GetNextNewMessage() 方法，返回下一条新消息
- **FR-6**: 消息对象实现 download() 方法，下载图片到本地
- **FR-7**: 消息对象实现 download_quote_image() 方法，下载引用消息中的图片
- **FR-8**: 消息对象实现 to_text() 方法，将语音消息转为文字
- **FR-9**: Moment 类实现 Publish() 方法，发布朋友圈
- **FR-10**: Moment 类实现 Close() 方法，关闭朋友圈页面
- **FR-11**: MomentItem 类实现 Like() 方法，给朋友圈点赞
- **FR-12**: Friend 对象实现 accept() 方法，通过好友请求并设置备注/标签
- **FR-13**: WxParam 添加 CHAT_WINDOW_SIZE 属性

## Non-Functional Requirements
- **NFR-1**: 所有方法必须保持与现有 wxauto4 代码风格一致
- **NFR-2**: 所有方法必须有适当的错误处理
- **NFR-3**: 方法签名必须与 wxbot_core.py 中的调用方式匹配
- **NFR-4**: 所有方法必须添加函数级注释

## Constraints
- **Technical**: 基于 Windows 平台，使用 uiautomation 库进行界面操作
- **Dependencies**: 依赖 wxauto4 现有代码结构和依赖项

## Assumptions
- wxauto4 库的目录结构保持不变
- 微信客户端界面结构与现有代码兼容
- 所有方法的实现方式与现有方法保持一致

## Acceptance Criteria

### AC-1: GetMyInfo() 方法实现
- **Given**: 微信已登录且正常运行
- **When**: 调用 wx.GetMyInfo()
- **Then**: 返回包含昵称和微信号的字典
- **Verification**: `programmatic`
- **Notes**: 参考 wx.nickname 的实现方式

### AC-2: IsOnline() 方法实现
- **Given**: 微信客户端已启动
- **When**: 调用 wx.IsOnline()
- **Then**: 返回布尔值表示微信是否在线
- **Verification**: `programmatic`
- **Notes**: 通过检测微信窗口状态判断

### AC-3: GetNewFriends() 方法实现
- **Given**: 微信已登录
- **When**: 调用 wx.GetNewFriends()
- **Then**: 返回新好友请求列表
- **Verification**: `programmatic`

### AC-4: GetListenMessage() 方法实现
- **Given**: 已设置监听并收到消息
- **When**: 调用 wx.GetListenMessage()
- **Then**: 返回所有监听消息列表
- **Verification**: `programmatic`

### AC-5: GetNextNewMessage() 方法实现
- **Given**: 全局监听模式已启用
- **When**: 调用 wx.GetNextNewMessage()
- **Then**: 返回下一条新消息对象
- **Verification**: `programmatic`

### AC-6: 消息 download() 方法实现
- **Given**: 收到图片消息
- **When**: 调用 msg.download()
- **Then**: 返回下载文件的本地路径
- **Verification**: `programmatic`

### AC-7: 消息 download_quote_image() 方法实现
- **Given**: 收到引用消息且包含图片
- **When**: 调用 msg.download_quote_image()
- **Then**: 返回引用图片的本地路径
- **Verification**: `programmatic`

### AC-8: 消息 to_text() 方法实现
- **Given**: 收到语音消息
- **When**: 调用 msg.to_text()
- **Then**: 返回语音转文字的结果
- **Verification**: `programmatic`

### AC-9: Moment.Publish() 方法实现
- **Given**: 朋友圈页面已打开
- **When**: 调用 pyq.Publish(text, images, privacy_config)
- **Then**: 成功发布朋友圈
- **Verification**: `programmatic`

### AC-10: Moment.Close() 方法实现
- **Given**: 朋友圈页面已打开
- **When**: 调用 pyq.Close()
- **Then**: 朋友圈页面关闭，返回聊天界面
- **Verification**: `programmatic`

### AC-11: MomentItem.Like() 方法实现
- **Given**: 获取到朋友圈动态
- **When**: 调用 moment.Like()
- **Then**: 成功点赞该朋友圈动态
- **Verification**: `programmatic`

### AC-12: Friend.accept() 方法实现
- **Given**: 有新的好友请求
- **When**: 调用 friend.accept(remark, tags)
- **Then**: 通过好友请求并设置备注和标签
- **Verification**: `programmatic`

### AC-13: WxParam.CHAT_WINDOW_SIZE 属性
- **Given**: 导入 WxParam 模块
- **When**: 访问 WxParam.CHAT_WINDOW_SIZE
- **Then**: 返回聊天窗口大小配置元组
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要处理微信版本差异导致的界面元素变化？
- [ ] 语音转文字功能是否需要依赖外部 API？
- [ ] 朋友圈发布的图片选择逻辑如何实现？