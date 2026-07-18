# wxautox4 拟人化操作 - 实现计划

## [x] Task 1: 创建拟人化工具模块 `human.py`
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 创建 `utils/human.py` 模块
  - 实现 `human_sleep(min, max)` 函数，支持正态分布随机延迟
  - 实现 `human_move_to(x, y)` 函数，使用贝塞尔曲线实现平滑鼠标移动
  - 实现 `human_click(control)` 函数，在控件范围内随机偏移点击位置
  - 实现 `human_type_text(text, control)` 函数，逐字输入文本
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-1.1: 验证 `human_sleep(0.1, 0.3)` 返回值在 0.1-0.3 秒范围内（执行100次统计）
  - `programmatic` TR-1.2: 验证 `human_click()` 生成的点击坐标在控件边界内且非固定中心（执行20次统计）
  - `programmatic` TR-1.3: 验证 `human_type_text()` 按键间隔在 50-200ms 范围内（执行10次统计）
  - `human-judgment` TR-1.4: 观察鼠标移动轨迹是否平滑自然

## [x] Task 2: 修改参数配置，支持随机范围
- **Priority**: medium
- **Depends On**: Task 1
- **Description**: 
  - 修改 `param.py` 中的 `LISTEN_INTERVAL` 为范围配置
  - 添加拟人化相关配置项：鼠标移动速度范围、点击偏移范围、按键间隔范围等
  - 添加开关配置，允许启用/禁用拟人化功能
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-2.1: 验证配置项正确加载和使用
  - `programmatic` TR-2.2: 验证拟人化开关生效（关闭时使用固定延迟）

## [x] Task 3: 修改 `chatbox.py` 消息发送逻辑
- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 修改 `send_text()` 方法，支持 `mode` 参数（'paste' 或 'type'）
  - 短消息（<50字符）默认使用逐字输入模式
  - 长消息使用粘贴模式，并在粘贴前后添加随机延迟
  - 随机化重试逻辑的时间间隔
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 验证短消息（<50字符）使用键盘输入模式
  - `programmatic` TR-3.2: 验证长消息（≥50字符）使用剪贴板粘贴模式
  - `programmatic` TR-3.3: 验证粘贴前后随机延迟在合理范围内

## [x] Task 4: 修改 `sessionbox.py` 搜索和切换逻辑
- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 修改 `search()` 方法，输入搜索关键词时添加随机按键间隔
  - 修改 `switch_chat()` 方法，点击搜索结果时使用平滑鼠标移动
  - 为所有固定延迟替换为 `human_sleep()` 调用
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-4.1: 验证搜索关键词输入间隔在 30-100ms 范围内
  - `programmatic` TR-4.2: 验证点击搜索结果前延迟在 200-500ms 范围内

## [x] Task 5: 修改 `wx.py` 主窗口逻辑
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 替换 `wx.py` 中所有硬编码的 `time.sleep()` 为 `human_sleep()`
  - 修改监听循环，添加随机噪声行为（5-15%概率）
  - 修改导航切换方法，添加随机延迟
- **Acceptance Criteria Addressed**: AC-4, AC-7
- **Test Requirements**:
  - `programmatic` TR-5.1: 验证监听循环中噪声行为按概率执行
  - `programmatic` TR-5.2: 验证所有固定延迟已替换为可变延迟

## [x] Task 6: 更新 `utils/__init__.py` 导出接口
- **Priority**: low
- **Depends On**: Task 1
- **Description**: 
  - 更新 `utils/__init__.py`，导出 `human.py` 中的公共函数
  - 保持向后兼容性，不修改现有导出
- **Acceptance Criteria Addressed**: N/A
- **Test Requirements**:
  - `programmatic` TR-6.1: 验证从 `wxautox4.utils` 可导入拟人化函数

## [x] Task 7: 整合测试和验证
- **Priority**: high
- **Depends On**: Task 1-6
- **Description**: 
  - 运行现有测试用例，确保无回归问题
  - 手动验证拟人化效果：观察鼠标移动、点击位置、输入速度
  - 检查代码风格和质量
- **Acceptance Criteria Addressed**: 所有 AC
- **Test Requirements**:
  - `programmatic` TR-7.1: 确保所有现有测试通过
  - `human-judgment` TR-7.2: 整体拟人化效果评估
