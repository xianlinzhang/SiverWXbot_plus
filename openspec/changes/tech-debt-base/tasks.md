# Tasks

> 测试层用零依赖 `unittest`（`python -m unittest discover`）起步；如确有需要再评估 pytest。

## 1. 版本号单一事实源

- [x] `web_server.py:1356`：去掉硬编码 `'V4.7.27'`，改用已导入的 `BOT_VERSION`。
- [x] 评估 `core/ai_api.py:14` `version`：改为引用统一来源 `core/_version.py`（独立常量模块，
      避免 wxbot_core ↔ ai_api 相互 import 拉重链；wxbot_core 也从 _version 导入并 re-export）。
- [x] 写 `scripts/update_version.py`：读 `core/_version.py` 主源 → 写 `docs/version.json`（保留 infrom 等其余字段）→
      打印仍需手动的 README/docs 徽章位置说明。
- [x] 验证：改 `core/_version.py` 一处，跑脚本后 `docs/version.json` / wxbot_core / ai_api(user-agent) /
      web_server 全部一致（实测 V9.9.9 改一处三端跟随，已还原）。

## 2. 最小可运行测试层

- [x] 建 `tests/`（`__init__.py` + `conftest.py` 伪对象 FakeRedis / FakeConfig / FakeBot），
      mock 掉 redis / 微信依赖，避免启动 WXBot。
- [x] `test_config_schema.py`：LOAD→COERCE→SAVE 字段强制不抛错、类型白名单（bool/int）、
      新增字段集中表（BOOL_KEYS/INT_KEYS 登记）。
- [x] `test_split_message.py`：`_parse_split_reply` 边界（空/超 max_count/多分隔符/全空白）、`split_long_text`。
- [x] `test_clean_reply.py`：`clean_ai_reply_text` 空清洗语义（None→空、think 块移除、纯空白→空）。
- [x] `test_task_queue.py`：注入伪 redis 的 `submit`/`get_pending_tasks`/`cancel`/`clear`/取序契约（FIFO + 优先级）。
- [x] `test_message_store.py`：伪 redis 的 `save_message`/`get_all`/`set_message_status` 语义契约。
- [x] `test_ai_worker.py`：P0 AIWorker 串行执行/非阻塞入队/优雅停止契约。
- [x] 统一 runner：`python -m unittest discover tests -v` 一次跑通（30 用例全绿）。

## 3. 文档同步

- [x] `AGENTS.md`：更新版本号维护说明（`core/_version.py` 单一事实源 + `scripts/update_version.py` 一处生成，勿手抄多写）。
- [x] `README.md`：版本徽章注明唯一真实来源是 `core/_version.py`，避免多人手工改到多岛。

## 4. 回归对接前面阶段

- [x] 确认 P0（ai_worker 拆分）/ P1（ZSET 队列 / message_store 收敛）的关键函数能被新测试
      层接入；`storage-simplify` 的队列结构变更后测试仍走契约断言（FIFO/优先级/取消/清空/save-get/状态更新 全过）。

## 5. 验证

- [x] `python -m unittest discover tests -v` 全绿（30 tests OK）。
- [ ] `python web_server.py` 面板正常启动，版本显示与主源一致（待真机）。