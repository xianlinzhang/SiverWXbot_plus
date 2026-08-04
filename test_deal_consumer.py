#!/usr/bin/env python3
"""
同城信息队列消费者（deal_queue_consumer）本地验证脚本。

不连接真实远程 Redis，也不调微信 UI：用内存 mock 替代远程 Redis、本地 Redis 与任务队列，
验证：渲染器（顺风车/招聘/空字段/截断/前缀）、发布成功回执、发布失败留 QUEUED、
已发布拒绝重复、discard/re_push 回执、待发布池容量上限停止拉取。

运行：python test_deal_consumer.py
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.deal_queue_consumer as dqc
from core.deal_queue_consumer import DealQueueConsumer, QUEUE_KEY, STATUS_KEY

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


class MockRemoteRedis:
    """模拟远程 Redis：只实现消费者用到的接口。"""

    def __init__(self):
        self.queue = []       # 队头是索引 0，rpop 从队尾取
        self.status = {}      # field -> QUEUED/PUBLISHED
        self.available = True

    def is_available(self):
        return self.available

    def rpop(self, name):
        if name != QUEUE_KEY:
            return None
        return self.queue.pop() if self.queue else None

    def llen(self, name):
        return len(self.queue) if name == QUEUE_KEY else 0

    def hget(self, name, field):
        return self.status.get(field) if name == STATUS_KEY else None

    def hset(self, name, field, value):
        if name == STATUS_KEY:
            self.status[field] = value

    def hdel(self, name, *fields):
        removed = 0
        if name == STATUS_KEY:
            for f in fields:
                if f in self.status:
                    del self.status[f]
                    removed += 1
        return removed

    def close(self):
        pass


class MockLocalRedis:
    """模拟本地 Redis（bot.redis_manager）。"""

    def __init__(self):
        self.data = {}

    def lpush(self, name, *values):
        if not isinstance(self.data.get(name), list):
            self.data[name] = []
        for v in reversed(values):
            self.data[name].insert(0, v)
        return len(self.data[name])

    def llen(self, name):
        lst = self.data.get(name)
        return len(lst) if isinstance(lst, list) else 0

    def lrange(self, name, start=0, end=-1):
        lst = self.data.get(name)
        if not isinstance(lst, list):
            return []
        if end < 0:
            end = len(lst) + end
        return lst[start:end + 1]

    def hset(self, name, key, value):
        if not isinstance(self.data.get(name), dict):
            self.data[name] = {}
        self.data[name][key] = value

    def hget(self, name, key):
        d = self.data.get(name)
        return d.get(key) if isinstance(d, dict) else None

    def hgetall(self, name):
        d = self.data.get(name)
        return dict(d) if isinstance(d, dict) else {}

    def lrem(self, name, count, value):
        lst = self.data.get(name)
        if not isinstance(lst, list):
            return 0
        before = len(lst)
        self.data[name] = [x for x in lst if x != value]
        return before - len(self.data[name])

    def delete(self, name):
        if name in self.data:
            del self.data[name]
        return 0


class MockTaskQueue:
    def __init__(self):
        self.submitted = []

    def submit(self, task_type, params, priority=5, callback=None):
        self.submitted.append({
            "type": task_type, "params": params,
            "priority": priority, "callback": callback,
        })
        return "task-1"


class MockBot:
    def __init__(self, local, task_queue):
        self.redis_manager = local
        self.task_queue = task_queue
        self.wx = type("Wx", (), {"nickname": "test_wx"})()
        self.config = type("Config", (), {
            "deal_queue_consumer_switch": False,
            "deal_queue_redis_host": "122.51.49.63",
            "deal_queue_redis_port": 6379,
            "deal_queue_redis_db": 0,
            "deal_queue_redis_password": "",
            "deal_queue_poll_interval": 0.1,
            "deal_queue_privacy": "public",
            "deal_queue_moments_prefix": "",
            "deal_queue_moments_max_len": 2000,
            "deal_queue_pending_max": 500,
            "redis_timeout": 2,
        })()


def make_consumer(remote, local, task_queue):
    dqc.RedisManager = lambda cfg: remote
    bot = MockBot(local, task_queue)
    return DealQueueConsumer(bot)


def sample_shun():
    return {
        "source": "shun_fen_che",
        "id": 1,
        "unique_id": "abc123",
        "push_date": "2026-08-04",
        "departure": "深圳",
        "destination": "广昌",
        "time_str": "明天早上 8:00",
        "car_type": "SUV",
        "num_people": "3",
        "phone": "13800000000",
        "original_content": "【顺风车：深圳→广昌】3人，SUV，明天早上8:00，联系电话13800000000",
        "status": "NORMAL",
    }


def sample_recruit():
    return {
        "source": "recruitment",
        "id": 2,
        "unique_id": "xyz789",
        "push_date": "2026-08-04",
        "type": "招聘",
        "title": "招聘销售经理",
        "corp": "某某科技有限公司",
        "address": "深圳南山区",
        "price": "15-20K",
        "recruitment_jobs": "销售经理",
        "job_skills": "",
        "education": "大专",
        "contact_person": "王经理",
        "phone": "13900000000",
        "content": "急招销售经理，公司某某科技有限公司，地点深圳南山区，薪资15-20K。联系电话13900000000",
        "images": "http://example.com/x.jpg",
    }


def test_renderer():
    print("\n[渲染器]")
    remote = MockRemoteRedis()
    local = MockLocalRedis()
    consumer = make_consumer(remote, local, MockTaskQueue())

    text = consumer.render(sample_shun())
    check("顺风车直接发 original_content", text == sample_shun()["original_content"])
    check("顺风车原文含电话", "13800000000" in text)

    t2 = consumer.render(sample_recruit())
    check("招聘含标题", "【招聘】招聘销售经理" in t2)
    check("招聘含原始 content", "急招销售经理" in t2 and "15-20K" in t2)
    check("电话不重复（content 已含）", "电话：13900000000" not in t2)

    empty = consumer.render({"source": "shun_fen_che", "original_content": ""})
    check("顺风车缺原文返回空串", empty == "")

    # 各 type：标题按 type 组成 + 原始 content
    sale = consumer.render({
        "source": "recruitment", "type": "出售", "title": "出售",
        "corp": "早稻米", "phone": "19916019398",
        "content": "自家种老品种78130早稻米，做粘糍用的米，联系电话19916019398",
    })
    check("出售标题用物品(corp)", sale.startswith("【出售】早稻米"))
    check("出售含原始 content", "老品种78130" in sale)
    check("电话不重复（content 已含）", "电话：" not in sale)

    job = consumer.render({
        "source": "recruitment", "type": "求职", "title": "求职",
        "recruitment_jobs": "销售岗", "job_skills": "拓客谈单",
        "education": "未知", "address": "广昌", "contact_person": "王女士",
        "phone": "18970480925",
        "content": "本人女50岁，求职销售岗，联系电话18970480925王女士",
    })
    check("求职标题用意向岗位", job.startswith("【求职】销售岗"))
    check("求职含原始 content", "本人女50岁" in job)

    # content 缺失回退字段模板
    fallback = consumer.render({
        "source": "recruitment", "type": "出售", "title": "出售",
        "corp": "早稻米", "price": "未提及", "address": "未提及",
        "subject_params": "老品种78130", "contact_person": "未提及",
        "phone": "19916019398", "content": "",
    })
    check("content 缺失回退字段模板", "老品种78130" in fallback and "未提及" not in fallback)

    unknown = consumer.render({"source": "recruitment", "type": "随便", "title": "t", "phone": "1"})
    check("未知 type 用兜底模板", "【随便】" in unknown and "电话：1" in unknown)

    consumer.bot.config.deal_queue_moments_prefix = "#同城信息#"
    check("前缀出现在开头", consumer.render(sample_shun()).startswith("#同城信息#\n"))
    consumer.bot.config.deal_queue_moments_prefix = ""

    consumer.bot.config.deal_queue_moments_max_len = 30
    long_text = consumer.render(sample_shun())
    check("超长截断", len(long_text) <= 30)
    consumer.bot.config.deal_queue_moments_max_len = 2000

    unknown = consumer.render({"source": "unknown", "unique_id": "1", "push_date": "2026-08-04"})
    check("未知 source 返回空串", unknown == "")


def test_publish_and_receipt():
    print("\n[发布与回执]")
    remote = MockRemoteRedis()
    local = MockLocalRedis()
    task_queue = MockTaskQueue()
    consumer = make_consumer(remote, local, task_queue)

    remote.queue.append(json.dumps(sample_shun()))
    consumer._consume(json.loads(json.dumps(sample_shun())))
    field = "shun_fen_che:abc123:2026-08-04"
    remote.status[field] = "QUEUED"  # 生产者入队时写入 QUEUED
    pending = consumer.get_pending()
    check("消费后入池 1 条", len(pending) == 1)
    check("入池状态 pending", pending[0].get("status") == "pending")
    check("远程回执保持 QUEUED", remote.status.get(field) == "QUEUED")

    # 发布中（重复发布拒绝）
    ok, _ = consumer.publish(field)
    check("发布提交成功", ok)
    check("提交了 send_moments 任务", task_queue.submitted and task_queue.submitted[-1]["type"] == "send_moments")
    check("params 透传 _receipt_field", task_queue.submitted[-1]["params"].get("_receipt_field") == field)
    ok2, msg2 = consumer.publish(field)
    check("发布中拒绝重复发布", not ok2 and "发布中" in msg2)

    # 任务成功（wxautox 返回 status=成功）→ 回报 PUBLISHED 并移出池
    task = task_queue.submitted[-1]
    task["callback"](True, {"status": "成功"}, task["params"])
    check("成功后远程回执 PUBLISHED", remote.status.get(field) == "PUBLISHED")
    check("成功后移出待发布池", consumer.get_pending() == [])

    # 已发布记录拒绝重复发布
    consumer.bot.redis_manager.lpush(consumer._pending_key(), field)
    consumer._save_detail(field, {
        "source": "shun_fen_che", "unique_id": "abc123", "push_date": "2026-08-04",
        "field": field, "text": "x", "status": "pending", "updated_at": "",
    })
    ok3, msg3 = consumer.publish(field)
    check("已发布拒绝重复发布", not ok3 and "已发布" in msg3)
    consumer._local_remove(field)


def test_failed_stays_queued():
    print("\n[发布失败]")
    remote = MockRemoteRedis()
    local = MockLocalRedis()
    task_queue = MockTaskQueue()
    consumer = make_consumer(remote, local, task_queue)

    consumer._consume(sample_recruit())
    field = "recruitment:xyz789:2026-08-04"
    remote.status[field] = "QUEUED"  # 生产者入队时写入 QUEUED
    consumer.publish(field)
    task = task_queue.submitted[-1]
    task["callback"](True, {"status": "失败"}, task["params"])
    check("失败后远程保持 QUEUED", remote.status.get(field) == "QUEUED")
    check("失败后保留在池且状态 failed", consumer.get_pending()[0].get("status") == "failed")

    # failed 状态可再次发布
    ok, _ = consumer.publish(field)
    check("failed 可再次发布", ok)


def test_discard_and_repush():
    print("\n[丢弃 / 重推]")
    remote = MockRemoteRedis()
    local = MockLocalRedis()
    consumer = make_consumer(remote, local, MockTaskQueue())

    consumer._consume(sample_shun())
    field = "shun_fen_che:abc123:2026-08-04"
    remote.status[field] = "QUEUED"

    ok, _ = consumer.discard(field)
    check("丢弃成功", ok)
    check("丢弃后远程回执 PUBLISHED", remote.status.get(field) == "PUBLISHED")
    check("丢弃后移出待发布池", consumer.get_pending() == [])

    remote.status[field] = "QUEUED"
    consumer._consume(sample_shun())
    ok2, _ = consumer.re_push(field)
    check("重推成功", ok2)
    check("重推后远程回执被删除", field not in remote.status)
    check("重推后移出待发布池", consumer.get_pending() == [])

    # 记录不存在
    ok3, _ = consumer.re_push("no:such:record")
    check("重推不存在的记录被拒绝", not ok3)


def test_pool_cap():
    print("\n[待发布池容量上限]")
    remote = MockRemoteRedis()
    local = MockLocalRedis()
    consumer = make_consumer(remote, local, MockTaskQueue())
    consumer.bot.config.deal_queue_pending_max = 1

    # 预填池到上限
    consumer._consume(sample_shun())
    check("预填 1 条", len(consumer.get_pending()) == 1)

    # 队列里再来一条，启动线程轮询；应因池满不拉取
    remote.queue.append(json.dumps(sample_recruit()))
    consumer._running = True
    t = threading.Thread(target=consumer._loop, daemon=True)
    t.start()
    time.sleep(0.5)
    check("池满时远程队列未消费", len(remote.queue) == 1)
    check("池满时本地仍是 1 条", len(consumer.get_pending()) == 1)

    # 清空池 → 下轮消费
    consumer._local_remove("shun_fen_che:abc123:2026-08-04")
    time.sleep(0.5)
    check("池空后消费到新消息", len(consumer.get_pending()) == 1)
    check("池空后远程队列已消费", len(remote.queue) == 0)

    consumer._running = False
    t.join(timeout=3)


def test_auto_approve():
    print("\n[自动审核发布]")

    def make():
        remote = MockRemoteRedis()
        local = MockLocalRedis()
        tq = MockTaskQueue()
        consumer = make_consumer(remote, local, tq)
        consumer.bot.config.deal_queue_auto_approve_switch = True
        consumer.bot.config.deal_queue_auto_approve_delay = 60
        consumer.bot.config.deal_queue_publish_interval_min = 300
        consumer.bot.config.deal_queue_publish_interval_max = 600
        return remote, local, tq, consumer

    def set_entry_ts(consumer, field, seconds_ago):
        past = time.time() - seconds_ago
        consumer.bot.redis_manager.hset(
            consumer._detail_key(field), "updated_at",
            datetime.fromtimestamp(past).strftime("%Y-%m-%d %H:%M:%S"))

    # ---- 窗口期内不发 ----
    remote, local, tq, c = make()
    c._consume(sample_shun())
    field = "shun_fen_che:abc123:2026-08-04"
    remote.status[field] = "QUEUED"
    c._auto_publish_scan()
    check("窗口期内不自动发布", tq.submitted == [])
    check("窗口期内回执保持 QUEUED", remote.status.get(field) == "QUEUED")

    # ---- 窗口期后可发 ----
    set_entry_ts(c, field, 120)
    c._auto_publish_scan()
    check("窗口期后自动发布一条", len(tq.submitted) == 1)
    check("自动发布走 send_moments 任务", tq.submitted[-1]["type"] == "send_moments")
    check("自动发布后状态 publishing", c.get_pending()[0].get("status") == "publishing")

    # 成功回调 → next_publish 落在随机区间并持久化
    now0 = int(time.time())
    tq.submitted[-1]["callback"](True, {"status": "成功"}, tq.submitted[-1]["params"])
    check("自动发布成功后回执 PUBLISHED", remote.status.get(field) == "PUBLISHED")
    check("自动发布成功后移出池", c.get_pending() == [])
    nxt = c._read_next_publish()
    check("next_publish 已持久化", nxt > 0)
    check("next_publish 落在随机区间", now0 + 300 <= nxt <= now0 + 600)
    last = int(local.hget(c._auto_key(), "last_publish"))
    check("last_publish 已记录", last == now0)

    # ---- 随机间隔内不发（窗口已过但 next_publish 未到）----
    c._consume(sample_recruit())
    f2 = "recruitment:xyz789:2026-08-04"
    remote.status[f2] = "QUEUED"
    set_entry_ts(c, f2, 120)
    c._auto_publish_scan()
    check("随机间隔内不发布", len(tq.submitted) == 1)

    # ---- 重启后按持久化 next_publish 恢复节奏 ----
    remote2 = MockRemoteRedis()
    tq2 = MockTaskQueue()
    c2 = make_consumer(remote2, local, tq2)  # 重启共享同一本地 Redis（next_publish 仍在 local 中）
    c2.bot.config.deal_queue_auto_approve_switch = True
    c2.bot.config.deal_queue_auto_approve_delay = 60
    c2.bot.config.deal_queue_publish_interval_min = 300
    c2.bot.config.deal_queue_publish_interval_max = 600
    check("重启后读回持久化 next_publish", c2._read_next_publish() == nxt)
    c2._consume(sample_shun())
    f3 = "shun_fen_che:abc123:2026-08-04"
    remote2.status[f3] = "QUEUED"
    set_entry_ts(c2, f3, 120)
    c2._auto_publish_scan()
    check("重启后间隔内不连发", tq2.submitted == [])

    # ---- FIFO 最老优先 ----
    remote3, local3, tq3, c3 = make()
    msg_old = sample_shun()
    msg_old["unique_id"] = "old001"
    msg_new = sample_shun()
    msg_new["unique_id"] = "new002"
    c3._consume(msg_old)
    c3._consume(msg_new)
    f_old = "shun_fen_che:old001:2026-08-04"
    f_new = "shun_fen_che:new002:2026-08-04"
    remote3.status[f_old] = "QUEUED"
    remote3.status[f_new] = "QUEUED"
    set_entry_ts(c3, f_old, 120)
    set_entry_ts(c3, f_new, 120)
    c3._auto_publish_scan()
    check("FIFO 选中最老 pending 发布", len(tq3.submitted) == 1 and tq3.submitted[0]["params"].get("_receipt_field") == f_old)
    check("FIFO 一次迭代只发一条", len(tq3.submitted) == 1)

    # ---- 跳过 publishing / failed，仍发 pending ----
    remote4, local4, tq4, c4 = make()
    msg_f = sample_shun()
    msg_f["unique_id"] = "failed001"
    msg_p = sample_shun()
    msg_p["unique_id"] = "pub002"
    msg_ok = sample_shun()
    msg_ok["unique_id"] = "ok003"
    c4._consume(msg_f)
    c4._consume(msg_p)
    c4._consume(msg_ok)
    f_f = "shun_fen_che:failed001:2026-08-04"
    f_p = "shun_fen_che:pub002:2026-08-04"
    f_ok = "shun_fen_che:ok003:2026-08-04"
    for ff in (f_f, f_p, f_ok):
        remote4.status[ff] = "QUEUED"
        set_entry_ts(c4, ff, 120)
    # 最老 failed、次老 publishing、最新 pending
    c4.bot.redis_manager.hset(c4._detail_key(f_f), "status", "failed")
    c4.bot.redis_manager.hset(c4._detail_key(f_p), "status", "publishing")
    c4._auto_publish_scan()
    check("跳过 failed/publishing 发布最新 pending", len(tq4.submitted) == 1 and tq4.submitted[0]["params"].get("_receipt_field") == f_ok)
    check("与人工并发(publishing)被守卫挡住", len(tq4.submitted) == 1)

    # ---- 失败不重试 ----
    remote5, local5, tq5, c5 = make()
    c5._consume(sample_recruit())
    f5 = "recruitment:xyz789:2026-08-04"
    remote5.status[f5] = "QUEUED"
    c5.publish(f5)
    tq5.submitted[-1]["callback"](True, {"status": "失败"}, tq5.submitted[-1]["params"])
    check("失败后状态 failed", c5.get_pending()[0].get("status") == "failed")
    set_entry_ts(c5, f5, 120)
    c5._auto_publish_scan()
    check("失败记录不自动重试", len(tq5.submitted) == 1)

    # ---- 开关关闭：保持人工模式 ----
    remote6, local6, tq6, c6 = make()
    c6.bot.config.deal_queue_auto_approve_switch = False
    c6._consume(sample_shun())
    f6 = "shun_fen_che:abc123:2026-08-04"
    remote6.status[f6] = "QUEUED"
    set_entry_ts(c6, f6, 120)
    c6._auto_publish_scan()
    check("开关关闭不自动发布", tq6.submitted == [])


def main():
    print("=" * 50)
    print("同城信息消费者本地验证")
    print("=" * 50)
    test_renderer()
    test_publish_and_receipt()
    test_failed_stays_queued()
    test_discard_and_repush()
    test_pool_cap()
    test_auto_approve()
    print("\n" + "=" * 50)
    print(f"结果：通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
