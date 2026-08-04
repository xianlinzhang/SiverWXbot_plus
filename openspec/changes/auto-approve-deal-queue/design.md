## Context

见 proposal.md - Why。基座 `consume-deal-redis-queue`(已归档)实现:远程队列 RPOP → 本地待发布池(`wxbot:{wxid}:deal:pending` LIST + `wxbot:{wxid}:deal:pending:{field}` HASH,四态 pending/publishing/published/failed)→ 人工 `publish()` 走 `task_queue.submit('send_moments')` → 成功回调回报 `PUBLISHED`。消费线程由主循环 `check()` 按 `deal_queue_consumer_switch` 启停,每 `deal_queue_poll_interval` 秒一轮。相关约束:

- `publish(field)` 已内建守卫:`publishing` 拒绝重复、远程回执 `PUBLISHED` 拒绝、远程不可用拒绝
- 待发布池 LIST 是 LPUSH(队头最新),HASH 详情含 `text/status/updated_at`
- 面板已有 `tab-deal`(配置卡 + 统计卡 + 列表),`saveConfig` 收集全部配置字段
- 项目拟人化 DNA:`core/utils.py` 提供 `_coerce_int_range`、`random` 随机延迟模式(如 `moments_like_min/max`)

## Goals / Non-Goals

**Goals:**
- 待发布池无人值守自动发布,纯放行(无内容过滤)
- 审核延迟窗口 + 随机发布间隔双节奏控制
- 上次发布时间持久化,重启不连发爆量
- 自动发布复用既有 `publish()` 链路,回执语义零改动

**Non-Goals:**
- AI 内容审核/过滤(已明确不做)
- 拆出独立发布线程(并入消费线程,见 D1)
- 失败自动重试(已明确不重试,人工处理)
- 修改远程回执契约或生产者侧代码

## Decisions

**D1. 自动发布并入消费线程 poll 循环,不拆新线程。**
消费线程每轮已有 `RPOP` 节奏,自动发布扫描在同轮执行:先拉取(若有),再调 `_auto_publish_scan()`。单线程,状态机无并发锁。代价:发布节奏精度 = `deal_queue_poll_interval`(默认 5s),对秒~分钟级间隔足够。
- 备选:独立 daemon 线程——多一份生命周期/锁管理,收益小,否决。
- 依赖:自动发布跟随 `deal_queue_consumer_switch` 启停(消费关则不自动发)。

**D2. 时间模型:`next_publish` 单一判定基准。**
持久化一个本地 Redis Hash `wxbot:{wxid}:deal:auto`,字段:
- `next_publish`(int 秒时间戳):下次允许自动发布的最早时刻
- `last_publish`(int 秒时间戳):上次成功发布时刻(统计/诊断用)

自动发布候选判定:`now >= next_publish` 且存在可发布记录 → 提交一条。发布成功后回调里写 `last_publish = now`、`next_publish = now + random.randint(interval_min, interval_max)`。审核延迟窗口合并进 `next_publish` 初值:第一条入池时若 `next_publish` 不存在或已过,则取 `max(now, entry_time + delay)` 作为该记录可发布的基准——**每条候选单独比较 `entry_time + delay`**,而 `next_publish` 只控制全局节奏:
```
候选可发 = (now >= item.entry_time + auto_approve_delay) AND (now >= next_publish)
```
- 备选(延迟放内存、只存 last_publish):重启后 delay 语义漂移、面板倒计时只能估算,否决。
- 备选(把 next 用随机值算一次存死):发布被人工动作打断后不准,每次判定实时读 `next_publish` 即可。

**D3. 首次与重启语义。**
本地无 `wxbot:{wxid}:deal:auto` 键时:首条候选可立即发布(`next_publish` 视为 0),成功后写入基准。重启后键仍在 → 按持久化的 `next_publish` 恢复节奏,不连发。天然满足「重启恢复节奏」与「从未发布过」两个场景。

**D4. FIFO 选取,一次迭代最多发一条。**
扫描时用 `LRANGE` 读池(队头最新),从队尾起找第一条 `status == pending` 的记录;跳过 `publishing`/`failed`。提交后回调里更新 `next_publish`,下一轮迭代再判定下一条——保证「从早到晚依次发布」且间隔只取决于成功回调时间。
- 需注意池 LIST 元素是 field 字符串,HASH 详情才是状态源;`status` 缺失的记录视为 `pending`(兼容入池瞬间的窗口)。

**D5. 失败不自动重试。**
自动发布与人工共用 `publish()` 与 `_on_publish_result`。失败回调把详情置 `failed` 留在池中;`_auto_publish_scan` 只认 `pending`,天然不会重试 `failed`。回执保持 `QUEUED`(契约语义不变)。

**D6. 配置项(5 个,热重载)。**
- `deal_queue_auto_approve_switch`(bool, False)——自动审核总开关
- `deal_queue_auto_approve_delay`(int, 60 秒, clamp 0~86400)——入池后延迟窗口
- `deal_queue_publish_interval_min`(int, 300 秒, clamp 1~86400)——发布间隔下限
- `deal_queue_publish_interval_max`(int, 600 秒, clamp min~86400)——发布间隔上限

`config_manager` 声明默认值 + `update_global_config` 同步(间隔 min/max 就地 clamp,保证 max ≥ min);`schema/coercers.py` 登记开关 `'bool'`;`auth.py` setdefault 补默认,保证面板首渲染有值。面板 `saveConfig` 收集 4 项(开关已含)。

**D7. 面板「下次自动发布」倒计时。**
`GET /api/deals` 的 stats 增加 `next_publish`(来自 `wxbot:{wxid}:deal:auto`),面板统计卡渲染「下次自动发布约 HH:MM:SS」;自动审核开启且无候选/无 next 时显示「-」。零额外轮询,复用既有 `refreshDeals` 5s 轮询。

## Risks / Trade-offs

- [自动发布与人工同时点到同一条] → `publishing` 守卫拒绝重复提交,无副作用
- [间隔随机区间固定 min 上限导致节奏可预测] → 区间由用户配置,默认 300~600s 已足够打散;与 `moments_like` 同构
- [微信 UI 层失败反复自动重发骚扰] → D5 失败不重试,停留 `failed` 人工处理
- [延迟窗口内大量入池 + 大间隔 → 池满告警持续] → 信息按天,池满只告警不丢数据,人工可临时调大上限或丢弃
- [重启瞬间多条已过延迟候选 → 理论上第一轮只发一条] → `next_publish` 持久化保证后续仍按间隔,不连发
- [`next_publish` 写失败(本地 Redis 不可用)] → 自动发布跳过本轮记日志;本地 Redis 为 bot 主存储,降级路径已有既有 fallback,可接受

## Migration Plan

1. 配置项 + 面板骨架(开关默认 False),不影响现有人工模式
2. `deal_queue_consumer.py` 落地 `_auto_publish_scan` + `next_publish` 读写,本地单测(mock 远程/本地 Redis)验证时间模型与 FIFO
3. 生产验证:开自动审核 → 观察面板「下次自动发布」倒计时 → 到点自动发布一条 → 核对远程回执 `PUBLISHED` → 核对间隔随机
4. 回滚:关 `deal_queue_auto_approve_switch` 即回到纯人工模式;`next_publish` 键残留无害(下次开启时按已存时间继续)

## Open Questions

- 无。规格、方案、任务均已收敛。
