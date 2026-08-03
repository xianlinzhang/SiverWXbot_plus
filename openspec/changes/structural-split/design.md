# Design

## 一、web_server.py → blueprint / 模块化

### 现状：单文件平铺

```
web_server.py (2897 行, 一个全局 `app`)
  路由/模板/配置/字段强制器/测试API/prompt/备份
  /任务/消息/记忆/联系人/redis/远程面板/登录鉴权
  全部 @app.route 平铺, 无模块边界
```

### 目标：factory pattern + blueprint 分簇

```
app 工厂 (create_app) 返回 Flask app
  ├─ blueprints/auth    login/logout/鉴权/安全头/登录限流 (dashboard.html 渲染页)
  ├─ blueprints/config  配置 load/save/校验/字段强制器 /test_api_config /备份
  ├─ blueprints/prompt  prompt 列表/保存/删除
  ├─ blueprints/bot    start_bot/stop_bot/activate/check_* /get_status /启动
  ├─ blueprints/task    /api/tasks*
  ├─ blueprints/message /api/messages* / send_message
  ├─ blueprints/memory  /memory/*
  ├─ blueprints/contacts /api/contacts*
  └─ blueprints/system  redis / misc / pick_image_file
```

原则：
- **URL / 路由签名 / 模板 / 配置结构 零改动**。blueprint 只搬函数归位，不改名路由。
- 跨 blueprint 共享的 `bot` 实例、`app.config`、secret、`log_server` 通过 `app` 上下文（`g`/
  `current_app`）或显式注入蓝图 `Blueprint.register` 时传入，杜绝循环 import。
- 字段强制器（`_coerce_*_fields`, :770-960）抽成 `schema/coercers.py` 集中表，前端 key 与
  强制器一一对应，新增字段只动这一处。

### 分步策略（低风险）

1. 先在 `web_server.py` 内部把函数按域重组+注释分组（不改行为），
2. 逐步抽 `blueprints/*.py`，每抽一个跑一次面板验证，
3. 最后把启动/bootstrap 收敛成 `create_app()`。

## 二、wxbot_core.py（782 行, 77 个机械转发）收敛

### 现状

```
class WXBot:
    def process_command(self, chat, message):
        return self.command_handler.process_command(chat, message)
    def handle_add_user(self, chat, message):
        return self.command_handler.handle_add_user(chat, message)
    ... ×77 手抄样板
```

### 收敛策略（组合 + 属性暴露，取代手抄）

以「组合优于逐一转发」收敛，三类：

1. **纯透传、不再被本类内部引用、外部也只当门面用的**：让调用方直接走到 `bot.command_handler` /
   `bot.message_handler` 等聚合对象，`WXBot` 上只保留**聚合访问器**（如
   `bot.cmd._add_user(...)`）或保持极少量高频门面。

2. **本类内部确实复用、或对外契约必须挂在 WXBot 上的**：保留，但收进按域组织的少量方法。

3. **样式一致的批量转发**：若必须保留，用「显式转发表 + 自动生成」代替手抄，保证新方法不漏层。

不强制数量指标——目标不是把 782 行压成 200 行，而是**消灭「改 core 还要同步手抄 wxbot_core」
这种隐性耦合**：未来加方法要么直接暴露聚合对象，要么走生成式转发。

## 风险

1. **循环 import**：blueprint 间、wxbot_core 与 core 模块互相 import → 工厂/注入式层级规避。
2. **blueprint 前缀与既有 URL 冲突**：绝不改名路由，只做函数归位。
3. **临时文件形态**：拆完需确认 `panel_logs`、静态文件、模板引用相对路径不因目录变化断裂。
4. wxbot_core 收敛若动到调用点（web_server.start_bot 里 `WXBot(...).run()`），需保持入口稳定。

## 不做（后续 phase）

- AI worker（P0）、存储简化（P1）。
- 版本号一处化 / 测试框架（P3）。