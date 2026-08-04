# 🛠️ Siver WX机器人技术文档

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        微信客户端 (wxautox4)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │  wx.py   │  │moment.py │  │ msgs/    │  │  ui/     │            │
│  │ 主接口   │  │朋友圈    │  │ 消息解析  │  │UI控件    │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        机器人核心层 (wxbot_core.py)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │配置管理  │  │ AI接口   │  │消息处理  │  │任务调度  │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  core/模块    │    │  core/模块    │    │  core/模块    │
│               │    │               │    │               │
│ config_manager│    │ message_store │    │  task_queue   │
│ redis_manager │    │ chatlog_mgr   │    │ command_hdlr  │
│ memory_mgr    │    │ message_hdlr  │    │    utils      │
└───────────────┘    └───────────────┘    └───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        数据存储层                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │  Redis   │  │ memory/  │  │ message_ │  │ fallback │            │
│  │(优先)    │  │对话记忆  │  │ store/   │  │_redis    │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Web 管理界面 (web_server.py)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ 登录认证  │  │配置管理  │  │状态监控  │  │日志查看  │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## core 模块详解

### 1. AI 接口模块 (`core/ai_api.py`)

负责对接多种 AI 平台，统一接口规范。

**支持的 AI 平台：**

| 平台 | 配置要求 | 说明 |
|------|----------|------|
| **DusAPI** | Key、URL、模型 ID | 自定义 API 接口 |
| **OpenAI SDK** | Key、URL、模型 | OpenAI 兼容接口 |
| **Dify** | Key、URL、工作流 ID | Dify 工作流接口 |
| **Coze** | Key、bot_id | 豆包智能体接口 |

**核心方法：**

```python
def chat(self, message, model=None, stream=False, prompt=None, history=None,
         image_path: str = "", image_url: str = ""):
    """
    调用 AI 接口获取回复。
    
    :param message: 用户输入的消息内容
    :param model: 指定模型，为 None 时使用当前默认模型
    :param stream: 是否使用流式输出
    :param prompt: 系统提示词，为 None 时使用配置中的 prompt
    :param history: 历史消息列表
    :param image_path: 本地图片路径，优先于 image_url
    :param image_url: 图片 URL
    :return: AI 回复的文本字符串
    """
```

**群组专属接口缓存：**
- 通过 `api_cache` 缓存群组专属接口实例，按 `api_index` 区分
- 支持为不同群组配置不同的 AI 接口

---

### 2. Chatlog 管理模块 (`core/chatlog_manager.py`)

通过 Chatlog API 获取消息的监听模式，相比界面监听更加稳定。

**核心功能：**

| 功能 | 说明 |
|------|------|
| **消息监听** | 通过 Chatlog API 轮询获取新消息 |
| **上下文增强** | 自动拉取历史消息增强 AI 回复上下文 |
| **联系人缓存** | 使用 Redis 缓存联系人数据，提升查询效率 |
| **消息去重** | 基于 `seq` 字段去重，避免重复处理 |

**配置参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `chatlog_listen_switch` | False | 是否启用 Chatlog 监听 |
| `chatlog_url` | `http://127.0.0.1:5030` | Chatlog 服务地址 |
| `chatlog_polling_interval` | 3 | 轮询间隔（秒） |
| `chatlog_request_timeout` | 5 | 请求超时（秒） |
| `chatlog_context_switch` | False | 是否启用上下文增强 |
| `chatlog_context_count` | 20 | 上下文消息条数 |
| `chatlog_reply_delay` | 60 | 消息回复延迟（秒） |
| `chatlog_contact_lookup_switch` | False | 是否启用联系人查询 |
| `chatlog_message_auto_refresh` | True | 是否自动刷新消息 |
| `chatlog_message_refresh_days` | 30 | 消息刷新拉取天数 |
| `chatlog_message_refresh_limit` | 500 | 消息刷新拉取条数上限 |

**核心方法：**

```python
def __init__(self, bot):
    """初始化 Chatlog 管理器"""

def _init_chatlog_client(self):
    """初始化 Chatlog 客户端（若配置开启）"""

def refresh_chatlog_contacts(self):
    """刷新联系人数据"""

def _load_contacts_from_redis(self):
    """从 Redis 加载联系人缓存数据"""
```

---

### 3. 配置管理模块 (`core/config_manager.py`)

负责配置文件的加载、保存、刷新和热重载。

**配置文件结构：**

```
config/
├── config.json      # 主配置（监听列表、AI接口、Prompt等）
├── admin.json       # 管理面板账号密码
├── email.txt        # 邮件告警配置
├── webhook.json     # Webhook 配置
├── panel_secret.key # 面板会话密钥
├── reply_count.json # 回复计数存储
├── fallback_redis.json # Redis 降级存储
├── message_store/   # 消息存储目录
└── prompt/          # Prompt 文件目录
    └── 默认.md      # 默认 Prompt
```

**核心配置字段：**

| 配置分类 | 主要字段 |
|----------|----------|
| **全局监听** | `AllListen_switch`, `chat_listen_only` |
| **AI 接口** | `api_configs`, `api_index`, `prompt`, `AtMe` |
| **群聊配置** | `group`, `group_api_map`, `group_switch`, `group_welcome` |
| **新好友** | `new_friend_switch`, `new_friend_reply_switch`, `new_friend_msg` |
| **关键词** | `chat_keyword_switch`, `group_keyword_switch`, `keyword_dict` |
| **自定义转发** | `custom_forward_switch`, `custom_forward_list` |
| **多 Prompt** | `default_prompt`, `chat_prompt_map`, `group_prompt_map` |
| **定时任务** | `scheduled_msg_switch`, `scheduled_moments_switch` |
| **同城信息消费** | `deal_queue_consumer_switch`, `deal_queue_redis_host`, `deal_queue_poll_interval`, `deal_queue_pending_max`, `deal_queue_auto_approve_switch`, `deal_queue_auto_approve_delay`, `deal_queue_publish_interval_min`, `deal_queue_publish_interval_max` |
| **对话记忆** | `memory_switch`, `memory_max_count`, `memory_context_count` |
| **发送延迟** | `reply_delay_switch`, `reply_delay_min`, `reply_delay_max` |
| **Chatlog** | `chatlog_listen_switch`, `chatlog_url`, `chatlog_polling_interval` |
| **Redis** | `redis_enabled`, `redis_host`, `redis_port`, `redis_fallback` |
| **任务队列** | `task_queue_enabled`, `task_queue_max_pending`, `task_queue_max_retries` |

**核心方法：**

```python
def __init__(self):
    """初始化配置管理器，加载默认配置"""

def load_config(self):
    """从 config.json 加载配置到 self.config 字典"""

def save_config(self):
    """将当前 self.config 字典持久化写回 config.json"""

def refresh_config(self):
    """重新加载配置文件，并将最新值同步到所有属性"""

def create_new_config_file(self):
    """若配置文件不存在，则创建一份包含默认值的配置文件"""
```

**配置热重载机制：**
- 支持在运行时修改配置并立即生效
- 通过 `/更新配置` 命令或面板保存触发
- 自动同步到内存中的配置对象

---

### 4. 消息处理模块 (`core/message_handler.py`)

负责处理微信消息的接收、分发、AI 回复等核心逻辑。

**消息处理流程：**

```
1. 接收消息
    ↓
2. 消息类型判断（文本/图片/文件/系统消息）
    ↓
3. 过滤检查（是否在监听列表、是否被忽略）
    ↓
4. 命令识别（是否为管理命令）
    ↓
5. AI 回复生成（构造 Prompt、调用接口、拆分回复）
    ↓
6. 消息发送（单条/多条、带延迟）
```

**核心方法：**

```python
def __init__(self, bot):
    """初始化消息处理器"""

def _get_chat_api(self, user_name):
    """获取私聊用户对应的 AI 接口实例"""

def _get_group_api(self, group_name):
    """获取群组对应的 AI 接口实例"""

def _get_chat_prompt(self, user_name):
    """获取私聊用户对应的 prompt 内容"""

def _get_group_prompt(self, group_name):
    """获取群组对应的 prompt 内容"""

def _build_split_prompt(self, base_prompt, max_chars, max_count):
    """将拆分格式要求注入到 prompt 前面"""

def _parse_split_reply(self, reply, max_count):
    """按 ||SPLIT|| 分隔符解析回复"""

def _clean_reply_for_send(self, reply):
    """按配置清洗即将发送给用户的 AI 回复"""
```

**消息过滤规则：**
- 黑名单用户消息直接忽略
- 白名单模式下只处理监听列表中的用户/群组
- 关键词触发模式下只处理包含关键词的消息

---

### 5. 消息存储模块 (`core/message_store.py`)

用于持久化存储消息记录，支持 Redis 和本地文件两种存储方式。

**存储结构：**

```
config/message_store/
└── {wx_id}/
    └── {chat_name}/
        └── {chat_name}_messages.json
```

**消息记录格式（MessageRecord）：**

```python
class MessageRecord:
    id = ""                  # 唯一标识（UUID）
    chat_name = ""           # 会话名称（备注名）
    sender = ""              # 发送者
    content = ""             # 消息内容
    msg_type = ""            # 消息类型（text/image/unknown）
    msg_attr = ""            # 消息属性（friend/group/self/system）
    seq = 0                  # Chatlog 消息序号
    receive_time = ""        # 接收时间
    status = "pending"       # 状态：pending/processed/replied/confirmed/rejected
    reply_id = None          # 关联的回复 ID
    reply_content = ""       # 回复内容
    reply_time = ""          # 回复时间
    needs_confirm = False    # 是否需要确认
    confirm_status = "pending" # 确认状态
    unread = False           # 是否未读
```

**核心方法：**

```python
def __init__(self, wx_id, config=None, base_path=None, bot=None):
    """初始化消息存储管理器"""

def save_message(self, chat_name, sender, content, msg_type, msg_attr, seq, message_time=None):
    """保存一条消息记录"""

def get_history(self, chat_name, count):
    """获取最近 count 条历史消息"""

def clear_messages(self, chat_name):
    """清空指定会话的消息记录"""

def clear_all_messages(self):
    """清空所有会话的消息记录"""
```

**去重机制：**
- 基于 `seq` 字段进行去重
- 同一 `seq` 的消息只存储一次
- 存储时自动清理过期消息，保持单会话最大存储数

---

### 6. Redis 管理模块 (`core/redis_manager.py`)

Redis 管理类，提供统一的 Redis 操作接口，支持自动降级到本地文件存储。

**构造函数：**

```python
def __init__(self, config):
    """
    初始化 Redis 管理器
    
    :param config: 配置对象，支持属性访问或字典访问
                   包含 host, port, db, password, timeout, retry_count, fallback, fallback_path
    """
```

**降级机制：**

```
Redis 可用 → 使用 Redis 存储
    ↓ (连接失败/库未安装)
自动降级 → 使用本地文件存储 (fallback_redis.json)
    ↓ (恢复连接)
自动切换 → 重新使用 Redis 存储
```

**支持的操作：**

| 操作 | Redis 方法 | 文件存储方法 |
|------|------------|--------------|
| 设置值 | `set()` | JSON 文件写入 |
| 获取值 | `get()` | JSON 文件读取 |
| 删除值 | `delete()` | JSON 文件删除 |
| 列表追加 | `lpush()` | 列表追加 |
| 列表弹出 | `rpop()` | 列表弹出 |
| 哈希设置 | `hset()` | 嵌套字典写入 |
| 哈希获取 | `hget()` | 嵌套字典读取 |
| 哈希获取全部 | `hgetall()` | 返回整个字典 |

**核心方法：**

```python
def _init_client(self) -> None:
    """初始化 Redis 客户端"""

def _test_connection(self) -> bool:
    """测试 Redis 连接"""

def _handle_connection_failure(self) -> None:
    """处理连接失败，降级到本地存储"""

def _load_fallback_data(self) -> None:
    """加载降级存储文件"""

def _save_fallback_data(self) -> None:
    """保存降级存储文件"""

def is_available(self) -> bool:
    """检查 Redis 是否可用"""
```

---

### 7. 任务队列模块 (`core/task_queue.py`)

任务队列管理，用于异步执行发送消息、发送朋友圈、点赞朋友圈等操作。

**支持的任务类型：**

| 任务类型 | 说明 | 参数 |
|----------|------|------|
| `send_msg` | 发送消息 | `chat_name`, `content`, `is_file` |
| `send_moments` | 发送朋友圈 | `content`, `images`, `privacy` |
| `like_moments` | 点赞朋友圈 | - |
| `pass_friend` | 通过好友请求 | `friend_name`, `welcome_msg` |
| `send_file` | 发送文件 | `chat_name`, `file_path` |

**任务数据结构（WXTask）：**

```python
@dataclass
class WXTask:
    id: str                    # 任务 ID
    type: str                  # 任务类型
    priority: int              # 优先级
    status: str                # 状态
    params: Dict[str, Any]     # 任务参数
    result: Optional[Any]      # 执行结果
    error: Optional[str]       # 错误信息
    create_time: Optional[str] # 创建时间
    start_time: Optional[str]  # 开始时间
    end_time: Optional[str]    # 结束时间
    callback: Optional[Callable] # 回调函数
```

**队列结构：**

```
任务队列（待执行）→ 执行中 → 历史记录（成功/失败）
```

**核心方法：**

```python
def __init__(self, bot):
    """
    初始化任务队列
    
    :param bot: 机器人实例
    """

def _start_worker(self) -> None:
    """启动工作线程"""

def stop(self) -> None:
    """停止任务队列"""

def add_task(self, task_type, **kwargs) -> str:
    """添加任务到队列，返回任务 ID"""

def execute_task(self, task) -> None:
    """执行单个任务"""

def get_task_status(self, task_id) -> Optional[Dict]:
    """获取任务状态"""

def get_pending_tasks(self) -> List[Dict]:
    """获取待执行任务列表"""

def get_history_tasks(self, limit=50) -> List[Dict]:
    """获取历史任务记录"""
```

**配置参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `task_queue_enabled` | True | 是否启用任务队列 |
| `task_queue_max_pending` | 1000 | 最大待执行任务数 |
| `task_queue_history_limit` | 500 | 历史记录保留条数 |
| `task_queue_max_retries` | 3 | 任务最大重试次数（0=不重试） |
| `task_queue_retry_interval` | 30 | 首次重试间隔（秒） |
| `task_queue_retry_factor` | 2 | 重试间隔递增倍数（指数退避） |

---

### 8. 记忆管理模块 (`core/memory_manager.py`)

管理对话记忆，AI 回复时携带历史上下文。采用代理模式，所有存储操作委托给 MessageStore。

**构造函数：**

```python
def __init__(self, message_store):
    """
    初始化记忆管理器（代理模式）
    
    :param message_store: MessageStore 实例，所有存储操作委托给它
    """
```

**核心方法：**

```python
def get_messages(self, chat_name, count):
    """
    获取最近 count 条记忆，返回 AI 兼容格式的消息历史
    
    :param chat_name: 会话名称
    :param count: 返回消息数量
    :return: 消息历史列表，格式：[{"time": "xxx", "type": "xxx", "attr": "xxx", "sender": "xxx", "content": "xxx"}]
    """

def save_message(self, chat_name, sender, content, msg_type, msg_attr, max_count, message_time=None):
    """保存一条消息到记忆存储"""

def clear_messages(self, chat_name):
    """清空指定会话的对话记忆"""

def clear_all_messages(self):
    """清空所有会话的对话记忆"""
```

**记忆清理机制：**
- 窗口名含非法字符时自动清理
- 清理后为空时使用 hash 前缀目录存储
- 目录下生成 `name.json` 记录原始窗口名

---

### 9. 命令处理模块 (`core/command_handler.py`)

处理管理员通过微信消息发送的管理命令。

**命令分类：**

| 分类 | 命令示例 | 说明 |
|------|----------|------|
| **系统状态** | `/指令`, `/当前版本`, `/更新配置` | 查看系统状态和版本 |
| **用户管理** | `/添加用户`, `/删除用户`, `/当前用户` | 管理监听用户 |
| **群组管理** | `/添加群`, `/删除群`, `/群机器人状态` | 管理监听群组 |
| **Prompt 管理** | `/当前AI设定`, `/更改AI设定为` | 管理 Prompt |
| **接口管理** | `/查看接口列表`, `/选择接口` | 管理 AI 接口 |

**核心方法：**

```python
def __init__(self, bot):
    """初始化命令处理器"""

def process_command(self, chat, message):
    """
    解析并分发管理员指令。
    
    :param chat: 管理员聊天窗口子对象
    :param message: 消息对象
    :return: 操作结果
    """

def send_command_list(self, chat):
    """发送命令列表帮助信息"""
```

---

### 10. 监听管理模块 (`core/listen_manager.py`)

管理微信消息监听模式（白名单/黑名单/全局监听）及相关操作。

**监听模式：**

| 模式 | 说明 |
|------|------|
| **白名单模式** (`listen_mode`) | 只监听指定的用户和群组 |
| **黑名单模式** (`ALLListen_mode`) | 监听所有用户，排除黑名单 |
| **Chatlog 模式** | 通过 Chatlog API 获取消息 |

**核心方法：**

```python
def __init__(self, bot):
    """初始化监听管理器"""

def listen_mode(self):
    """普通监听模式（白名单模式）：获取所有监听窗口的最新消息并逐一处理"""

def ALLListen_mode(self, last_time, timeout=10):
    """
    全局监听模式主函数（黑名单模式）。
    
    :param last_time: 上次执行超时检测的时间戳
    :param timeout: 超时检测间隔（秒），默认 10 秒
    :return: 更新后的 last_time
    """
```

---

### 11. 工具函数模块 (`core/utils.py`)

提供通用工具函数。

**主要工具函数：**

| 函数 | 说明 |
|------|------|
| `clean_text(text)` | 清理文本中的非法字符 |
| `split_long_text(text, max_length)` | 按最大长度拆分文本 |
| `now_time()` | 获取当前时间字符串 |
| `human_delay(min_delay, max_delay)` | 模拟人工操作延迟 |
| `get_run_time(start_time)` | 获取运行时间字符串 |
| `_normalize_chat_max_round_map(value)` | 标准化回复轮数映射 |
| `_coerce_int_range(value, min_val, max_val)` | 将值限制在整数范围内 |

---

## 消息流程

### 传统界面监听模式

```
微信客户端 → wxautox4 消息回调 → ListenManager.listen_mode() → WXBot.process_message()
                                                                     ↓
                                                            MessageHandler 处理消息
                                                                     ↓
                                                            命令识别 / AI 回复
                                                                     ↓
                                                            消息发送
```

### Chatlog 监听模式

```
微信客户端 → Chatlog 服务 → ChatlogManager.listen() → WXBot.process_message()
                                                          ↓
                                                    MessageHandler 处理消息
                                                          ↓
                                                    上下文增强
                                                          ↓
                                                    命令识别 / AI 回复
                                                          ↓
                                                    消息发送
```

---

## 任务执行流程

```
用户操作 / 定时任务 → TaskQueue.add_task() → Redis/文件队列
                                                   ↓
                                              工作线程轮询
                                                   ↓
                                              TaskQueue.execute_task()
                                                   ↓
                                              微信客户端执行操作
                                                   ↓
                                              更新任务状态到历史记录
```

---

## 数据存储策略

### 优先级策略

1. **Redis 优先**：配置了 Redis 且可用时，使用 Redis 存储
2. **文件降级**：Redis 不可用或未配置时，自动降级到本地文件存储
3. **独立目录**：不同 wx 号的数据存储在独立目录，避免冲突

### 存储内容

| 存储项 | 存储位置 |
|--------|----------|
| 消息记录 | `config/message_store/` 或 Redis |
| 对话记忆 | `memory/`（通过 MessageStore） |
| 任务队列 | Redis 或 `fallback_redis.json` |
| 回复计数 | `config/reply_count.json` |
| 配置文件 | `config/` |

---

## 远程访问服务架构

```
用户浏览器 → SiverPanel 服务器 → 远程隧道 → 本地面板 (web_server.py)
                                              ↓
                                         微信机器人核心
```

**安全机制：**
- 安全入口验证（5-32位，仅小写字母、数字、连字符）
- 面板账号密码认证
- HTTPS 加密传输

---

## 扩展开发指南

### 添加新的 AI 接口

1. 在 `core/ai_api.py` 中创建新的 API 类，继承基础接口类
2. 实现 `chat()` 方法
3. 在 `WXBot._init_api()` 中注册新的接口类型
4. 在管理面板中添加对应的配置项

### 添加新的任务类型

1. 在 `core/task_queue.py` 的 `TASK_TYPES` 中添加新类型
2. 在 `_task_handlers` 中添加对应的处理方法
3. 实现 `_handle_xxx()` 方法
4. 在管理面板中添加对应的触发界面

### 添加新的管理命令

1. 在 `core/command_handler.py` 的 `process_command()` 中添加命令分支
2. 实现对应的处理方法
3. 在命令分类目录中添加说明

---

## 性能优化建议

1. **启用 Redis**：Redis 存储相比文件存储有显著性能提升
2. **合理配置记忆条数**：记忆条数过多会增加 token 消耗，建议单会话 1000-3000 条
3. **启用消息回复延迟**：避免消息尚未完全接收就开始处理
4. **配置拆分多条回复**：减少大消息的处理时间，提升响应速度
5. **启用任务队列**：异步执行操作，避免阻塞主进程

---

## 版本历史

| 版本 | 更新内容 |
|------|----------|
| V4.7.27 | 优化远程访问、关闭SESSION_COOKIE_HTTPONLY方便内外网访问、优化面板接口测试 |
