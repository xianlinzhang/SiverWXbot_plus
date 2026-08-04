## Why

同城信息消费（`consume-deal-redis-queue`）已实现人工确认发布流程,但运营上希望无人值守全自动发布:消息入池后无需人工点击「发布」,系统按拟人化节奏自动发布朋友圈。当前每次发布都要人工确认,无法规模化。

## What Changes

- 新增「自动审核」总开关,开启后待发布池中的 `pending` 记录自动进入发布流程(纯放行,不做 AI 内容过滤)
- 新增「审核延迟」配置:消息入池后等待该时长才允许自动发布(给运营留拦截窗口,期间仍可人工丢弃/重推)
- 新增「发布间隔」随机区间配置:任意两条已发布朋友圈之间至少间隔随机时长,避免固定规律被风控
- 自动发布走既有 `publish()` → `send_moments` → 成功回调回报 `PUBLISHED` 链路,回执契约零改动
- 上次发布时间持久化到 Redis,重启后不连发爆量
- 自动发布失败后停留 `failed`,不自动重试(人工处理,防风控)
- 面板「同城发布」标签页:新增配置项 + 「下次自动发布预计时间」倒计时展示
- **不改变**:人工「发布/丢弃/重推」按钮(自动开启时仍可用)、四态状态机、远程回执语义、待发布池容量上限

## Capabilities

### New Capabilities
- `auto-approve`: 待发布池自动发布能力——自动审核开关、审核延迟窗口、随机发布间隔、上次发布时间持久化、失败不自动重试、面板倒计时展示

### Modified Capabilities
- (无;本变更不改动 `deal-queue-consumer` 已有 requirement 的行为语义)

## Impact

- `core/config_manager.py`:新增 5 个配置项(开关/延迟/间隔min/max)及默认值、同步行、clamp
- `core/deal_queue_consumer.py`:消费线程 poll 循环内新增自动发布扫描(FIFO 选取最老 pending 记录);新增 `last_publish` 时间戳读写;新增「下次自动发布」计算
- `templates/dashboard.html`:同城发布标签页加自动审核配置卡 + 倒计时展示
- `schema/coercers.py`、`README.md`、`docs/tech_doc.md`:配置字段登记与文档
- 依赖:既有 `wxbot:{wxid}:deal:pending` 池结构、`task_queue.submit` 回调、远程回执契约(均不变)
