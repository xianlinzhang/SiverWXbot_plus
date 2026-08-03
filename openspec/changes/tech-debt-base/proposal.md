# Proposal

## Problem

P3 处理影响「可验证性、可追溯性」的债：

### 1) 版本号散落多处以手工同步，易漏

AGENTS.md 声称「版本号在两处同步」，实际 grep 发现**不止两处**：

| 位置 | 内容 | 需同步? |
|------|------|--------|
| `wxbot_core.py:6-7` | `version` / `version_log` | 主源 |
| `docs/version.json` | `version` / `version_log` + 更新说明 | 派生 |
| `web_server.py:1356` | 硬编码 `'V4.7.27'` | 派生（与主源脱钩风险）|
| `ai_api.py:14` | `version = "V4.7.27"`（user-agent）| 派生 |
| `README.md` / `docs/docs.md` / 徽章 | `V4.7.27` | 文档 |

每次发版要手工对 4~6 处，漏一处就版本漂移；`web_server.py:1356` 硬编码与主源可能已经脱钩。

### 2) 无任何自动化测试

AGENTS.md 明确「无 pytest 等框架、无 lint/typecheck」。现有脚本需真实登录微信才能跑
（`demo.py` / `test_moment.py` / `wxautox4/tests/`）。这意味着：
- 任何改动都无法被机器验证，全靠 `python web_server.py` 手动跑面板看日志；
- 回归靠记忆，P0/P1/P2 的结构性改动尤其需要「行为不变」的机器证明。

### 3) 文档与配置同步只能靠人工

README 的配置字段表、`.trae/specs/` 设计规格，改动后需手工同步，易遗漏。

## 目标

1. 版本号收敛为**单一事实源**，其它位置从此处读取/生成，消除手工多写漂移。
2. 建立**不依赖真实微信**的最小可运行测试层，覆盖配置合法性、字段强制、任务队列、
  message_store 的 mock 路径等纯逻辑单元，让结构性重构有自动回归。
3. 搭好后续改动「可验证」的基线：`python -m pytest`（或等价最小 runner）能被新 change 复用。

## 非目标

- 不做大规模 UI / wxautox4 内核的端到端测试（那需真实微信，超出 P3 且本平台不易）。
- 不把手动运行 `python web_server.py` 的面板验证流程删除（它仍是最终接收）。
- 不处理 siver_panel（用户明确排除）。

## 验收

- 版本号：只改 `wxbot_core.py` 一处，`docs/version.json`、`ai_api` user-agent、
  面板/文档显示自动跟随（提供统一读取函数/脚本，README 徽章可接受仍硬编码）。
- 新增测试层：`python -m pytest`（或 runners）能跑通现有最小测试，零外部依赖 / mock 掉微信。
- 为 P0/P1/P2 的关键函数（如 `_parse_split_reply`、`_clean_reply_for_send`、task_queue、
  config 字段强制、message_store 存取）补上 smoke 级用例。
- `docs` 与 `README` 的配置表同步流程有文字文档（或指向集中表）。