# Proposal

## Problem

微信客服机器人的主循环 `WXBot.main()`（`wxbot_core.py:630`）是**单线程串行**的：

```
main() while 循环                    (wxbot_core.py:704)
  └─ chatlog_listen_loop()          (chatlog_manager.py:433)
       └─ chatlog_process_message()
            └─ _chatlog_send_ai()   (message_handler.py:163)
                 └─ api.chat()      ← 秒级同步网络阻塞 (message_handler.py:232/241/248/251)
```

所有 AI 接口调用都同步跑在唯一的监听主线程里。一次慢接口 / 一次超时 / 一次网络抖动，
会冻结整个 bot —— 离线检测、新好友检查、定时任务、朋友圈、点赞**全部停摆**。
这既是性能问题，也是稳定性问题：bot 不可预测地「卡死」，且难以察觉（错误只落日志）。

当前分界已部分到位：**消息发送**已通过 `task_queue` 异步执行（`message_handler.py:319`），
但**AI 生成**这一步仍在监听线程里同步跑。本 change 只把 AI 生成这一块解耦出去。

## 目标

1. AI 接口调用响应的**卡顿/超时不再冻结整个 bot** —— 主循环只管派发，永不触碰 AI 网络调用。
2. 单条回复的失败/超时只影响它自己，其它会话、其它模块照常运行。
3. 保持 wxautox4 微信 UI 驱动的安全边界：绝不引入多个并发写微信 UI 的线程（见 design，方案 A）。

## 非目标（Non-Goals）

- 不提升单会话 AI 回复的**并发吞吐**（不追求同一批多条消息并行过 AI）。
- 不重写 `task_queue`（那是 P1 范围：当前 AI worker 复用同一 worker 模型即可，暂不清扫其 lrange 实现）。
- 不拆 `web_server.py` / `wxbot_core.py` 转发层（P2 范围）。
- 不引入 pytest 等测试框架（P3 范围）。
- 不处理 `siver_panel`（用户明确排除）。

## 判定用户故事

1. 聊天/群聊触发多条 AI 回复，其中一条接口超时 —— 其它回复与离线检测/定时任务不受影响。
2. 主循环始终秒级 tick，无论 AI 是否在跑。
3. `msg_replied_count`、消息状态、`bind_reply` 等既有语义不回退。

## 验收

- 单独跑 `python web_server.py`，面板启动机器人。
- 构造一个「慢 AI」场景（临时指向一个故意延迟/不通的接口），观察：
  - 主循环 sleep 周期不被 AI 拖长；离线检测/新好友/定时任务照常轮询。
  - 慢接口只导致对应会话延迟，其它模块日志照常。
- 既有全部开关（关键字应答、chat_listen_only、图片识别、拆分回复、memory 增强）行为不回退。