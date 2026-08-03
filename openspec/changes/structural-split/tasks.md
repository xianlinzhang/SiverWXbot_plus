# Tasks

> 全部改动跑 `python web_server.py` → 面板逐项回归验证（无 pytest）。
> 每抽一个 blueprint / 每收敛一批转发，跑一次面板确认行为不变，小步前进。

## 1. web_server 内部按域重排（第一步，无行为改动）

- [x] 在 `web_server.py` 内按域对函数/路由分组 + 注释分区（auth/config/prompt/bot/task/
      message/memory/contacts/system）——以 域1~域6 横幅 + 既有 `---...---` 分区归位，纯注释不挪逻辑。
- [ ] 确认运行正常后 commit 基线。（不自动 commit；待用户确认）

## 2. 抽 schema 字段强制集中表

- [x] 将 `_coerce_bool_fields` / `_coerce_list_fields` / `_coerce_float_fields` /
      `_coerce_int_range_fields` / `_coerce_dict_fields`（原 :770-960）抽为 `schema/coercers.py`
      的集中表 `FIELD_HANDLERS`（55 字段，单一登记处），`coerce_*_fields()` 五个函数由表驱动。
- [x] 校验字段 key → 强制规则映射完整，无遗漏（55 条全被消费；bool/list/float/int/dict 各型有测试）
- [x] 回退验证 `load_config` / `save_config` 行为与拆分前一致：
      `save_config` 仍跑 5 个强制器（含 int_range，float 取原值兜底）；
      `save_config_route` 仍只跑 4 个（bool/list/float/dict，不含 int_range）。新增 `tests/test_coercers.py`
      15 用例覆盖，全套 45 用例全绿。

## 3. 抽 blueprints（每抽一个跑一次面板验证）

> 说明：9 个 blueprint 模块 + `create_app()` 聚合已实施完成，沙箱已做路由/登录/静态回归；
> 真机面板逐项回归归入任务 5 全量回归。

- [x] `blueprints/auth.py`：login/logout/dashboard 渲染/鉴权/安全头/登录限流。
- [x] `blueprints/config.py`：load/save_config、test_api_config、backup、字段强制引用。
- [x] `blueprints/prompt.py`：list/save/delete_prompt。
- [x] `blueprints/bot.py`：start/stop_bot、activate、check_activate/update、get_status、siver-panel 状态。
- [x] `blueprints/task.py`：/api/tasks*（status/pending/history/cancel/clear）。
- [x] `blueprints/message.py`：/api/messages*、send_message。
- [x] `blueprints/memory.py`：/memory/*。
- [x] `blueprints/contacts.py`：/api/contacts*。
- [x] `blueprints/system.py`：redis status/stats、pick_image_file 等 misc。
- [x] `__init__.py` / 启动入口收敛为 `create_app()`，注册全部 blueprint。

## 4. wxbot_core 转发层收敛

> 68 个手抄转发已收敛为 `_FORWARD_TABLE` + `install_forwarders()` 生成式转发表（组合 > 手抄），
> 新 core 方法只需在聚合对象下登记一行。同时修复 2 个潜在 bug：
> `process_message` / `wx_send_ai`（core 内 `self.bot.X` 调用但 WXBot 从未定义）。

- [x] 盘点 77 个方法是纯透传还是含逻辑；分类（聚合暴露可删 / 必须保留 / 生成式）。
- [x] 对纯透传、外部只当门面用的：改为调用方直接走 `bot.<聚合对象>.<method>`（web_server/blueprints 本就直连聚合对象，无 `bot.<forwarder>` 依赖）。
- [x] 对本类或对外契约必须挂在 WXBot 的：集成组并保留或走生成式转发表（`_FORWARD_TABLE` 5 组 68 项 + 修复 2 项 = 70）。
- [x] 确认 `web_server.start_bot` 里的 `WXBot(...).run()` 入口与既有调用点稳定不变（`run()`/`main()` 原样保留）。
- [x] 验证：45 测试全绿；`WXBot()` 实例化后 70 转发可调用、委托正确；`web_server` app 57 路由不变。

## 5. 全量回归

- [ ] `python web_server.py` 启动，逐一回归：登录、保存配置、API 测试、prompt、备份、
       任务队列、消息、记忆、联系人、统计、redis、远程面板。
- [ ] 确认模板/静态文件/`panel_logs` 相对路径不因目录变化断裂。
- [ ] `git diff` 确认重构无行为性功能改动（净等价结构）。