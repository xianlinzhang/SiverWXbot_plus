## 1. 配置面

- [x] 1.1 `core/config_manager.py` `__init__` 声明 10 个新默认值（`deal_queue_consumer_switch`、`deal_queue_redis_host/port/db/password`、`deal_queue_poll_interval`、`deal_queue_privacy`、`deal_queue_moments_prefix`、`deal_queue_moments_max_len`、`deal_queue_pending_max`）
- [x] 1.2 `core/config_manager.py` `update_global_config` 加同步行，int 字段就地 clamp（poll 2~600、max_len 100~2000、pending_max 1~10000）
- [x] 1.3 `schema/coercers.py` `FIELD_HANDLERS` 登记 `deal_queue_consumer_switch: 'bool'`
- [x] 1.4 `README.md` 与 `docs/tech_doc.md` 配置字段表补 10 项说明

## 2. 核心模块 `core/deal_queue_consumer.py`

- [x] 2.1 新建 `DealQueueConsumer(bot)`：自建远程 `RedisManager(fallback=False)`（host/port/db/password 从 config 读），暴露 `is_remote_ready()`；本地待发布池复用 `bot.redis_manager`
- [x] 2.2 渲染器：顺风车/招聘两套模板，空字段跳过，前缀可配，超长按 `max_len` 截断，忽略 `images`；字段取值与 producer ORM 列名一致（`shun_fen_che`/`recruitment` 两表）
- [x] 2.3 消费线程 `_start/_stop/_loop`：daemon 线程，每 `deal_queue_poll_interval` 秒 `RPOP`；取到消息先校验 `LLEN wxbot:{wxid}:deal:pending < deal_queue_pending_max`（超限跳过并 `log` 告警）；组装 `field={source}:{unique_id}:{push_date}`，渲染后 `LPUSH` 待发布池 + `HSET` 详情（status=pending）
- [x] 2.4 `check()`：主循环每轮调用，按 `deal_queue_consumer_switch` 启停线程；远程不可用时记 ERROR 继续睡
- [x] 2.5 `get_pending()` / `get_stats()`：读待发布池列表（`LRANGE` + `HGETALL` 详情）与统计（pending/publishing/failed 计数 + 远程 `LLEN`）
- [x] 2.6 `publish(field)`：先 `HGET` 远程 status，已是 `PUBLISHED` 则拒绝返回提示；否则详情置 `publishing`，提交 `task_queue.submit('send_moments', {text, images:[], privacy, tags:[], _receipt_field: field}, callback)`
- [x] 2.7 发布回调 `_on_publish_result(success, result, params)`：成功 → 远程 `HSET PUBLISHED` + 本地 `LREM` + `HDEL` 详情；失败 → 详情置 `failed` 保留在池中
- [x] 2.8 `discard(field)`：远程 `HSET PUBLISHED` + 本地清理
- [x] 2.9 `re_push(field)`：远程 `HDEL` + 本地清理（不做本地去重）
- [x] 2.10 `stop()`：停线程（join timeout 5s），关闭远程连接

## 3. `wxbot_core.py` 接入

- [x] 3.1 `__init__` 创建 `self.deal_consumer = DealQueueConsumer(self)`（不启动线程）
- [x] 3.2 主循环加 `self.deal_consumer.check()`（try/except 包裹，异常记日志不打断主循环）
- [x] 3.3 `stop_wxbot` 加 `self.deal_consumer.stop()`

## 4. 蓝图 `blueprints/deal.py`

- [x] 4.1 新建 `blueprints/deal.py`（照 `blueprints/task.py` 模板）：`GET /api/deals`、`POST /api/deals/publish`、`POST /api/deals/discard`、`POST /api/deals/re_push`，统一 `_require_bot('deal_consumer')` 守卫与 `login_required`
- [x] 4.2 `blueprints/__init__.py` `build_blueprints()` 注册 `deal.bp`

## 5. 面板 `templates/dashboard.html`

- [x] 5.1 侧边栏加 `data-tab="tab-deal"` 导航项（图标自选）
- [x] 5.2 新增 `config-panel#tab-deal`：配置卡（10 项输入）+ 统计卡（待发布/发布中/失败/远程队列长度）+ 待发布列表（source 徽标、渲染文案预览、状态标签、发布/丢弃/重推按钮），照 `tab-messages` 结构与样式
- [x] 5.3 JS：`loadDealData()` 拉 `/api/deals` 渲染列表；发布/丢弃/重推调对应接口；`saveConfig` 收集 10 个新字段；进入标签页时刷新
- [x] 5.4 四态状态标签渲染（pending 待发布 / publishing 发布中 / published 已发布 / failed 失败）

## 6. 验证

- [x] 6.1 写本地验证脚本（`test_deal_consumer.py`，mock 远程 Redis 与 `wx.SendMoments`）：渲染器输出正确（顺风车/招聘/空字段/截断/前缀）、`publish` 成功回执 `PUBLISHED`、失败留 `QUEUED`、`discard`/`re_push` 回执正确、池上限停止拉取
- [ ] 6.2 手工验证清单：`python web_server.py` → 面板登录 → 「同城发布」标签页 → 开总开关 → 待发布入池 → 发布一条核对远程回执 → 关闭总开关确认线程停止
