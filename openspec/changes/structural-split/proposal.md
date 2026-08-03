# Proposal

## Problem

两个「大而黏」的文件拖累可维护性，改动在单文件里游泳、风险传导、难并行。

### 1) web_server.py（2897 行单文件，~57 个路由）

一个文件同时承担：Flask 路由分发、模板渲染、配置读取/校验/存入、API 测试、prompt 管理、
备份、任务/消息/记忆/联系人 REST API、siver-panel 远程面板、登录鉴权与安全头。
单一 `app` 全局对象 + 大量 `@app.route` 平铺在顶部，函数位置即路由、无模块边界。
要改「配置字段」就得在 `_coerce_bool_fields` / `_coerce_list_fields` / `_coerce_int_range_fields`
（:770-960 一堆字段强制器）与前端模板 `templates/dashboard.html` 之间来回对齐，牵一发动全身。

### 2) wxbot_core.py（782 行，其中 77 个方法几乎是纯机械转发）

```
WXBot.process_command  → return self.command_handler.process_command(...)
WXBot.handle_add_user  → return self.command_handler.handle_add_user(...)
WXBot._get_group_api   → return self.message_handler._get_group_api(...)
... ×77
```

这些转发是纯粹样板，不夹逻辑，纯为「把 WXBot 当成统一门面」。好处是调用方（web_server、
其他模块）只依赖 `WXBot` 一个对象；坏处是每个 `core/` 方法都必须在 `wxbot_core` 手抄一遍，
新方法忘记加转发就产生「丢了一层」的隐性耦合，文件持续膨胀。

## 目标

1. `web_server.py` 拆成若干 blueprint / 模块，每个路由簇归位到职责文件，`app` 工厂化。
2. `wxbot_core.py` 的 77 个纯样板转发收敛：能通过「组合/属性暴露」取代的，不再手抄。
3. 对外行为**完全不变**（所有 URL、路由签名、模板、既有 config 结构、admin 登录全保留）。

## 非目标

- 不改路由 URL、不改前端模板、不改配置 JSON 结构、不改登录鉴权流程。
- 不顺手做 P0（AI worker）/ P1（存储）的改动。
- 不重构 wxautox4 内核库。
- 不处理 siver_panel（用户明确排除）。

## 验收

- 启动 `python web_server.py`，面板登录、所有既有路由（配置保存、API 测试、prompt、备份、
  任务/消息/记忆/统计/联系人/redis、登录鉴权、远程面板状态）行为与拆分前一致。
- `git diff` 在重构变更中**只增相等价结构**，无行为性功能改动可被识别。
- wxbot_core 中不再有新功能需要「加转发」。

## 判定用户故事

1. 想给面板加一个新的「配置开关字段」：改动落在单一模块 + 一处字段强制集中表，而非 2897 行里搜索。
2. 新加一个 `message_handler` 方法：调用方直接用量存在，无需又在 wxbot_core 抄一遍。