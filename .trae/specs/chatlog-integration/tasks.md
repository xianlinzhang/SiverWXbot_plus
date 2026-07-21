# Tasks

- [ ] Task 1: 创建 ChatlogClient HTTP 客户端模块
  - [ ] SubTask 1.1: 新建 `chatlog_client.py`，定义 `ChatlogError` 异常类与 `ChatlogClient` 类
  - [ ] SubTask 1.2: 实现四个方法（默认使用 `format=json`）：
    - `get_session(has_unread=None, ignore_usernames=None)` → 返回 dict，含 `items` 列表（每项含 `userName`, `nickName`, `content`, `nTime`, `UnreadCount`）
    - `get_chatroom(keyword=None)` → 返回 dict，含 `items` 列表
    - `search_contact(keyword=None, is_friend=None)` → 返回 dict，含 `items` 列表（每项含 `userName`, `alias`, `remark`, `nickName`, `isFriend`）
    - `get_chatlog(talker, time=None, sender=None, keyword=None, limit=None, offset=None)` → 返回 list[dict]（每项含 `seq`, `time`, `talker`, `talkerName`, `isChatRoom`, `sender`, `senderName`, `isSelf`, `type`, `content`, `contents`）
  - [ ] SubTask 1.3: 实现统一的 `_request()` 封装，支持超时（`chatlog_request_timeout`，默认 5s）、重试（最多 2 次，间隔 0.5s）、错误降级（返回空结果或抛 `ChatlogError`）
  - [ ] SubTask 1.4: 添加 `health_check()` 方法，返回布尔值表示服务是否可达，供面板状态展示与监听启动前校验使用
  - [ ] SubTask 1.5: 为所有公开方法添加函数级注释（参数、返回值、异常）

- [ ] Task 2: 扩展 WXBotConfig 配置字段
  - [ ] SubTask 2.1: 在 `WXBotConfig.__init__()` 中新增 chatlog 相关默认字段：`chatlog_url='http://127.0.0.1:5030'`、`chatlog_listen_switch=False`、`chatlog_context_switch=False`、`chatlog_contact_lookup_switch=False`、`chatlog_polling_interval=3`、`chatlog_context_count=20`、`chatlog_request_timeout=5`
  - [ ] SubTask 2.2: 在 `create_new_config_file()` 的默认配置字典中加入上述字段
  - [ ] SubTask 2.3: 在 `update_global_config()` 中将 `self.config` 字典的 chatlog 字段映射到 `self.xxx` 属性，缺失时使用默认值
  - [ ] SubTask 2.4: 在配置保存接口（`save_config` 或等价方法）中将 chatlog 字段持久化到 `config.json`

- [ ] Task 3: 在 WXBot 中集成 ChatlogClient 实例
  - [ ] SubTask 3.1: 在 `WXBot.__init__()` 中新增 `self.chatlog_client = None`（延迟初始化）
  - [ ] SubTask 3.2: 新增 `_init_chatlog_client()` 方法，根据 `chatlog_url` 实例化 `ChatlogClient` 并执行 `health_check()`；失败时记录日志但不阻塞启动
  - [ ] SubTask 3.3: 在 `init_wx_listeners()` 末尾调用 `_init_chatlog_client()`；若 `chatlog_listen_switch=True` 但服务不可达，记录 ERROR 日志并自动回退到 UI 监听模式

- [ ] Task 4: 实现 Chatlog 轮询监听模式
  - [ ] SubTask 4.1: 新增 `self.chatlog_last_seq = {}` 字典，记录每个监听对象的最后处理消息序号（seq），替代时间戳作为去重依据
  - [ ] SubTask 4.2: 实现 `chatlog_listen_loop()` 方法：
    1. 先调用 `get_session()` 获取所有会话，筛选出 `UnreadCount > 0` 的会话（未读预过滤）
    2. 对每个有未读消息的监听对象（白名单/黑名单逻辑与 `process_message` 中 `is_monitored` 一致）调用 `get_chatlog(talker, limit=50)`
    3. 使用 `seq` 过滤出大于本地 `last_seq` 的消息，避免重复处理
    4. 首次启动时初始化 `last_seq` 为当前最大 seq，避免回放历史
  - [ ] SubTask 4.3: 将 Chatlog 消息 dict 转换为与 `wxautox4` 兼容的轻量消息对象（`types.SimpleNamespace`），映射规则：
    - `type`：`1` → `'text'`，`3` → `'image'`，其他 → `'unknown'`
    - `attr`：`isSelf=True` → `'self'`，`isChatRoom=True` → `'group'`，其他 → `'friend'`
    - `sender`：优先使用 `senderName`，为空时使用 `sender`（wxid）
    - `content`：文本消息直接使用；图片消息使用 `contents.md5` 作为标识；语音消息暂不处理
    - `id`：使用 `seq` 字段
  - [ ] SubTask 4.4: 对每条新消息调用 `process_message(chat, msg)`，其中 `chat` 通过 `self._get_verified_subwindow(talker)` 获取（必要时调用 `AddListenChat` 注册，但回调内跳过处理）
  - [ ] SubTask 4.5: 处理完成后更新 `chatlog_last_seq[talker]` 为本批消息的最大 seq；首批以 `datetime.now()` 为基准，避免回放历史
  - [ ] SubTask 4.6: 在 `message_handle_callback()` 开头新增判断：`if self.config.chatlog_listen_switch: return`，避免 UI 回调与 Chatlog 轮询重复处理

- [ ] Task 5: 修改 WXBot.main() 主循环
  - [ ] SubTask 5.1: 在主循环消息源选择处新增分支：`if self.config.chatlog_listen_switch: self.chatlog_listen_loop()`，并跳过 `listen_mode()` / `ALLListen_mode()`
  - [ ] SubTask 5.2: 轮询节流：使用 `time.sleep(wait_time)` 控制循环频率，`wait_time` 在 Chatlog 模式下取 `max(1, chatlog_polling_interval)`，其他模式维持 3 秒
  - [ ] SubTask 5.3: 异常处理：Chatlog 调用失败时记录日志并继续下一轮，不中断主循环

- [ ] Task 6: 实现 AI 上下文增强
  - [ ] SubTask 6.1: 新增 `_build_chatlog_history(chat_name, count)` 方法：调用 `chatlog_client.get_chatlog(talker=chat_name, limit=count)`，将结果转换为 `MemoryManager` 兼容的 entry 格式（`time`/`type`/`attr`/`sender`/`content`）
  - [ ] SubTask 6.2: 新增 `_merge_history(chatlog_history, memory_history, max_count)` 方法：按 `time` 去重（`time`+`content` 哈希）、按时间升序排序、截断至 `max_count` 条
  - [ ] SubTask 6.3: 在 `process_message()` 调用 `api.chat()` 前新增逻辑：`if self.config.chatlog_context_switch and self.chatlog_client:` 则用合并后的 history 替换原 history；失败时降级为仅 MemoryManager
  - [ ] SubTask 6.4: 对群聊场景同样应用上下文增强（在群聊 AI 调用分支中复用同一逻辑）

- [ ] Task 7: 实现联系人查询增强
  - [ ] SubTask 7.1: 在 `init_wx_listeners()` 中新增分支：`if self.config.chatlog_contact_lookup_switch and self.chatlog_client:` 则在添加监听前调用 `chatlog_client.search_contact(keyword=nickname)` 校验对象存在性
  - [ ] SubTask 7.2: 校验失败的对象记录 WARNING 日志并跳过 UI 注册；校验成功的对象正常进入 UI 监听注册流程
  - [ ] SubTask 7.3: 缓存 wxid 与昵称的映射到 `self.chatlog_contact_map`，供后续 Chatlog 查询使用（`talker` 参数优先使用 wxid）

- [ ] Task 8: Web 面板配置与状态集成
  - [ ] SubTask 8.1: 在 `web_server.py` 新增 `GET/POST /api/chatlog/config` 接口，读取/保存 chatlog 配置字段
  - [ ] SubTask 8.2: 在 `web_server.py` 新增 `GET /api/chatlog/status` 接口，返回 Chatlog 服务连接状态（调用 `chatlog_client.health_check()`）
  - [ ] SubTask 8.3: 在 `WXBot.get_status()` 返回字典中新增 `chatlog_listen_switch`、`chatlog_context_switch`、`chatlog_connected` 字段
  - [ ] SubTask 8.4: 在 `templates/dashboard.html` 状态区新增 Chatlog 连接状态徽标；在配置区新增 Chatlog 配置卡片（URL 输入框、三个开关、轮询间隔、上下文条数），保存按钮调用 `/api/chatlog/config`
  - [ ] SubTask 8.5: 配置保存后通过 `WXBot.reload_config()` 或等价机制热更新（参考现有 API 配置热更新逻辑）

- [ ] Task 9: 端到端测试与文档
  - [ ] SubTask 9.1: 编写 `demo_chatlog.py` 演示脚本，验证 ChatlogClient 四个接口可用
  - [ ] SubTask 9.2: 手动验证：启动 Chatlog 服务 + SiverWXbot_plus，开启 `chatlog_listen_switch`，向微信发送消息确认能被处理并自动回复
  - [ ] SubTask 9.3: 手动验证：开启 `chatlog_context_switch`，确认 AI 回复时使用了 Chatlog 历史上下文（通过日志观察）
  - [ ] SubTask 9.4: 手动验证：关闭 Chatlog 服务，确认主循环不崩溃、自动降级到 UI 监听（若 `chatlog_listen_switch` 开启但服务不可达则记录 ERROR 并退出监听）
  - [ ] SubTask 9.5: 在 `docs/docs.md` 中追加 Chatlog 集成说明章节（部署要求、配置项、常见问题）

# Task Dependencies
- Task 2 依赖 Task 1（配置字段引用 ChatlogClient 默认值）
- Task 3 依赖 Task 1 与 Task 2
- Task 4 依赖 Task 3
- Task 5 依赖 Task 4
- Task 6 依赖 Task 3（可与 Task 4/5 并行）
- Task 7 依赖 Task 3（可与 Task 4/5/6 并行）
- Task 8 依赖 Task 2、Task 3
- Task 9 依赖 Task 1~8 全部完成
