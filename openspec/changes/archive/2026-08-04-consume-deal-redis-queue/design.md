## Context

见 proposal.md - Why。消费契约见 `we-mp-rss/docs/redis-deal-queue.md`：生产者 `LPUSH wemp:deal:push:queue`（FIFO，队尾取），回执 Hash `wemp:deal:push:status`（field=`{source}:{unique_id}:{push_date}`，value=`QUEUED`/`PUBLISHED`），失败不自动重推，人工补救 = `HDEL`（重推）/ `HSET PUBLISHED`（放弃）。消息为 JSON，含 `source` 与 ORM 全行字段。

本程序现状（相关约束）：
- `RedisManager` 支持任意 host/port/db/password 配置，但**无 `blpop`**，且默认 `fallback=True`（`core/redis_manager.py:33-43`）。
- bot 本地 Redis 在 `127.0.0.1:6379`；远程队列在 `122.51.49.63:6379 db0`（有密码，`fallback=False`）。
- `task_queue.submit(task_type, params, priority, callback)`，回调签名 `callback(success, result, params)`，params 被 JSON 序列化存 Redis（`core/task_queue.py:194-236, 439-448`）。
- `wx.SendMoments(text, images, privacy, tags)` → `Moment.Publish`（`wxautox4/wx.py:525-543`）。
- 面板已有"待确认"先例：`MessageStore.add_pending_confirm` + `blueprints/message.py` + `tab-messages`（List + Hash 详情 + stat-card 列表）。
- 蓝图注册在 `blueprints/__init__.py:build_blueprints()`；配置热重载靠 `config_manager.update_global_config` 逐键 `self.config.get` 同步；面板保存走 `coerce_*_fields`（save_config_route 只跑 bool/list/float/dict，int 区间在 config_manager 里 clamp）。
- 主循环每 3s 一轮；`stop_wxbot`（`wxbot_core.py:329`）统一停止各子系统。

## Goals / Non-Goals

**Goals:**
- 内嵌消费方，单微信账号，人工确认后发布，纯文本文案
- 严格满足契约回执语义：`PUBLISHED` 只在"真发出"后写入
- 待发布池持久化（bot 重启不丢）、四态状态机、容量上限
- 面板独立标签页，动作齐全（发布/丢弃/重推）

**Non-Goals:**
- 多账号 fan-out（单账号场景，不做消息分发）
- 图片发布（`images` URL 不下载，文案忽略图片字段）
- 消费失败自动重推（契约明确不自动重推，走人工补救）
- 修改生产者侧代码或队列键名

## Decisions

**D1. 消费方式：RPOP 轮询 daemon 线程，不用 BLPOP。**
契约给出 `BLPOP`（阻塞实时）/`RPOP`（轮询，适合人工逐步处理）两种。人工确认流程实时性要求低，`RedisManager` 也无 `blpop`（补它还得给 fallback 圆谎，本地 JSON 无法阻塞）。新开 daemon 线程照 `TaskQueue._start_worker` 的模式，每 `deal_queue_poll_interval` 秒 `RPOP` 一次。备选：塞主循环轮询（改动最小但队列量大时拖慢主循环，且与监听逻辑耦合）；独立脚本（两进程抢同一微信 UI，风险高，否决）。

**D2. 双 Redis：远程消费连接与本地待发布池分离。**
- 远程：消费者自建 `RedisManager(fallback=False)`（`_init_client` 失败即 `_is_available=False`，`_handle_connection_failure` 在 fallback=False 时只记 ERROR），专用于 `RPOP` 队列 + `HGET/HSET/HDEL` 回执。
- 本地：待发布池存 bot 自身 `redis_manager`（`127.0.0.1`），键空间与远程 `wemp:*` 天然隔离。
- 键位：
  - `wxbot:{wxid}:deal:pending` — LIST，元素为回执 field 字符串（队头最新）
  - `wxbot:{wxid}:deal:pending:{field}` — HASH：`{source, unique_id, push_date, field, text, status, updated_at}`
- 备选：待发布池放远程库——会污染生产者 db0，否决。

**D3. 回执时序：`PUBLISHED` 写在 send_moments 任务成功回调里。**
发布动作提交 `task_queue.submit('send_moments', {text, images:[], privacy, tags:[], _receipt_field: field}, callback=cb)`。`_handle_send_moments` 只读 text/images/privacy/tags，`_receipt_field` 作为透传字段随 params 序列化。`cb(success, result, params)`：
- success → 远程 `HSET status field PUBLISHED`，本地 `LREM` + `HDEL detail`
- fail → 本地 detail `status='failed'` 保留在池中（远程保持 `QUEUED`，task_queue 已重试 3 次进死信，任务队列标签页可恢复/丢弃）
发布动作前先 `HGET` 远程 field，若已 `PUBLISHED` 拒绝并提示（契约 §4 防并发重复发布）。

**D4. 四态状态机。**
`pending → publishing → published / failed`：
- 入池 `pending`；点发布提交任务前置 `publishing`；任务成功 `published`（移出列表）；任务最终失败 `failed`（留在列表，可再次点发布/丢弃/重推）。
- 面板渲染按状态打标签，失败可定位环节。

**D5. 待发布池容量上限。**
消费线程每次取消息前先 `LLEN wxbot:{wxid}:deal:pending`，达到 `deal_queue_pending_max` 则跳过本轮并 `log` 告警，避免人工长期不处理导致本地膨胀。上限 `int` 在 `config_manager` clamp（1~10000，默认 500）。

**D6. 渲染器：固定模板 + 可配前缀，忽略图片。**
- 顺风车：`【顺风车】{departure} → {destination}` + 时间/车型/人数/电话等非空行
- 招聘：`【招聘】{title}` + 类型/公司/地点/薪资/联系人/电话等非空行
- `deal_queue_moments_prefix` 置于文案开头；超长按 `deal_queue_moments_max_len`（默认 2000）截断。
- 备选：面板可视化编辑模板——超出本次范围，Non-Goals。

**D7. 生命周期：主循环 `check()` 按开关启停线程。**
`DealQueueConsumer(bot)` 在 `WXBot.__init__` 创建（不启动线程）。主循环每轮调 `self.deal_consumer.check()`（try/except 包裹）：开关开且线程未起 → `_start()`；开关关且线程在跑 → `_stop()`（daemon 线程，join timeout 5s）。`stop_wxbot` 加 `self.deal_consumer.stop()`。远程连接不可用时线程只记日志继续睡，不影响主循环。

**D8. 面板与蓝图。**
- 新 `blueprints/deal.py`（照 `blueprints/task.py` 的 `_require_bot` 模板）：`GET /api/deals`（列表+统计+远程 LLEN）、`POST /api/deals/publish`、`POST /api/deals/discard`、`POST /api/deals/re_push`。
- `blueprints/__init__.py:build_blueprints()` 注册 `deal.bp`。
- `dashboard.html`：侧边栏加 `data-tab="tab-deal"`；新 `config-panel#tab-deal`（配置卡 + stat-card + 待发布列表，照 `tab-messages` 结构）；`saveConfig` JS 收集 10 个新字段。

**D9. 配置面（10 项）。**
`config_manager.__init__` 声明默认值 + `update_global_config` 同步行（int 就地 clamp），`schema/coercers.py` 登记 `deal_queue_consumer_switch: 'bool'`，README/tech_doc 补表。
- `deal_queue_consumer_switch`(bool, False)
- `deal_queue_redis_host`(str, 122.51.49.63) / `_port`(int, 6379) / `_db`(int, 0) / `_password`(str, 空)
- `deal_queue_poll_interval`(int, 5, clamp 2~600)
- `deal_queue_privacy`(str, public)
- `deal_queue_moments_prefix`(str, 空)
- `deal_queue_moments_max_len`(int, 2000, clamp 100~2000)
- `deal_queue_pending_max`(int, 500, clamp 1~10000)
密码存 `config/config.json`（gitignore，与 API Key 同级）。

## Risks / Trade-offs

- [RPOP 后、写本地 pending 前崩溃 → 消息丢失，远程留 QUEUED] → 窗口毫秒级，可接受；契约 §5 人工补救（HDEL 重推）兜底。
- [回执 HSET 在任务成功后仍失败（远程瞬断）→ 已发布但远程留 QUEUED] → 记 ERROR 日志；生产者按 field 存在跳过不入队，不会重复推送；人工可用 HDEL 强制重推或 HSET 放弃。
- [发布失败进 task_queue 死信，用户再点发布会再生成任务，死信里残留旧任务] → 死信记录可恢复/丢弃（既有任务队列标签页），行为一致、无副作用。
- [文案超长被截断可能切掉联系电话] → 渲染顺序把电话放最后且模板内容短，实际命中概率低；`max_len` 可配。
- [远程密码明文存 config.json] → 与既有 API Key 同级处理，文件已 gitignore，无新增风险。

## Migration Plan

1. 先加配置项与面板骨架（开关默认 False），不启动消费者，不影响现有运行。
2. 落地 `core/deal_queue_consumer.py` + 主循环/stop 接入，开关置 True 前本地 `python` 单测渲染与回执逻辑（mock 远程 Redis）。
3. 生产验证：开启开关 → 面板看待发布入池 → 人工发布一条 → 核对远程回执变 `PUBLISHED`。
4. 回滚：关开关即停消费者线程；面板动作全部幂等，不产生脏数据。

## Open Questions

- 无。规格、方案、任务拆解均已收敛。
