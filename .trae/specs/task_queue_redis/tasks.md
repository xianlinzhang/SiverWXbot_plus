# 微信界面操作任务队列与 Redis 集成改造 - 实现计划

## \[x] Task 1: 创建 RedisManager 模块

* **Priority**: high

* **Depends On**: None

* **Description**:

  * 新建 `core/redis_manager.py` 文件

  * 实现 Redis 连接管理、连接池、自动重连机制

  * 封装 Redis 基本操作方法（get/set/hget/hset/lpush/rpop/zadd/zrange/delete）

  * 实现降级策略：Redis 不可用时自动切换到本地 JSON 文件存储

  * 添加连接状态检测方法

* **Acceptance Criteria Addressed**: AC-1

* **Test Requirements**:

  * `programmatic` TR-1.1: RedisManager 初始化成功，is\_available() 返回正确状态

  * `programmatic` TR-1.2: Redis 可用时，set/get 操作正确执行

  * `programmatic` TR-1.3: Redis 不可用时，自动降级到本地存储，set/get 操作正确执行

  * `human-judgment` TR-1.4: 代码结构清晰，有完整的函数级注释

## \[x] Task 2: 更新配置管理

* **Priority**: high

* **Depends On**: None

* **Description**:

  * 在 `core/config_manager.py` 中添加 Redis 相关配置项（redis\_enabled, redis\_host, redis\_port, redis\_db, redis\_password, redis\_timeout, redis\_retry\_count, redis\_fallback）

  * 添加任务队列相关配置项（task\_queue\_enabled, task\_queue\_max\_pending, task\_queue\_history\_limit）

  * 标记 wx\_lock\_enabled、wx\_lock\_timeout 为废弃

* **Acceptance Criteria Addressed**: AC-1

* **Test Requirements**:

  * `programmatic` TR-2.1: ConfigManager 能正确加载 Redis 和任务队列配置项

  * `programmatic` TR-2.2: 配置项有合理的默认值

  * `human-judgment` TR-2.3: 配置项命名规范，注释清晰

## \[x] Task 3: 创建 TaskQueue 模块

* **Priority**: high

* **Depends On**: Task 1, Task 2

* **Description**:

  * 新建 `core/task_queue.py` 文件

  * 实现 `WXTask` 数据类（id, type, priority, status, params, result, error, create\_time, start\_time, end\_time）

  * 实现 `TaskQueue` 类，基于 Redis List 实现任务队列

  * 实现任务提交（submit）、队列状态查询（get\_queue\_status）、待执行任务列表（get\_pending\_tasks）、任务历史（get\_history）、取消任务（cancel\_task）、清空队列（clear\_queue）方法

  * 实现工作线程主循环（\_worker\_loop），单线程串行执行任务

* **Acceptance Criteria Addressed**: AC-2, AC-6

* **Test Requirements**:

  * `programmatic` TR-3.1: 任务提交后正确入队，队列长度增加

  * `programmatic` TR-3.2: 工作线程正确消费任务，任务状态从 pending 变为 running 再变为 completed

  * `programmatic` TR-3.3: 取消任务后任务状态变为 cancelled，不会被执行

  * `programmatic` TR-3.4: 清空队列后待执行任务数为 0

  * `human-judgment` TR-3.5: 任务类型覆盖所有界面操作（send\_msg, send\_moments, like\_moments, pass\_friend, send\_file）

## \[x] Task 4: 重构 MessageStore 模块

* **Priority**: high

* **Depends On**: Task 1, Task 2

* **Description**:

  * 修改 `core/message_store.py` 文件

  * 将存储后端从 JSON 文件改为 Redis

  * 实现降级到本地存储的逻辑

  * 保留原有 API 接口（save\_message, get\_message, get\_all\_messages, get\_pending\_messages, set\_message\_status, add\_pending\_confirm, confirm\_message, reject\_message, bind\_reply）

  * 新增 `get_history(chat_name, count)` 方法，返回 AI 兼容格式的历史消息

* **Acceptance Criteria Addressed**: AC-3

* **Test Requirements**:

  * `programmatic` TR-4.1: 保存消息后能通过 get\_message 获取，数据一致

  * `programmatic` TR-4.2: 设置消息状态后状态正确更新

  * `programmatic` TR-4.3: 添加待确认消息后能通过 get\_pending\_messages 获取

  * `programmatic` TR-4.4: get\_history 返回正确格式的历史消息，可直接用于 AI 上下文

  * `human-judgment` TR-4.5: API 接口保持兼容，调用方无需修改代码

## \[x] Task 5: 重构 MemoryManager 模块

* **Priority**: high

* **Depends On**: Task 4

* **Description**:

  * 修改 `core/memory_manager.py` 文件

  * 移除 MemoryManager 的独立存储逻辑

  * MemoryManager 改为代理模式，内部调用 MessageStore 的 get\_history 方法

  * 保留 ReplyCountStore 类（独立于消息存储）

  * 保留原有 API 接口（get\_messages, save\_message, clear\_messages）

* **Acceptance Criteria Addressed**: AC-4

* **Test Requirements**:

  * `programmatic` TR-5.1: 调用 MemoryManager.get\_messages 返回与之前相同格式的消息历史

  * `programmatic` TR-5.2: ReplyCountStore 功能正常，不受 MemoryManager 重构影响

  * `human-judgment` TR-5.3: API 接口保持兼容，调用方无需修改代码

## \[x] Task 6: 迁移联系人数据到 Redis

* **Priority**: high

* **Depends On**: Task 1, Task 2

* **Description**:

  * 修改 `core/chatlog_manager.py` 文件

  * chatlog\_contact\_map 改为从 Redis 读写

  * 启动时优先从 Redis 加载联系人缓存

  * 刷新联系人时同步更新 Redis

  * Redis 不可用时降级到内存缓存

* **Acceptance Criteria Addressed**: AC-5

* **Test Requirements**:

  * `programmatic` TR-6.1: Redis 可用时，启动后从 Redis 加载联系人数据

  * `programmatic` TR-6.2: 刷新联系人后数据正确更新到 Redis

  * `programmatic` TR-6.3: Redis 不可用时，降级到内存缓存，功能正常

  * `human-judgment` TR-6.4: 联系人数据格式保持一致

## \[x] Task 7: 集成到 WXBot 主类

* **Priority**: high

* **Depends On**: Task 1, Task 2, Task 3, Task 4, Task 5, Task 6

* **Description**:

  * 修改 `wxbot_core.py` 文件

  * 初始化 `self.redis_manager = RedisManager(self.config)`

  * 初始化 `self.task_queue = TaskQueue(self)`

  * 移除 `self.wx_lock = WXLock(self.config)`

  * 添加启动时启动 Redis 连接和任务队列工作线程的逻辑

  * 添加退出时优雅停止的逻辑

* **Acceptance Criteria Addressed**: AC-2, AC-3, AC-4, AC-5, AC-6

* **Test Requirements**:

  * `programmatic` TR-7.1: WXBot 初始化时正确创建 redis\_manager 和 task\_queue 实例

  * `programmatic` TR-7.2: 启动后任务队列工作线程正常运行

  * `programmatic` TR-7.3: 退出时任务队列工作线程优雅停止

  * `human-judgment` TR-7.4: wx\_lock 相关代码已移除

## \[x] Task 8: 改造 message\_handler.py

* **Priority**: high

* **Depends On**: Task 3, Task 7

* **Description**:

  * 修改 `core/message_handler.py` 文件

  * 移除 wx\_lock 相关代码

  * 将 `SendMsg` 调用改为提交 send\_msg 任务到队列

  * 保持消息存储功能（已改为 Redis 后端）

* **Acceptance Criteria Addressed**: AC-6

* **Test Requirements**:

  * `programmatic` TR-8.1: AI 回复消息时正确提交 send\_msg 任务到队列

  * `programmatic` TR-8.2: 任务队列正确执行消息发送任务

  * `human-judgment` TR-8.3: wx\_lock 相关代码已移除

## \[x] Task 9: 改造 wx\_utils.py

* **Priority**: high

* **Depends On**: Task 3, Task 7

* **Description**:

  * 修改 `core/wx_utils.py` 文件

  * 移除所有 wx\_lock.acquire/release 调用

  * 将 send\_scheduled\_msg 改为提交 send\_msg 任务

  * 将 send\_scheduled\_moments 改为提交 send\_moments 任务

  * 将 \_do\_moments\_like 改为提交 like\_moments 任务

  * 将 \_check\_random\_moments 改为提交 send\_moments 任务

  * 将 \_check\_random\_msg 改为提交 send\_msg 任务

  * 将 Pass\_New\_Friends 改为提交 pass\_friend 任务

* **Acceptance Criteria Addressed**: AC-6

* **Test Requirements**:

  * `programmatic` TR-9.1: 所有界面操作函数正确提交任务到队列

  * `human-judgment` TR-9.2: wx\_lock 相关代码已完全移除

  * `human-judgment` TR-9.3: 任务参数传递正确，包含所有必要信息

## \[x] Task 10: 改造 command\_handler.py

* **Priority**: medium

* **Depends On**: Task 1, Task 3, Task 6

* **Description**:

  * 修改 `core/command_handler.py` 文件

  * 移除微信锁相关命令（/微信锁、/锁状态、/解锁、/强制解锁）

  * 移除消息存储相关命令（/消息存储、/消息列表、/消息统计）

  * 添加任务队列相关命令（/任务队列、/任务列表、/任务历史、/清空队列、/取消任务）

  * 添加 Redis 状态查询命令（/Redis状态、/Redis测试）

  * 添加联系人缓存命令（/联系人缓存）

* **Acceptance Criteria Addressed**: AC-7

* **Test Requirements**:

  * `human-judgment` TR-10.1: 新增命令能正确执行并返回结果

  * `human-judgment` TR-10.2: 移除的命令不再响应

  * `human-judgment` TR-10.3: 命令格式统一，支持中文和英文两种格式

## \[x] Task 11: 添加 Web API 接口

* **Priority**: medium

* **Depends On**: Task 1, Task 3, Task 4, Task 6

* **Description**:

  * 修改 `web_server.py` 文件

  * 添加任务队列相关 API：/api/tasks/status, /api/tasks/pending, /api/tasks/history, /api/tasks/cancel, /api/tasks/clear

  * 添加消息管理相关 API：/api/messages/pending\_confirm, /api/messages/confirm, /api/messages/reject, /api/messages/search, /api/messages/stats

  * 添加联系人管理相关 API：/api/contacts/list, /api/contacts/search, /api/contacts/messages, /api/contacts/refresh

* **Acceptance Criteria Addressed**: AC-8

* **Test Requirements**:

  * `programmatic` TR-11.1: 所有 API 接口返回正确的 HTTP 状态码

  * `programmatic` TR-11.2: API 返回正确格式的 JSON 响应

  * `programmatic` TR-11.3: POST 请求正确处理参数并返回结果

  * `human-judgment` TR-11.4: API 路径命名规范，与界面功能对应

## \[x] Task 12: 添加界面标签页

* **Priority**: medium

* **Depends On**: Task 11

* **Description**:

  * 修改 `templates/dashboard.html` 文件

  * 在侧边栏添加三个新导航项：tab-tasks（任务队列）、tab-messages（消息管理）、tab-contacts（联系人管理）

  * 添加任务队列标签页内容：队列状态卡片、待执行任务列表、任务历史表格、取消任务和清空队列按钮

  * 添加消息管理标签页内容：消息统计卡片、待确认消息列表、消息搜索功能

  * 添加联系人管理标签页内容：联系人统计卡片、联系人搜索功能、联系人列表、查看消息记录

  * 添加对应的 JavaScript 逻辑：数据加载、操作处理、定时刷新

* **Acceptance Criteria Addressed**: AC-9

* **Test Requirements**:

  * `human-judgment` TR-12.1: 侧边栏导航正确显示三个新标签页

  * `human-judgment` TR-12.2: 任务队列标签页正确显示队列状态、待执行任务、任务历史

  * `human-judgment` TR-12.3: 消息管理标签页正确显示待确认消息、消息搜索结果

  * `human-judgment` TR-12.4: 联系人管理标签页正确显示联系人列表、联系人统计

  * `human-judgment` TR-12.5: 页面操作按钮可正常使用（取消任务、清空队列、确认消息、拒绝消息、刷新联系人）

  * `human-judgment` TR-12.6: 页面定时刷新功能正常，数据实时更新

## \[x] Task 13: 清理和验证

* **Priority**: medium

* **Depends On**: All previous tasks

* **Description**:

  * 删除 `core/wx_lock.py` 文件

  * 语法检查所有修改的文件

  * 验证私聊 AI 回复功能正常

  * 验证定时消息/朋友圈功能正常

  * 验证管理员命令正常

  * 验证 Redis 连接和降级策略正常

  * 验证 Web 界面新标签页功能正常

* **Acceptance Criteria Addressed**: All ACs

* **Test Requirements**:

  * `programmatic` TR-13.1: 所有 Python 文件语法检查通过

  * `human-judgment` TR-13.2: 私聊 AI 回复功能正常，消息通过队列发送

  * `human-judgment` TR-13.3: 定时消息和朋友圈功能正常，任务正确入队并执行

  * `human-judgment` TR-13.4: 管理员命令响应正常

  * `human-judgment` TR-13.5: Redis 启用时数据正确存储到 Redis，禁用时使用本地存储

  * `human-judgment` TR-13.6: Web 界面新标签页功能正常，数据正确显示

