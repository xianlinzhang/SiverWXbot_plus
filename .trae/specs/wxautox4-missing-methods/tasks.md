# wxautox4 缺失方法实现 - 任务分解计划

## [x] Task 1: 实现 WeChat 类缺失方法（GetMyInfo、IsOnline、GetNewFriends）
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 wxauto4/wx.py 中实现 GetMyInfo() 方法，返回当前登录用户信息
  - 实现 IsOnline() 方法，检测微信在线状态
  - 实现 GetNewFriends() 方法，获取新好友请求列表
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-1.1: 验证 GetMyInfo() 返回包含 nickname 和 wxid 的字典
  - `programmatic` TR-1.2: 验证 IsOnline() 返回布尔值
  - `programmatic` TR-1.3: 验证 GetNewFriends() 返回列表类型
- **Notes**: 参考现有 wx.py 中其他方法的实现模式

## [x] Task 2: 实现 WeChat 类监听消息方法（GetListenMessage、GetNextNewMessage）
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 在 wxauto4/wx.py 中实现 GetListenMessage() 方法
  - 实现 GetNextNewMessage() 方法，支持全局监听模式
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: 验证 GetListenMessage() 返回消息列表
  - `programmatic` TR-2.2: 验证 GetNextNewMessage() 返回单个消息对象或 None
- **Notes**: 需要检查现有监听机制的实现

## [x] Task 3: 实现消息对象下载方法（download、download_quote_image）
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 wxauto4/msgs/base.py 中实现 download() 方法，用于下载图片消息
  - 实现 download_quote_image() 方法，下载引用消息中的图片
- **Acceptance Criteria Addressed**: AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-3.1: 验证 download() 返回有效文件路径
  - `programmatic` TR-3.2: 验证 download_quote_image() 返回有效文件路径
- **Notes**: 需要参考现有消息对象的实现方式

## [x] Task 4: 实现消息对象语音转文字方法（to_text）
- **Priority**: medium
- **Depends On**: Task 3
- **Description**: 
  - 在 wxauto4/msgs/base.py 中实现 to_text() 方法，将语音消息转为文字
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-4.1: 验证 to_text() 返回字符串类型
- **Notes**: 可能需要处理语音消息的特殊逻辑

## [x] Task 5: 实现 Moment 类方法（Publish、Close）
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 在 wxauto4/moment.py 中实现 Publish() 方法，发布朋友圈
  - 实现 Close() 方法，关闭朋友圈页面
- **Acceptance Criteria Addressed**: AC-9, AC-10
- **Test Requirements**:
  - `programmatic` TR-5.1: 验证 Publish() 方法可正常调用
  - `programmatic` TR-5.2: 验证 Close() 方法可正常调用
- **Notes**: 需要参考现有 Moment 类的实现方式

## [x] Task 6: 实现 MomentItem 类 Like 方法
- **Priority**: medium
- **Depends On**: Task 5
- **Description**: 
  - 在 wxauto4/moment.py 中实现 Like() 方法，给朋友圈点赞
- **Acceptance Criteria Addressed**: AC-11
- **Test Requirements**:
  - `programmatic` TR-6.1: 验证 Like() 方法可正常调用
- **Notes**: 需要参考现有 MomentItem 类的实现方式

## [x] Task 7: 实现 Friend 对象 accept 方法
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 在 wxauto4 中实现 Friend 对象的 accept() 方法，通过好友请求并设置备注/标签
- **Acceptance Criteria Addressed**: AC-12
- **Test Requirements**:
  - `programmatic` TR-7.1: 验证 accept() 方法可正常调用
- **Notes**: 需要确认 Friend 对象的定义位置

## [x] Task 8: 添加 WxParam.CHAT_WINDOW_SIZE 属性
- **Priority**: low
- **Depends On**: None
- **Description**: 
  - 在 wxauto4/param.py 中添加 CHAT_WINDOW_SIZE 属性
- **Acceptance Criteria Addressed**: AC-13
- **Test Requirements**:
  - `programmatic` TR-8.1: 验证 WxParam.CHAT_WINDOW_SIZE 可访问且返回元组类型
- **Notes**: 参考现有参数的定义方式