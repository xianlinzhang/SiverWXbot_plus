## 1. 配置面

- [x] 1.1 `core/config_manager.py` `__init__` 声明 4 个新默认值（`deal_queue_auto_approve_switch`、`deal_queue_auto_approve_delay`、`deal_queue_publish_interval_min`、`deal_queue_publish_interval_max`）
- [x] 1.2 `core/config_manager.py` `update_global_config` 加同步行，int 就地 clamp（delay 0~86400、interval_min 1~86400、interval_max 保证 ≥ interval_min 且 ≤ 86400）
- [x] 1.3 `schema/coercers.py` `FIELD_HANDLERS` 登记 `deal_queue_auto_approve_switch: 'bool'`
- [x] 1.4 `blueprints/auth.py` setdefault 块补 4 项默认值（保证面板首渲染有值）
- [x] 1.5 `README.md` 与 `docs/tech_doc.md` 配置字段表补 4 项说明

## 2. 核心模块 `core/deal_queue_consumer.py`

- [x] 2.1 新增本地自动节奏键 `_auto_key()`（`wxbot:{wxid}:deal:auto` HASH：`next_publish`/`last_publish`）；`_read_next_publish()`/`_write_next_publish(last, next)` 读写（int 秒时间戳，missing 视为 0）
- [x] 2.2 新增 `_auto_publish_scan()`：读取池 `LRANGE`，从队尾（最老）找第一条 `status==pending` 的候选；判定 `now >= entry.updated_at + deal_queue_auto_approve_delay` 且 `now >= next_publish` 才调 `publish(field)`（返回失败静默跳过）；一次迭代最多发一条
- [x] 2.3 消费线程 `_loop` 每轮 `RPOP` 后调用 `_auto_publish_scan()`（仅 `deal_queue_auto_approve_switch` 开启时；外层 try/except 包裹不打断主循环）
- [x] 2.4 `_on_publish_result` 成功分支：写 `_auto_key`（`last_publish=now`、`next_publish=now+random.randint(min,max)`）；失败分支不动 next_publish（保持 `failed` 不重试）
- [x] 2.5 `get_stats()` 增加 `next_publish`（读 `_auto_key` 返回）供面板倒计时

## 3. 蓝图 `blueprints/deal.py`

- [x] 3.1 `GET /api/deals` 的 stats 透出 `next_publish`（从 `deal_consumer.get_stats()` 已有字段带出，无需新路由）

## 4. 面板 `templates/dashboard.html`

- [x] 4.1 `tab-deal` 配置卡新增自动审核区块：总开关 + 审核延迟(秒) + 发布间隔 min/max(秒)，照现有配置卡样式
- [x] 4.2 `saveConfig` JS 收集 4 个新字段（带 clamp）
- [x] 4.3 统计卡新增「下次自动发布」项，`refreshDeals()` 渲染倒计时（读取 `stats.next_publish`，格式 HH:MM:SS，无值显示 `-`）

## 5. 验证

- [x] 5.1 扩展 `test_deal_consumer.py`（mock 远程/本地 Redis + 任务队列）：延迟窗口内不发、窗口后可发、间隔随机区间、next_publish 持久化后重启恢复节奏、FIFO 最老优先、跳过 publishing/failed、失败不重试、与人工并发被 `publishing` 守卫挡住
- [ ] 5.2 手工验证清单：`python web_server.py` → 面板开自动审核 → 待发布入池后观察「下次自动发布」倒计时 → 到点自动发布 → 核对远程回执 `PUBLISHED` 与两次发布间隔落在随机区间 → 关闭自动审核确认回到人工模式





