# 消息存储与标注层优化实现计划

## 需求分析

### 核心需求
1. **数据存储层**：在 Chatlog 监听人和消息和发送消息之间加一层数据存储和标注
2. **消息未读设置**：消息可设置未读状态
3. **私聊回复确认**：私聊设置自动回复前确认（自动和人工都支持）
4. **消息回复对应**：消息和回复有对应关系
5. **微信界面操作锁**：操作微信界面需要有锁，可手动设置占用和释放，其他任务需获取锁才能操作，未获取锁的任务延迟执行

### 技术要求
- 拆分出来的文件必须放到 `core` 目录
- 遵循工程约定（随机延迟、贝塞尔曲线等）
- 保持代码风格一致性

## 现有架构分析

### 当前消息处理流程
```
消息监听(wxautox/Chatlog) → MessageHandler → AI API → 发送消息
```

### 关键模块
| 模块 | 职责 |
|------|------|
| `core/chatlog_manager.py` | Chatlog API 轮询监听、消息转换、消息处理 |
| `core/message_handler.py` | 消息分发、AI 回复生成、发送处理 |
| `core/listen_manager.py` | 监听模式管理、消息获取 |
| `core/memory_manager.py` | 对话记忆存储（按窗口分文件） |

### 当前问题
- 消息处理是同步的，收到消息后直接处理并回复
- 没有中间存储层，无法支持延迟回复、人工确认等功能
- 消息与回复之间没有显式的对应关系
- 多个任务同时操作微信界面会导致操作混乱

## 解决方案设计

### 新增模块：`core/message_store.py`

#### 核心数据结构

```python
class MessageRecord:
    """消息记录对象"""
    def __init__(self):
        self.id = str(uuid.uuid4())        # 唯一标识
        self.chat_name = ""                # 会话名称（备注名）
        self.sender = ""                   # 发送者
        self.content = ""                  # 消息内容
        self.msg_type = ""                 # 消息类型（text/image/unknown）
        self.msg_attr = ""                 # 消息属性（friend/group/self/system）
        self.seq = 0                       # Chatlog 消息序号
        self.receive_time = ""             # 接收时间
        self.status = "pending"            # 状态：pending/processed/replied/confirmed
        self.reply_id = None               # 关联的回复 ID（回复对应关系）
        self.reply_content = ""            # 回复内容
        self.reply_time = ""               # 回复时间
        self.needs_confirm = False         # 是否需要确认
        self.confirm_status = "pending"    # 确认状态：pending/confirmed/rejected
```

#### 存储结构

```
config/message_store/
├── {wx_id}/
│   ├── {chat_name}_messages.json    # 按会话存储消息记录
│   └── pending_confirm.json          # 待确认消息队列
```

#### 核心方法

| 方法 | 功能 |
|------|------|
| `save_message()` | 保存消息记录 |
| `get_message()` | 根据 ID 获取消息 |
| `get_pending_messages()` | 获取待处理消息 |
| `get_unread_messages()` | 获取未读消息 |
| `set_message_status()` | 设置消息状态 |
| `set_unread()` | 设置消息为未读 |
| `add_pending_confirm()` | 添加待确认消息 |
| `confirm_message()` | 确认消息（同意回复） |
| `reject_message()` | 拒绝消息（不回复） |
| `bind_reply()` | 绑定消息与回复的对应关系 |
| `get_replied_messages()` | 获取已回复消息列表 |

### 新增模块：`core/wx_lock.py`

#### 核心数据结构

```python
class WXLock:
    """微信界面操作锁"""
    def __init__(self):
        self._lock = threading.Lock()           # 基础锁对象
        self._held = False                      # 是否被占用
        self._holder = None                     # 占用者标识
        self._hold_time = None                  # 占用开始时间
        self._lock_timeout = 300               # 锁超时时间（秒）
```

#### 核心方法

| 方法 | 功能 |
|------|------|
| `acquire()` | 获取锁（阻塞等待直到获取） |
| `release()` | 释放锁 |
| `try_acquire()` | 尝试获取锁（非阻塞，立即返回结果） |
| `is_held()` | 检查锁是否被占用 |
| `get_holder()` | 获取锁占用者 |
| `force_release()` | 强制释放锁（管理员操作） |
| `acquire_with_timeout()` | 获取锁（带超时时间） |

#### 使用方式

```python
# 在需要操作微信界面的代码前获取锁
if self.bot.wx_lock.acquire():
    try:
        # 执行微信界面操作
        self.bot.wx.SendMsg(msg=content, who=chat_name)
    finally:
        # 操作完成后释放锁
        self.bot.wx_lock.release()
```

### 新增模块：`core/wx_lock_decorator.py`（可选）

提供装饰器方式简化锁的使用：

```python
@wx_lock_decorator
def send_message(self, chat_name, content):
    """发送消息（自动获取和释放锁）"""
    return self.bot.wx.SendMsg(msg=content, who=chat_name)
```

### 新增配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `chat_reply_confirm_switch` | bool | False | 私聊回复确认开关 |
| `chat_reply_confirm_wait_timeout` | int | 300 | 确认等待超时时间（秒） |
| `message_store_max_count` | int | 1000 | 单会话最大存储消息数 |
| `wx_lock_enabled` | bool | True | 微信界面操作锁开关 |
| `wx_lock_timeout` | int | 300 | 锁自动超时时间（秒） |

### 修改现有模块

#### 1. 修改 `core/config_manager.py`
- 添加新配置项定义和同步逻辑

#### 2. 修改 `core/chatlog_manager.py`
- 在消息处理前调用 `MessageStore.save_message()`
- 在发送回复后调用 `MessageStore.bind_reply()`
- 支持私聊回复确认机制
- 添加微信界面操作锁

#### 3. 修改 `core/message_handler.py`
- 在 `wx_send_ai()` 和 `_chatlog_send_ai()` 中集成消息存储层
- 添加回复前确认检查
- 添加微信界面操作锁

#### 4. 修改 `core/command_handler.py`
- 添加 `/确认回复` 和 `/拒绝回复` 命令
- 添加 `/查看待确认` 命令
- 添加 `/占用微信锁` 和 `/释放微信锁` 命令
- 添加 `/查看微信锁状态` 命令

#### 5. 修改 `core/listen_manager.py`
- 在监听操作前获取微信界面操作锁

#### 6. 修改 `core/wx_utils.py`
- 在微信操作前获取微信界面操作锁

#### 7. 修改 `wxbot_core.py`
- 初始化 `MessageStore` 实例
- 初始化 `WXLock` 实例

### 新的消息处理流程

```
消息监听 → MessageStore.save_message() → 判断是否需要确认
    ├─ 无需确认 → MessageHandler → AI API → 发送消息 → MessageStore.bind_reply()
    └─ 需要确认 → MessageStore.add_pending_confirm() → 等待确认
                      ├─ 确认 → MessageHandler → AI API → 发送消息 → bind_reply()
                      └─ 拒绝 → 设置状态为 rejected
```

## 实施步骤

### 阶段一：创建消息存储模块

**文件**: `core/message_store.py`

1. 实现 `MessageRecord` 类（数据模型）
2. 实现 `MessageStore` 类（存储管理）
3. 实现文件持久化逻辑（JSON 文件存储）
4. 实现线程安全锁机制

### 阶段二：创建微信界面操作锁模块

**文件**: `core/wx_lock.py`

1. 实现 `WXLock` 类（锁管理）
2. 实现 `acquire()`、`release()`、`try_acquire()` 方法
3. 实现 `force_release()` 强制释放方法
4. 实现锁超时检测机制
5. 实现锁状态查询方法

### 阶段三：修改配置管理

**文件**: `core/config_manager.py`

1. 在 `__init__` 中添加新配置属性（含微信锁配置）
2. 在 `create_new_config_file()` 中添加默认值
3. 在 `update_global_config()` 中添加配置同步逻辑

### 阶段四：集成消息存储到消息处理流程

**文件**: `core/message_handler.py`

1. 修改 `wx_send_ai()` 添加消息存储逻辑和微信锁
2. 修改 `_chatlog_send_ai()` 添加消息存储逻辑和微信锁
3. 添加回复确认检查逻辑

### 阶段五：集成到 Chatlog 监听流程

**文件**: `core/chatlog_manager.py`

1. 在 `chatlog_process_message()` 中集成消息存储和微信锁
2. 添加私聊回复确认支持

### 阶段六：集成微信锁到监听管理器

**文件**: `core/listen_manager.py`

1. 在 `listen_mode()` 中添加微信锁获取/释放
2. 在 `ALLListen_mode()` 中添加微信锁获取/释放
3. 在 `next_message_handle()` 中添加微信锁获取/释放

### 阶段七：集成微信锁到微信工具模块

**文件**: `core/wx_utils.py`

1. 在 `send_group_welcome_msg()` 中添加微信锁
2. 在 `Pass_New_Friends()` 中添加微信锁
3. 在 `send_scheduled_msg()` 中添加微信锁
4. 在 `send_scheduled_moments()` 中添加微信锁
5. 在 `_do_moments_like()` 中添加微信锁

### 阶段八：添加管理命令

**文件**: `core/command_handler.py`

1. 添加 `/确认回复` 命令（支持指定消息 ID）
2. 添加 `/拒绝回复` 命令（支持指定消息 ID）
3. 添加 `/查看待确认` 命令（列出待确认消息）
4. 添加 `/查看未读消息` 命令
5. 添加 `/占用微信锁` 命令（手动占用）
6. 添加 `/释放微信锁` 命令（手动释放）
7. 添加 `/查看微信锁状态` 命令（查看锁状态）

### 阶段九：初始化消息存储和微信锁

**文件**: `wxbot_core.py`

1. 在 `WXBot.__init__` 中初始化 `MessageStore`
2. 在 `WXBot.__init__` 中初始化 `WXLock`
3. 在 `get_status()` 中添加待确认消息数量统计和锁状态

## 风险与注意事项

### 风险点
1. **性能影响**：新增存储层可能影响消息处理速度
   - 缓解措施：使用异步写入、批量处理
2. **数据一致性**：消息存储与回复绑定的原子性
   - 缓解措施：使用事务性写入（先写临时文件再替换）
3. **存储容量**：大量消息可能导致存储文件过大
   - 缓解措施：配置最大存储数量、自动清理旧消息
4. **死锁风险**：微信界面操作锁可能导致死锁
   - 缓解措施：实现锁超时机制、强制释放功能、避免嵌套锁
5. **锁饥饿**：某些任务可能长时间无法获取锁
   - 缓解措施：实现公平锁机制、锁优先级、超时重试
6. **性能瓶颈**：锁竞争可能成为性能瓶颈
   - 缓解措施：最小化锁持有时间、批量操作、锁粒度优化

### 注意事项
1. 所有新增文件必须放在 `core/` 目录
2. 遵循项目现有的代码风格和命名约定
3. 保持向后兼容性，不影响现有功能
4. 添加函数级注释
5. 确保所有微信界面操作都通过锁机制进行
6. 锁获取失败时应延迟重试而非直接丢弃

## 验证方案

### 功能验证
1. **消息存储验证**：发送测试消息后检查存储文件是否生成
2. **未读设置验证**：通过命令设置消息未读状态
3. **回复确认验证**：开启确认开关后，发送消息应进入待确认队列
4. **回复对应验证**：查看消息记录中的回复关联关系
5. **微信锁验证**：验证锁机制正常工作，避免并发操作混乱
6. **锁手动控制验证**：通过命令手动占用和释放锁
7. **锁超时验证**：验证锁超时自动释放功能

### 测试用例
1. 开启私聊回复确认，发送消息后验证进入待确认队列
2. 使用 `/确认回复` 命令确认后验证自动回复
3. 使用 `/拒绝回复` 命令拒绝后验证不回复
4. 使用 `/查看待确认` 命令验证列表显示
5. 使用 `/查看未读消息` 命令验证未读消息显示
6. 使用 `/占用微信锁` 命令占用锁后，发送消息验证延迟执行
7. 使用 `/释放微信锁` 命令释放锁后，验证消息正常回复
8. 使用 `/查看微信锁状态` 命令验证锁状态显示
9. 测试并发消息场景，验证锁机制避免操作混乱
10. 测试锁超时场景，验证超时后自动释放

## 完成标准

1. ✅ 新建 `core/message_store.py` 文件
2. ✅ 新建 `core/wx_lock.py` 文件
3. ✅ 修改 `core/config_manager.py` 添加配置项
4. ✅ 修改 `core/message_handler.py` 集成存储层和微信锁
5. ✅ 修改 `core/chatlog_manager.py` 集成存储层和微信锁
6. ✅ 修改 `core/listen_manager.py` 集成微信锁
7. ✅ 修改 `core/wx_utils.py` 集成微信锁
8. ✅ 修改 `core/command_handler.py` 添加管理命令
9. ✅ 修改 `wxbot_core.py` 初始化存储模块和微信锁
10. ✅ 所有文件语法检查通过
11. ✅ 功能验证通过
