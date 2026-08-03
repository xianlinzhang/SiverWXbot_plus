# Spec: 技术债基线（版本号单一来源 + 最小测试 + 文档）

能力：`tech-debt-base`

## 目的

让每次改动可被机器验证、版本号单一维护、文档同步可循，为 P0/P1/P2 提供验证设施。

## ADDED Requirements

### Requirement: 版本号单一事实源
系统 SHALL 以 `wxbot_core.py` 的 `version`/`version_log` 为唯一主源，各消费方 MUST 从此处
读取或经统一脚本生成，不得各自维护独立的版本字符串。

#### Scenario: 改版本只改主源
- GIVEN 发布新版本需要更新版本号
- WHEN 在 `wxbot_core.py` 更新 version/version_log
- THEN `docs/version.json` 经脚本同步、AI user-agent 引用主源
- AND 其它显示 / 面板读取到一致版本号

#### Scenario: 修复硬编码脱钩
- GIVEN `web_server.py` 曾硬编码 `'V4.7.27'`
- WHEN 该模块需要版本号
- THEN 引用统一的 `BOT_VERSION`，不保留副版本字符串

### Requirement: 不依赖真实微信的最小测试层
系统 SHALL 提供可在无微信登录环境下运行的自动测试 runner，覆盖配置字段强制、回复拆分/清洗、
任务队列、消息存储等纯逻辑契约，MUST NOT 依赖真实微信 UI。

#### Scenario: 纯逻辑单元可跑
- **GIVEN** 无微信登录环境
- **WHEN** 运行测试 runner（`python -m unittest discover tests` 或等价）
- **THEN** 配置 schema 校验、`_parse_split_reply`、`clean_ai_reply_text`、
          task_queue（伪 redis）、message_store（伪 redis）用例通过

### Requirement: 测试聚焦行为契约而非实现细节
新测试 SHALL 以行为契约断言（提交后能取到、保存后能读到、类型合法），而非绑定内部 key 结构，
以便 P1 的存储重构安全演进。

#### Scenario: 存储重构不清断测试
- **GIVEN** task_queue 或 message_store 内部 key 结构改变（如 List→ZSET）
- **WHEN 运行既有测试
- **THEN** 只要对外契约（submit→取到、save→读到）不变则仍通过

## MODIFIED Requirements

创建/更新文档约定：
- AGENTS.md 更新为「版本号由 `scripts/update_version.py` 一处生成」。
- README / docs 的版本徽章注明主源，避免误改。

## Scenario: 版本与测试并存可追溯
- **GIVEN** 一次改动涉及版本号与逻辑
- **WHEN** 发版（改主源 + 跑脚本）并运行测试
- **THEN** 版本各显示一致、测试通过、改动可被验证