# 朋友圈拟人化操作 - 实现计划

## [x] Task 1: 添加拟人化工具函数导入
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `moment.py` 文件顶部导入 `human.py` 中的必要函数：`human_click`, `human_sleep`, `human_type_text`
  - 确保导入路径正确，与项目其他模块保持一致
- **Acceptance Criteria Addressed**: [AC-1, AC-2, AC-3, AC-4, AC-5, AC-6]
- **Test Requirements**:
  - `programmatic` TR-1.1: 导入语句无语法错误，模块可正常导入
  - `human-judgement` TR-1.2: 导入方式与项目其他模块（如 `sessionbox.py`）保持一致
- **Notes**: 需要处理可能的导入异常情况

## [x] Task 2: 实现点赞操作拟人化
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 修改 `Moment._invoke_action_menu()` 方法中的点击操作，支持拟人化
  - 修改 `MomentActionMenu.like()` 和 `comment()` 方法中的点击操作，支持拟人化
  - 使用 `WxParam.ENABLE_HUMANIZATION` 判断是否启用拟人化
- **Acceptance Criteria Addressed**: [AC-1, AC-2, AC-6]
- **Test Requirements**:
  - `programmatic` TR-2.1: 当 `ENABLE_HUMANIZATION=False` 时，使用原始 `Click()` 方法
  - `human-judgement` TR-2.2: 当 `ENABLE_HUMANIZATION=True` 时，使用 `human_click()` 方法
- **Notes**: 需要确保右键菜单定位逻辑不受影响

## [x] Task 3: 实现评论操作拟人化
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 修改 `Moment.Comment()` 方法中的评论控件点击操作，支持拟人化
  - 修改 `MomentCommentDialog.send()` 方法中的输入方式：短消息（<50字符）使用 `human_type_text()` 逐字输入，长消息使用粘贴
  - 粘贴前后添加随机延迟（使用 `human_sleep()` 和 `WxParam.PASTE_DELAY_MIN/MAX`）
- **Acceptance Criteria Addressed**: [AC-3, AC-4, AC-6]
- **Test Requirements**:
  - `programmatic` TR-3.1: 短消息（<50字符）使用逐字输入模式
  - `programmatic` TR-3.2: 长消息（>=50字符）使用粘贴模式，粘贴前后有延迟
  - `human-judgement` TR-3.3: 当 `ENABLE_HUMANIZATION=False` 时，使用原始粘贴方式
- **Notes**: 需要处理特殊字符转义

## [x] Task 4: 实现发布操作拟人化
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 修改 `Moment.Publish()` 方法中的所有点击操作（发布按钮、添加图片按钮、打开按钮、发表按钮），支持拟人化
  - 将固定延迟 `time.sleep()` 替换为 `human_sleep()` 使用正态分布随机延迟
  - 文本输入支持拟人化：短消息逐字输入，长消息粘贴
- **Acceptance Criteria Addressed**: [AC-5, AC-6]
- **Test Requirements**:
  - `programmatic` TR-4.1: 所有 `time.sleep()` 调用替换为 `human_sleep()`
  - `programmatic` TR-4.2: 所有控件点击操作支持拟人化模式切换
  - `human-judgement` TR-4.3: 拟人化模式下操作更自然，符合人类行为
- **Notes**: 需要注意发布流程中的控件定位逻辑

## [x] Task 5: 实现评论回复操作拟人化
- **Priority**: medium
- **Depends On**: Task 1
- **Description**: 
  - 修改 `Moment.Comment()` 方法中回复评论时的控件点击操作，支持拟人化
  - 确保回复评论流程与直接评论流程一致
- **Acceptance Criteria Addressed**: [AC-3, AC-4, AC-6]
- **Test Requirements**:
  - `human-judgement` TR-5.1: 回复评论时的点击操作支持拟人化模式切换
- **Notes**: 回复评论流程需要先点击评论控件打开回复输入框

## [x] Task 6: 代码验证与测试
- **Priority**: high
- **Depends On**: Task 2, Task 3, Task 4, Task 5
- **Description**: 
  - 运行项目测试套件，确保修改不破坏现有功能
  - 验证拟人化配置项 `ENABLE_HUMANIZATION` 可正确控制拟人化行为
- **Acceptance Criteria Addressed**: [AC-1, AC-2, AC-3, AC-4, AC-5, AC-6]
- **Test Requirements**:
  - `programmatic` TR-6.1: 项目测试套件全部通过
  - `human-judgement` TR-6.2: 代码风格与项目其他模块保持一致
- **Notes**: 需要确保没有引入新的依赖问题