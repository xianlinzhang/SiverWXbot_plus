# 微信界面操作任务队列与 Redis 集成改造计划

## 一、现状分析

### 1.1 当前架构问题

**WXLock（微信界面操作锁）**

* 位置：[wx\_lock.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/wx_lock.py)

* 机制：使用 `threading.Lock` 互斥锁，操作前 acquire，操作后 release

* 问题：

  * 锁是同步阻塞的，任务到来时要么等待要么失败，没有排队机制

  * 无法查看待执行任务列表，无法管理任务优先级

  * 每个界面操作点都要手动加锁/释放，代码重复且容易遗漏

  * 超时自动释放机制复杂，实际价值有限

**MessageStore（消息存储）**

* 位置：[message\_store.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/message_store.py)

* 功能：消息持久化到 JSON 文件，支持状态管理、待确认队列等

* 问题：

  * 每条消息都要读写磁盘，性能开销大

  * 待确认队列在内存中，重启后丢失

  * 与 Chatlog 监听模式的消息序列管理有重叠

**联系人数据（chatlog\_contact\_map）**

* 位置：[chatlog\_manager.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/chatlog_manager.py#L33)

* 当前：存储在 `self.bot.chatlog_contact_map` 内存字典中，重启后需重新获取

* 问题：每次重启都要调用 Chatlog API 获取联系人，速度慢且浪费资源

**MemoryManager（对话记忆）**

* 位置：[memory\_manager.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/memory_manager.py)

* 当前：存储在本地 JSON 文件中

* 问题：多进程/多实例无法共享记忆数据

**界面操作分散**

* 发送消息：[message\_handler.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/message_handler.py#L562-L702) `wx_send_ai`

* 定时消息：[wx\_utils.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/wx_utils.py#L180-L250) `send_scheduled_msg`

* 定时朋友圈：[wx\_utils.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/wx_utils.py#L252-L311) `send_scheduled_moments`

* 随机朋友圈点赞：[wx\_utils.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/wx_utils.py#L313-L335) `_do_moments_like`

* 随机朋友圈：[wx\_utils.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/wx_utils.py#L337-L366) `_check_random_moments`

* 随机消息：[wx\_utils.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/wx_utils.py#L368) `_check_random_msg`

* 通过好友申请：[wx\_utils.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/wx_utils.py#L144) `Pass_New_Friends`

### 1.2 改造目标

用**任务队列 + Redis** 替代 WXLock + MessageStore 的组合：

* 所有界面操作以任务形式提交到队列，单线程串行执行

* 任务队列支持 Redis 持久化，重启后未完成任务不丢失

* 消息存储迁移到 Redis，支持状态管理、待确认队列

* 联系人数据缓存到 Redis，减少 Chatlog API 调用

* 对话记忆可选迁移到 Redis，支持多实例共享

* Redis 不可用时自动降级到本地存储

***

## 二、方案设计

### 2.1 Redis 数据结构规划

| 数据类型         | Redis Key                                    | Redis 类型 | 说明                                       |
| ------------ | -------------------------------------------- | -------- | ---------------------------------------- |
| 任务队列         | `wxbot:{wx_id}:tasks:pending`                | List     | 待执行任务列表（LPUSH/RPOP）                      |
| 任务详情         | `wxbot:{wx_id}:tasks:{task_id}`              | Hash     | 单个任务的详细信息                                |
| 任务历史         | `wxbot:{wx_id}:tasks:history`                | ZSet     | 已完成任务（score=时间戳）                         |
| 当前任务         | `wxbot:{wx_id}:tasks:current`                | String   | 当前正在执行的任务 ID                             |
| 消息存储         | `wxbot:{wx_id}:messages:{chat_name}`         | List     | 会话消息列表（最多 N 条）                           |
| 消息状态         | `wxbot:{wx_id}:msg_status:{message_id}`      | String   | 消息状态（pending/processed/replied）          |
| 待确认队列        | `wxbot:{wx_id}:pending_confirm`              | List     | 待人工确认的消息                                 |
| 待确认详情        | `wxbot:{wx_id}:pending_confirm:{message_id}` | Hash     | 待确认消息详情                                  |
| 联系人映射        | `wxbot:{wx_id}:contacts`                     | Hash     | 联系人双向映射（wxid/nickname/remark -> contact） |
| 联系人列表        | `wxbot:{wx_id}:contacts:list`                | Set      | 所有联系人 wxid 集合                            |
| Chatlog 最后序号 | `wxbot:{wx_id}:chatlog_seq:{chat_name}`      | String   | 各会话最后处理的消息 seq                           |
| 对话记忆         | `wxbot:{wx_id}:memory:{chat_name}`           | List     | 会话对话历史                                   |
| 回复计数         | `wxbot:{wx_id}:reply_count:{user_key}`       | Hash     | 用户 AI 回复计数                               |

### 2.2 Redis 管理器（RedisManager）

新建文件：`core/redis_manager.py`

**核心职责：**

* 统一管理 Redis 连接（连接池）

* 提供 Redis 操作封装方法

* 实现降级策略（Redis 不可用时 fallback 到本地存储）

* 提供连接状态检测和自动重连

**核心方法：**

* `__init__(config)`: 初始化，读取 Redis 配置

* `connect()`: 建立 Redis 连接

* `is_available()`: 检查 Redis 是否可用

* `disconnect()`: 断开连接

* `get(key)`: 获取值

* `set(key, value, expire=None)`: 设置值

* `hget(hash_key, field)`: 获取 Hash 字段

* `hset(hash_key, field, value)`: 设置 Hash 字段

* `lpush(list_key, value)`: 列表左侧插入

* `rpop(list_key)`: 列表右侧弹出

* `zadd(zset_key, score, value)`: ZSet 添加

* `zrange(zset_key, start, end)`: ZSet 范围查询

* `delete(*keys)`: 删除键

**降级策略：**

* Redis 连接失败时，自动切换到本地 JSON 文件存储

* 提供统一接口，调用方无需关心底层存储

* 记录降级日志，提醒用户 Redis 不可用

### 2.3 任务队列核心类（TaskQueue）

新建文件：`core/task_queue.py`

**核心数据结构：**

* `_redis_manager`: RedisManager 实例

* `_pending_key`: 待执行任务列表的 Redis Key

* `_history_key`: 任务历史的 Redis Key

* `_current_key`: 当前任务的 Redis Key

* `_worker_thread`: 工作线程，单线程消费队列

**任务对象（WXTask）：**

```
- id: 任务唯一ID
- type: 任务类型（send_msg / send_moments / like_moments / pass_friend / send_file）
- priority: 优先级（数字越小优先级越高，默认 5）
- status: pending / running / completed / failed / cancelled
- params: 任务参数字典
- result: 执行结果
- error: 错误信息
- create_time: 创建时间
- start_time: 开始时间
- end_time: 结束时间
- callback: 完成回调函数（可选）
```

**核心方法：**

* `submit(task_type, params, priority=5, callback=None)`: 提交任务

* `get_queue_status()`: 获取队列状态（待执行数、当前任务、历史统计）

* `get_pending_tasks()`: 获取待执行任务列表

* `get_history(limit=50)`: 获取历史任务

* `cancel_task(task_id)`: 取消待执行任务

* `clear_queue()`: 清空队列

* `_worker_loop()`: 工作线程主循环

### 2.4 消息存储重构（MessageStore）与 MemoryManager 合并

**核心决策：MemoryManager 合并到 MessageStore**

**分析：**

* MemoryManager 和 MessageStore 都存储相同的对话消息，只是格式不同

* MemoryManager 存储轻量格式（time/type/attr/sender/content），用于 AI 上下文

* MessageStore 存储完整格式（含状态、确认信息等），用于消息审计和状态管理

* 两者数据重叠，且 Chatlog 已提供完整历史，MemoryManager 的独立存储价值有限

**合并方案：**

* 将 MemoryManager 的存储功能合并到 MessageStore（统一存储到 Redis）

* MessageStore 新增 `get_history(chat_name, count)` 方法，返回 AI 兼容格式

* 保留 MemoryManager 的 API 接口作为 MessageStore 的代理，确保兼容性

* 删除 MemoryManager 的独立存储逻辑（save\_message/get\_messages/clear\_messages）

**重构文件：[message\_store.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/message_store.py)**

**核心变更：**

* 将存储后端从本地 JSON 文件改为 Redis

* 新增 `get_history(chat_name, count)`: 返回 AI 兼容格式的历史消息

* 保留原有 API 接口，确保兼容性

* 支持 Redis 降级到本地存储

* 待确认队列改为 Redis List，重启后不丢失

**保留方法：**

* `save_message()`: 保存消息到 Redis

* `get_message()`: 根据 ID 获取消息

* `get_all_messages()`: 获取会话所有消息

* `get_history()`: 获取 AI 兼容格式的历史消息（新增，替代 MemoryManager.get\_messages）

* `get_pending_messages()`: 获取待处理消息

* `set_message_status()`: 设置消息状态

* `add_pending_confirm()`: 添加待确认消息

* `confirm_message()`: 确认消息

* `reject_message()`: 拒绝消息

* `bind_reply()`: 绑定回复

**重构文件：[memory\_manager.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/memory_manager.py)**

**核心变更：**

* 移除 `MemoryManager` 类的独立存储逻辑

* `MemoryManager` 改为代理模式，内部调用 MessageStore 的方法

* 保留 `ReplyCountStore` 类（独立于消息存储）

* 保留原有 API 接口，确保兼容性

### 2.5 联系人数据迁移（ChatlogManager）

修改文件：[chatlog\_manager.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/chatlog_manager.py)

**核心变更：**

* `chatlog_contact_map` 改为从 Redis 读写

* 启动时先从 Redis 加载联系人缓存

* 刷新联系人时同时更新 Redis

* Redis 不可用时降级到内存缓存

### 2.6 与现有模块的集成

#### message\_handler.py（消息处理）

* 当前：AI 生成回复后，直接调用 `chat.SendMsg()` 并手动加 wx\_lock

* 改造后：AI 生成回复后，将发送任务提交到 task\_queue，立即返回

#### wx\_utils.py（辅助工具）

* `send_scheduled_msg`: 定时消息触发时，提交 send\_msg 任务到队列

* `send_scheduled_moments`: 定时朋友圈触发时，提交 send\_moments 任务

* `_do_moments_like`: 随机点赞触发时，提交 like\_moments 任务

* `_check_random_moments`: 随机朋友圈触发时，提交 send\_moments 任务

* `_check_random_msg`: 随机消息触发时，提交 send\_msg 任务

* `Pass_New_Friends`: 提交 pass\_friend 任务

#### wxbot\_core.py（主类）

* 移除 `self.wx_lock = WXLock(self.config)`

* 修改 `self.message_store = MessageStore(self.config)`（改用 Redis）

* 新增 `self.redis_manager = RedisManager(self.config)`

* 新增 `self.task_queue = TaskQueue(self)`

* 启动时启动 Redis 连接和任务队列工作线程，退出时优雅停止

### 2.7 管理员命令更新

在 [command\_handler.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/command_handler.py) 中添加/修改命令：

| 命令                                 | 说明                |
| ---------------------------------- | ----------------- |
| `/任务队列` 或 `/task queue`            | 查看队列状态（待执行数、当前任务） |
| `/任务列表` 或 `/task list`             | 查看待执行任务列表         |
| `/任务历史` 或 `/task history`          | 查看最近任务历史          |
| `/清空队列` 或 `/task clear`            | 清空待执行队列           |
| `/取消任务 <id>` 或 `/task cancel <id>` | 取消指定任务            |
| `/Redis状态`                         | 查看 Redis 连接状态     |
| `/Redis测试`                         | 测试 Redis 连接       |
| `/联系人缓存`                           | 刷新联系人缓存到 Redis    |
| （移除）`/微信锁` 相关命令                    | <br />            |
| （移除）`/消息存储` 相关命令                   | <br />            |

### 2.8 界面功能设计

在管理界面中添加以下新标签页，支持在浏览器中查看和操作：

#### 2.8.1 任务队列标签页（tab-tasks）

**功能：**

* 查看队列状态（待执行任务数、当前执行任务、队列统计）

* 查看待执行任务列表（任务ID、类型、目标、优先级、创建时间）

* 查看任务历史（任务ID、类型、状态、结果、执行时间）

* 取消指定待执行任务

* 清空队列

* 实时刷新队列状态

**API 接口：**

* `GET /api/tasks/status` - 获取队列状态

* `GET /api/tasks/pending` - 获取待执行任务列表

* `GET /api/tasks/history` - 获取任务历史

* `POST /api/tasks/cancel` - 取消指定任务

* `POST /api/tasks/clear` - 清空队列

#### 2.8.2 消息管理标签页（tab-messages）

**功能：**

* 查看待确认消息列表（联系人、消息内容、接收时间）

* 确认消息（同意发送回复）

* 拒绝消息（不发送回复）

* 搜索消息（按联系人、关键词）

* 查看消息状态统计

**API 接口：**

* `GET /api/messages/pending_confirm` - 获取待确认消息列表

* `POST /api/messages/confirm` - 确认消息

* `POST /api/messages/reject` - 拒绝消息

* `GET /api/messages/search` - 搜索消息

* `GET /api/messages/stats` - 获取消息统计

#### 2.8.3 联系人管理标签页（tab-contacts）

**功能：**

* 查看联系人列表（备注名、昵称、微信号、wxid）

* 搜索联系人（按备注名、昵称、微信号）

* 查看联系人的消息记录

* 刷新联系人缓存

* 查看联系人统计

**API 接口：**

* `GET /api/contacts/list` - 获取联系人列表

* `GET /api/contacts/search` - 搜索联系人

* `GET /api/contacts/messages` - 获取联系人消息记录

* `POST /api/contacts/refresh` - 刷新联系人缓存

#### 2.8.4 界面布局设计

**任务队列标签页布局：**

```
┌─────────────────────────────────────────────────────┐
│ 队列状态                                            │
│ ┌──────────┬──────────┬──────────┬──────────┐      │
│ │待执行数  │ 当前任务  │ 成功数   │ 失败数   │      │
│ │  5       │ send_msg │  120     │  3       │      │
│ └──────────┴──────────┴──────────┴──────────┘      │
├─────────────────────────────────────────────────────┤
│ 待执行任务                                          │
│ ┌──────┬──────────┬──────────┬─────────┬────────┐ │
│ │任务ID│ 类型     │ 目标     │ 优先级  │ 创建时间│ │
│ │123abc│ send_msg │ 张三     │ 1       │ 10:30  │ │
│ │456def│ moments  │ -        │ 5       │ 10:31  │ │
│ └──────┴──────────┴──────────┴─────────┴────────┘ │
│ [取消任务] [清空队列]                              │
├─────────────────────────────────────────────────────┤
│ 任务历史（最近50条）                                │
│ ┌──────┬──────────┬──────────┬─────────┬────────┐ │
│ │任务ID│ 类型     │ 状态     │ 结果    │ 时间   │ │
│ │789ghi│ send_msg │ completed│ success │ 10:28  │ │
│ └──────┴──────────┴──────────┴─────────┴────────┘ │
└─────────────────────────────────────────────────────┘
```

**消息管理标签页布局：**

```
┌─────────────────────────────────────────────────────┐
│ 消息统计                                            │
│ ┌──────────┬──────────┬──────────┬──────────┐      │
│ │待确认数  │ 已处理数  │ 已回复数  │ 总消息数 │      │
│ │  3       │  250     │  200     │  500     │      │
│ └──────────┴──────────┴──────────┴──────────┘      │
├─────────────────────────────────────────────────────┤
│ 待确认消息                                          │
│ ┌──────────┬──────────┬───────────────────────┐     │
│ │ 联系人   │ 时间     │ 消息内容               │     │
│ │ 张三     │ 10:25    │ 你好，请问xxx？       │     │
│ │ 李四     │ 10:28    │ 帮我查一下xxx         │     │
│ └──────────┴──────────┴───────────────────────┘     │
│ [确认] [拒绝]                                       │
├─────────────────────────────────────────────────────┤
│ 消息搜索                                            │
│ [搜索框] [搜索按钮]                                  │
│ ┌──────────┬──────────┬──────────┬──────────┐      │
│ │联系人   │ 时间     │ 状态     │ 内容     │      │
│ └──────────┴──────────┴──────────┴──────────┘      │
└─────────────────────────────────────────────────────┘
```

**联系人管理标签页布局：**

```
┌─────────────────────────────────────────────────────┐
│ 联系人统计                                          │
│ ┌──────────┬──────────┬──────────┐                 │
│ │总人数    │ 好友数    │ 群聊数   │                 │
│ │  200     │  150     │  50      │                 │
│ └──────────┴──────────┴──────────┘                 │
│ [刷新联系人]                                        │
├─────────────────────────────────────────────────────┤
│ 联系人搜索                                          │
│ [搜索框] [搜索按钮]                                  │
├─────────────────────────────────────────────────────┤
│ 联系人列表                                          │
│ ┌──────────┬──────────┬──────────┬──────────┐      │
│ │备注名    │ 昵称     │ 微信号   │ wxid     │      │
│ │ 张三     │ ZhangSan │ zhangsan │ wxid_xxx │      │
│ │ 李四     │ LiSi     │ lisi     │ wxid_yyy │      │
│ └──────────┴──────────┴──────────┴──────────┘      │
│ 点击联系人查看消息记录...                             │
└─────────────────────────────────────────────────────┘
```

#### 2.8.5 界面修改文件

| 文件                         | 操作 | 说明                   |
| -------------------------- | -- | -------------------- |
| `templates/dashboard.html` | 修改 | 添加任务队列、消息管理、联系人管理标签页 |
| `web_server.py`            | 修改 | 添加相关 API 路由          |

### 2.9 配置更新

在 [config\_manager.py](file:///e:/Project/wxauto/SiverWXbot_plus/core/config_manager.py) 中新增 Redis 相关配置：

```python
# ---------- Redis 配置 ----------
self.redis_enabled = False           # Redis 总开关
self.redis_host = '127.0.0.1'        # Redis 主机地址
self.redis_port = 6379               # Redis 端口
self.redis_db = 0                    # Redis 数据库编号
self.redis_password = ''             # Redis 密码（可选）
self.redis_timeout = 5               # Redis 连接超时时间（秒）
self.redis_retry_count = 3           # 连接重试次数
self.redis_fallback = True           # Redis 不可用时是否降级到本地存储

# ---------- 任务队列配置 ----------
self.task_queue_enabled = True       # 任务队列总开关
self.task_queue_max_pending = 1000   # 最大待执行任务数
self.task_queue_history_limit = 500  # 任务历史保留条数
```

***

## 三、实施步骤

### 步骤 1：创建 Redis 管理器模块

* 新建 `core/redis_manager.py`

* 实现 Redis 连接管理、操作封装、降级策略

* 添加连接状态检测和自动重连机制

### 步骤 2：更新配置管理

* 在 `config_manager.py` 中添加 Redis 相关配置项

* 添加任务队列相关配置项

* 标记 `wx_lock_enabled`、`wx_lock_timeout` 为废弃

### 步骤 3：创建任务队列模块

* 新建 `core/task_queue.py`

* 实现 `WXTask` 数据类

* 实现 `TaskQueue` 类，基于 Redis List 实现任务队列

* 编写工作线程主循环

### 步骤 4：重构消息存储模块

* 修改 `core/message_store.py`

* 将存储后端从 JSON 文件改为 Redis

* 实现降级到本地存储的逻辑

* 保留原有 API 接口

### 步骤 5：迁移联系人数据到 Redis

* 修改 `core/chatlog_manager.py`

* `chatlog_contact_map` 改为从 Redis 读写

* 启动时优先从 Redis 加载

* 刷新联系人时同步更新 Redis

### 步骤 6：集成到 WXBot 主类

* 在 `wxbot_core.py` 中初始化 `self.redis_manager` 和 `self.task_queue`

* 移除 `wx_lock` 的初始化

* 添加启动/停止逻辑

### 步骤 7：改造 message\_handler.py

* 移除 `wx_lock` 相关代码

* 将 `SendMsg` 调用改为提交 `send_msg` 任务

* 保持消息存储功能（已改为 Redis 后端）

### 步骤 8：改造 wx\_utils.py

* 移除所有 `wx_lock.acquire/release` 调用

* 所有界面操作改为提交任务到队列

### 步骤 9：改造 command\_handler.py

* 移除微信锁相关命令

* 移除消息存储相关命令

* 添加任务队列相关命令

* 添加 Redis 状态查询命令

### 步骤 10：添加 Web API 接口

* 在 `web_server.py` 中添加任务队列相关 API：

  * `/api/tasks/status` - 获取队列状态

  * `/api/tasks/pending` - 获取待执行任务列表

  * `/api/tasks/history` - 获取任务历史

  * `/api/tasks/cancel` - 取消指定任务

  * `/api/tasks/clear` - 清空队列

* 在 `web_server.py` 中添加消息管理相关 API：

  * `/api/messages/pending_confirm` - 获取待确认消息列表

  * `/api/messages/confirm` - 确认消息

  * `/api/messages/reject` - 拒绝消息

  * `/api/messages/search` - 搜索消息

  * `/api/messages/stats` - 获取消息统计

* 在 `web_server.py` 中添加联系人管理相关 API：

  * `/api/contacts/list` - 获取联系人列表

  * `/api/contacts/search` - 搜索联系人

  * `/api/contacts/messages` - 获取联系人消息记录

  * `/api/contacts/refresh` - 刷新联系人缓存

### 步骤 11：添加界面标签页

* 在 `templates/dashboard.html` 侧边栏添加三个新导航项：

  * `tab-tasks` - 任务队列

  * `tab-messages` - 消息管理

  * `tab-contacts` - 联系人管理

* 添加任务队列标签页内容（队列状态、待执行任务、任务历史）

* 添加消息管理标签页内容（消息统计、待确认消息、消息搜索）

* 添加联系人管理标签页内容（联系人统计、联系人列表、消息记录）

* 添加对应的 JavaScript 逻辑（数据加载、操作处理、实时刷新）

### 步骤 12：清理和验证

* 删除 `core/wx_lock.py`

* 语法检查所有修改的文件

* 验证私聊 AI 回复功能

* 验证定时消息/朋友圈功能

* 验证管理员命令

* 验证 Redis 连接和降级策略

* 验证 Web 界面新标签页功能

***

## 四、风险与注意事项

### 4.1 风险点

1. **Redis 依赖问题**

   * 用户环境可能没有安装 Redis

   * 对策：Redis 设为可选配置（默认禁用），未启用时使用本地存储

2. **异步发送影响同步逻辑**

   * 当前 `wx_send_ai` 是同步的，发送结果直接返回

   * 改为队列后，调用方无法立即知道发送结果

   * 对策：通过 callback 回调处理结果

3. **消息延迟增加**

   * 队列串行执行，如果队列积压，消息回复延迟会增加

   * 对策：设置合理的优先级，监控队列长度

4. **Redis 故障降级**

   * Redis 连接中断时需要平滑降级

   * 对策：实现自动重连 + 本地存储降级，记录降级日志

5. **数据一致性**

   * Redis 和本地存储之间的数据同步问题

   * 对策：降级时只写本地，恢复后可选同步

### 4.2 兼容性考虑

* 配置项不直接删除，标记为"已废弃"

* Redis 默认禁用，不影响现有用户

* 保留旧命令名作为别名一段时间

* 消息存储 API 保持不变

***

## 五、文件变更清单

| 文件                         | 操作 | 说明                                                       |
| -------------------------- | -- | -------------------------------------------------------- |
| `core/redis_manager.py`    | 新建 | Redis 连接管理和操作封装                                          |
| `core/task_queue.py`       | 新建 | 任务队列核心模块                                                 |
| `core/wx_lock.py`          | 删除 | 微信锁模块，功能由队列替代                                            |
| `core/message_store.py`    | 重构 | 存储后端改为 Redis，支持降级                                        |
| `core/config_manager.py`   | 修改 | 添加 Redis 和任务队列配置项                                        |
| `core/chatlog_manager.py`  | 修改 | 联系人数据迁移到 Redis                                           |
| `core/memory_manager.py`   | 重构 | MemoryManager 合并到 MessageStore，改为代理模式；保留 ReplyCountStore |
| `wxbot_core.py`            | 修改 | 添加 redis\_manager 和 task\_queue                          |
| `core/message_handler.py`  | 修改 | 发送消息改为提交任务                                               |
| `core/wx_utils.py`         | 修改 | 所有界面操作改为提交任务                                             |
| `core/command_handler.py`  | 修改 | 添加队列和 Redis 相关命令                                         |
| `web_server.py`            | 修改 | 添加任务队列、消息管理、联系人管理相关 API 接口                               |
| `templates/dashboard.html` | 修改 | 添加任务队列、消息管理、联系人管理标签页                                     |

