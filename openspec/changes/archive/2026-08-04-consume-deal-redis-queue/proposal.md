## Why

`we-mp-rss` 每天把顺风车/招聘数据经 Redis 队列（`wemp:deal:push:queue`）推给外部微信朋友圈发布方，并约定回执协议（`wemp:deal:push:status` 的 QUEUED→PUBLISHED）。本程序拥有已登录的微信 + 现成的朋友圈发布与任务队列能力，应作为该消费方，把这些同城信息经人工确认后发布到朋友圈，并把回执回报给生产者。

## What Changes

- 新增 `core/deal_queue_consumer.py`：daemon 线程按配置间隔从远程队列 `RPOP` 消费消息，渲染为纯文本朋友圈文案，写入本地待发布池（bot 本地 Redis），等待人工确认。
- 新增面板「同城发布」标签页 + `blueprints/deal.py` 蓝图：展示待发布列表，提供**发布 / 丢弃 / 重推**三个动作。
  - **发布**：提交 `send_moments` 任务，成功回调里写远程回执 `PUBLISHED`（严格保证"真发出才回执"）。
  - **丢弃**：直接写远程回执 `PUBLISHED`（放弃发布，防重复入队）。
  - **重推**：`HDEL` 远程回执 field，生产者下次轮询会重新 LPUSH（不设本地去重，重推记录需再次发布）。
- 待发布池采用**四态状态机**：`pending → publishing → published / failed`，面板可定位失败环节。
- 新增 9 个配置项（总开关、远程 Redis 连接、轮询间隔、可见范围、文案前缀/截断长度、待发布池上限）。
- 远程 Redis 连接 `fallback=False`（队列场景不允许落到本地 JSON 假成功），与 bot 自身本地 Redis 连接相互独立。
- 文案纯文本渲染（顺风车/招聘两套模板），忽略 `images` 字段，按上限截断。

## Capabilities

### New Capabilities

- `deal-queue-consumer`: 消费远程同城信息推送队列，经人工确认后发布朋友圈并回报回执的完整能力。

### Modified Capabilities

<!-- 无既有 spec，全部为新能力。 -->

## Impact

- 新文件：`core/deal_queue_consumer.py`、`blueprints/deal.py`
- 修改：`wxbot_core.py`（初始化、主循环、`stop_wxbot`）、`core/config_manager.py`（默认值 + 同步）、`schema/coercers.py`（开关字段登记）、`blueprints/__init__.py`（注册蓝图）、`templates/dashboard.html`（侧边导航 + 新标签页 + saveConfig JS）、`README.md` / `docs/tech_doc.md`（配置字段表）
- 外部依赖：可访问 `122.51.49.63:6379 db0`（凭据入 `config/config.json`，gitignore）；不引入新 pip 依赖（复用 `redis`、`wxautox4` 既有能力）
- 契约约束：消费方行为需符合 `we-mp-rss/docs/redis-deal-queue.md`（队列键、回执 field、失败不自动重推、人工补救三态）
