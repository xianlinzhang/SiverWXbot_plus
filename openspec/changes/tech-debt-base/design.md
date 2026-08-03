# Design

## 一、版本号单一事实源

### 现状（多处手工，易漂移）

```
wxbot_core.py:version            ← 主源（人工改）
docs/version.json:version        ← 人工抄
web_server.py:1356 硬编码        ← 人工抄, 已潜在脱钩
core/ai_api.py:14 version        ← 人工抄 (user-agent)
README/docs 徽章, 面板显示        ← 人工抄
```

### 目标：单一来源 + 一处生成

方案：以 `wxbot_core.py` 为**主源**，其余全部读取它或由构建脚本生成。

- `web_server.py` 已 `from wxbot_core import version as BOT_VERSION`（:24）——把 :1356 硬编码
  改为引用 `BOT_VERSION` 即可（此项是纯 bug 修复，消除潜在脱钩）。
- `core/ai_api.py`：改为 import `wxbot_core.version`（或注入），不再自持一份字符串。
- `docs/version.json`：由一次性脚本从 `wxbot_core` 生成，或提供 `scripts/update_version.py`
  （读主源 → 写 version.json → 打印面板/文档需改的标语），发版只改主源再跑脚本。
- README/docs 徽章：可接受仍硬编码，但文档注明「唯一真实来源是 wxbot_core.version」。

发版流程收敛为：
```
1) 改 wxbot_core.py 的 version / version_log
2) 跑 scripts/update_version.py  → 同步 docs/version.json（+提示其它手动位置）
```

## 二、最小可运行测试层（不依赖真实微信）

现状 `test_moment.py` 已 mock 掉 redis；`wxautox4/tests/` 存在。P3 基于此搭骨架：

```
tests/
  __init__.py
  conftest.py          # mock 配置对象 / 关闭 redis / 避免弹微信
  test_config_schema.py   # 字段强制器往返(load→coerce→save) 不抛错、类型对
  test_split_reply.py     # _parse_split_reply / split_long_text 边界
  test_clean_reply.py     # clean_ai_reply_text 空/正常
  test_task_queue.py      # 用 memory/伪 redis 的 TaskQueue.submit→ZSET 取序
  test_message_store.py   # 伪 backend 的 save/get/set_status 语义
```

原则：
- 只测**纯逻辑 / 可 mock 边界**，不启动 WXBot(需真实登录)、不驱动微信 UI。
- 对 `core/*` 纯函数、`schema/coercers`、`message_store`（注入伪 redis）、`task_queue`
  （注入伪 redis）给 smoke 用例。
- runner 选择：仓库无 deps。优先用内置 `unittest`（零依赖，`python -m unittest discover`），
  若确定性缺依赖再考虑 `pytest`（作为 dev extra，不进 requirements 生产依赖）。

## 风险

1. **mock 过度 + 与结构漂移**：测试里含实现细节（如 ZSET key）易碎，测试聚焦「行为不变」契约
   （submit 后 get_pending 顺序、save 后 get 得回、coerce 后类型对）。
2. **ai_api import wxbot_core 可能拉重链**：ai_api 与 wxbot_core 相互 import 风险，若构造性避免
  （如把 version 抽到独立 `_version.py` 常量模块，两者都 import 之）更干净。
3. **测试不覆盖真实微信路径**：需明确这是「单元/契约层」，最终验收仍需跑面板 —— 文档写明边界。

## 三、文档同步基线

- 新增小改：在 AGENTS.md 更新「版本号现已由 scripts/update_version.py 一处生成，勿手抄多写」。
- `docs` / `README` 配置表：把指向集中 schema 表的能力写清楚。

## 不做（后续 phase）

- AI worker（P0）、存储简化（P1）、web_server blueprint（P2）—— 但本 change 为其提供验证设施。