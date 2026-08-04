"""同城信息（顺风车/招聘）Redis 队列消费者。

消费 we-mp-rss 推送的 `wemp:deal:push:queue`，经人工确认后通过任务队列发布朋友圈，
并按契约回报发布回执（`wemp:deal:push:status` → `PUBLISHED`）。

消费契约见 `we-mp-rss/docs/redis-deal-queue.md`。
"""

import json
import random
import re
import threading
import time
from datetime import datetime

from logger import log
from .redis_manager import RedisManager
from .task_queue import TaskQueue

QUEUE_KEY = "wemp:deal:push:queue"
STATUS_KEY = "wemp:deal:push:status"

# 远程队列连接默认参数（config 未提供时）
_DEFAULT_REMOTE = {
    "host": "122.51.49.63",
    "port": 6379,
    "db": 0,
    "password": None,
}


class DealQueueConsumer:
    """同城信息队列消费者。

    - 远程：自建 `RedisManager(fallback=False)` 专用于 RPOP 队列与回执读写。
    - 本地：待发布池存 bot 自身 `redis_manager`（127.0.0.1）。
    - 键位：
      - `wxbot:{wxid}:deal:pending` — LIST，元素为回执 field 字符串
      - `wxbot:{wxid}:deal:pending:{field}` — HASH：source/unique_id/push_date/field/text/status/updated_at
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self._remote = RedisManager(self._remote_config())
        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self._last_warn_ts = 0.0  # 告警日志节流

    # ------------------------------------------------------------
    # 连接与键
    # ------------------------------------------------------------
    def _remote_config(self):
        cfg = self.config
        return {
            "host": getattr(cfg, "deal_queue_redis_host", None) or _DEFAULT_REMOTE["host"],
            "port": int(getattr(cfg, "deal_queue_redis_port", _DEFAULT_REMOTE["port"]) or _DEFAULT_REMOTE["port"]),
            "db": int(getattr(cfg, "deal_queue_redis_db", _DEFAULT_REMOTE["db"]) or _DEFAULT_REMOTE["db"]),
            "password": getattr(cfg, "deal_queue_redis_password", None) or None,
            "timeout": getattr(cfg, "redis_timeout", 5),
            "retry_count": 2,
            "fallback": False,
            "fallback_path": "./fallback_redis.json",
        }

    def _wx_id(self):
        """当前微信昵称，未登录时用 default（与 task_queue 一致）。"""
        return getattr(getattr(self.bot, "wx", None), "nickname", None) or "default"

    def _pending_key(self):
        return f"wxbot:{self._wx_id()}:deal:pending"

    def _detail_key(self, field):
        return f"wxbot:{self._wx_id()}:deal:pending:{field}"

    def _save_detail(self, field, detail):
        """把详情字段逐项写入本地 Hash（与 hgetall 读回一致）。"""
        key = self._detail_key(field)
        for k, v in detail.items():
            self.bot.redis_manager.hset(key, k, v)

    def _auto_key(self):
        """本地自动发布节奏键：HASH（next_publish/last_publish，int 秒时间戳）。"""
        return f"wxbot:{self._wx_id()}:deal:auto"

    def _read_next_publish(self):
        """读取下次自动发布最早时刻；missing/非法视为 0。"""
        try:
            val = self.bot.redis_manager.hget(self._auto_key(), "next_publish")
        except Exception as e:
            log(level="WARNING", message=f"同城信息消费者读取发布节奏失败：{e}")
            return 0
        try:
            return int(val or 0)
        except (TypeError, ValueError):
            return 0

    def _write_next_publish(self, last, next_publish):
        """持久化上次/下次自动发布时刻（int 秒时间戳）。"""
        try:
            key = self._auto_key()
            self.bot.redis_manager.hset(key, "last_publish", last)
            self.bot.redis_manager.hset(key, "next_publish", next_publish)
        except Exception as e:
            log(level="WARNING", message=f"同城信息消费者写入发布节奏失败：{e}")

    def _entry_ts(self, detail):
        """详情 `updated_at`（入池时刻字符串）转 int 秒时间戳；缺失/非法视为 0。"""
        ts = (detail or {}).get("updated_at")
        if not ts:
            return 0
        try:
            return datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            return 0

    def is_remote_ready(self):
        """远程 Redis 是否可用。"""
        try:
            return self._remote.is_available()
        except Exception:
            return False

    # ------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------
    _NOISE = {"未提及", "未知", "无", "暂无", "null", "none"}

    def _kv_lines(self, items):
        """把非空字段渲染为「标签：值」行；None/空串/占位噪音值跳过。"""
        out = []
        for label, value in items:
            if value is None:
                continue
            s = str(value).strip().strip("：:，,。 ")
            if not s or s.lower() in ("null", "none") or s in self._NOISE:
                continue
            out.append(f"{label}：{s}")
        return out

    # 各 type 标题组成：按优先级取第一个有意义的字段（title 不一定是首选）
    _RECRUIT_HEADERS = {
        "招聘": ["title", "corp"],
        "求职": ["recruitment_jobs", "title", "address"],
        "出售": ["corp", "title"],
        "求购": ["corp", "title"],
        "出租": ["title", "corp", "address"],
        "求租": ["corp", "title", "address"],
        "转让": ["title", "corp"],
        "领养": ["title", "corp"],
        "回收": ["title", "corp"],
        "寻找技能服务": ["title", "subject_params", "corp"],
        "其他": ["title", "recruitment_jobs", "corp"],
    }

    # 各 type 字段模板（content 缺失时兜底）：标签 -> 字段名（电话固定最后拼）
    _RECRUIT_TEMPLATES = {
        "招聘": [("公司", "corp"), ("地点", "address"), ("薪资", "price"),
                ("职位", "recruitment_jobs"), ("技能要求", "job_skills"),
                ("学历", "education"), ("联系人", "contact_person")],
        "求职": [("意向岗位", "recruitment_jobs"), ("技能", "job_skills"),
                ("学历", "education"), ("期望地区", "address"), ("联系人", "contact_person")],
        "出售": [("物品", "corp"), ("价格", "price"), ("地点", "address"),
                ("详情", "subject_params"), ("联系人", "contact_person")],
        "求购": [("求购物品", "corp"), ("预算", "price"), ("地点", "address"),
                ("要求", "subject_params"), ("联系人", "contact_person")],
        "出租": [("出租物", "corp"), ("租金", "price"), ("地址", "address"),
                ("详情", "subject_params"), ("联系人", "contact_person")],
        "求租": [("求租物", "corp"), ("预算", "price"), ("地址", "address"),
                ("要求", "subject_params"), ("联系人", "contact_person")],
        "转让": [("转让物", "corp"), ("价格", "price"), ("地址", "address"),
                ("详情", "subject_params"), ("联系人", "contact_person")],
        "领养": [("对象", "corp"), ("费用", "price"), ("地址", "address"),
                 ("详情", "subject_params"), ("联系人", "contact_person")],
        "回收": [("对象", "corp"), ("地址", "address"), ("联系人", "contact_person")],
        "寻找技能服务": [("需求", "subject_params"), ("地址", "address"), ("联系人", "contact_person")],
    }

    def render(self, msg):
        """把消息渲染为纯文本朋友圈文案；无法识别的 source 返回空串。

        - 顺风车：直接发 `original_content` 原文。
        - recruitment：标题按 `type` 组合 + 原始 `content` 全文；content 缺失退回字段模板。
        """
        source = msg.get("source")

        if source == "shun_fen_che":
            text = str(msg.get("original_content") or "").strip()
            if not text:
                return ""
            lines = [text]
        elif source == "recruitment":
            lines = self._render_recruitment(msg)
            if not lines:
                return ""
        else:
            return ""

        text = "\n".join(line for line in lines if line.strip()).strip()
        prefix = (getattr(self.config, "deal_queue_moments_prefix", "") or "").strip()
        if prefix:
            text = prefix + "\n" + text
        max_len = int(getattr(self.config, "deal_queue_moments_max_len", 2000) or 2000)
        if len(text) > max_len:
            text = text[:max_len]
        return text

    def _render_recruitment(self, msg):
        """recruitment：按 type 组合标题 + 原始 content 全文；content 缺失退回字段模板。"""
        rtype = str(msg.get("type") or "").strip() or "其他"

        header = f"【{rtype}】"
        for key in self._RECRUIT_HEADERS.get(rtype, ["title"]):
            v = str(msg.get(key) or "").strip().strip("：:，,。 ")
            if v and v != rtype and v not in self._NOISE:
                header += v
                break

        content = str(msg.get("content") or "").strip()
        if content:
            lines = [header]
            lines += [ln.strip() for ln in content.splitlines() if ln.strip()]
            phone = str(msg.get("phone") or "").strip()
            # 号码按分隔符拆片段，content 已含任意号码片段则不重复追加
            if phone and phone not in self._NOISE:
                frags = [f for f in re.split(r"[，,、;；/ ]", phone) if f]
                if frags and not any(f in content for f in frags):
                    lines.append(f"电话：{phone}")
            return lines

        fields = self._RECRUIT_TEMPLATES.get(rtype)
        if fields is None:
            fields = [("标题", "title"), ("公司", "corp"), ("地点", "address"),
                      ("职位", "recruitment_jobs"), ("联系人", "contact_person")]
        lines = [header]
        lines += self._kv_lines([(label, msg.get(key)) for label, key in fields])
        lines += self._kv_lines([("电话", msg.get("phone"))])
        return lines

    # ------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------
    def _start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="deal-queue-consumer")
            self._thread.start()
            log(message="同城信息消费者线程已启动")

    def _stop(self):
        with self._lock:
            self._running = False
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=5)
        log(message="同城信息消费者线程已停止")

    def check(self):
        """主循环每轮调用：按总开关启停消费线程。"""
        try:
            switch = bool(getattr(self.config, "deal_queue_consumer_switch", False))
            if switch:
                self._start()
            else:
                self._stop()
        except Exception as e:
            log(level="ERROR", message=f"同城信息消费者 check 出错：{e}")

    def stop(self):
        """停止消费者线程并关闭远程连接。"""
        self._stop()
        try:
            self._remote.close()
        except Exception as e:
            log(level="ERROR", message=f"同城信息消费者关闭远程连接失败：{e}")

    def _throttle_log(self, message):
        now = time.time()
        if now - self._last_warn_ts >= 60:
            self._last_warn_ts = now
            log(level="WARNING", message=message)

    def _loop(self):
        while self._running:
            try:
                interval = int(getattr(self.config, "deal_queue_poll_interval", 5) or 5)
                if not self.is_remote_ready():
                    self._throttle_log("同城信息消费者：远程 Redis 不可用，稍后重试")
                    time.sleep(interval)
                    continue

                # 自动审核发布不依赖待发布池容量：池满时正是需要自动发布来腾出空间，
                # 因此放在 pending_max 检查之前，避免池满 continue 时跳过自动发布。
                if bool(getattr(self.config, "deal_queue_auto_approve_switch", False)):
                    try:
                        self._auto_publish_scan()
                    except Exception as e:
                        log(level="ERROR", message=f"同城信息消费者自动审核扫描出错：{e}")

                pending_max = int(getattr(self.config, "deal_queue_pending_max", 500) or 500)
                try:
                    pending_len = int(self.bot.redis_manager.llen(self._pending_key()) or 0)
                except Exception:
                    pending_len = 0
                if pending_len >= pending_max:
                    self._throttle_log(
                        f"同城信息消费者：待发布池已达上限 {pending_max}，暂停拉取，请人工处理"
                    )
                    time.sleep(interval)
                    continue

                raw = self._remote.rpop(QUEUE_KEY)
                if raw is not None:
                    msg = raw if isinstance(raw, dict) else json.loads(raw)
                    self._consume(msg)

                time.sleep(interval)
            except Exception as e:
                log(level="ERROR", message=f"同城信息消费者线程出错：{e}")
                time.sleep(5)

    def _consume(self, msg):
        if not isinstance(msg, dict):
            return
        source = msg.get("source")
        unique_id = msg.get("unique_id")
        push_date = msg.get("push_date")
        if not source or not unique_id or not push_date:
            return
        field = f"{source}:{unique_id}:{push_date}"

        # 已发布则丢弃（防并发重复发布，契约 §4）
        try:
            remote_status = self._remote.hget(STATUS_KEY, field)
            if remote_status == "PUBLISHED":
                return
        except Exception as e:
            log(level="WARNING", message=f"同城信息消费者查询回执失败，仍入池：{field}（{e}）")

        text = self.render(msg)
        if not text:
            log(level="WARNING", message=f"同城信息消费者：无法渲染消息，跳过 {field}")
            return

        detail = {
            "source": source,
            "unique_id": str(unique_id),
            "push_date": str(push_date),
            "field": field,
            "text": text,
            "status": "pending",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.bot.redis_manager.lpush(self._pending_key(), field)
        self._save_detail(field, detail)
        log(message=f"同城信息消费者：{source} 消息已入待发布池 {field}")

    # ------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------
    def get_pending(self):
        """待发布池列表（按入池时间倒序）。"""
        fields = self.bot.redis_manager.lrange(self._pending_key(), 0, -1) or []
        if not isinstance(fields, list):
            fields = []
        items = []
        for field in fields:
            detail = self.bot.redis_manager.hgetall(self._detail_key(field))
            if detail:
                items.append(detail)
            else:
                items.append({"field": field, "status": "pending"})
        return items

    def get_stats(self):
        """待发布池统计 + 远程队列长度。"""
        items = self.get_pending()
        pending = sum(1 for d in items if d.get("status") == "pending")
        publishing = sum(1 for d in items if d.get("status") == "publishing")
        failed = sum(1 for d in items if d.get("status") == "failed")
        remote_len = -1
        if self.is_remote_ready():
            try:
                remote_len = int(self._remote.llen(QUEUE_KEY) or 0)
            except Exception:
                remote_len = -1
        return {
            "pending_count": pending,
            "publishing_count": publishing,
            "failed_count": failed,
            "total_count": len(items),
            "remote_len": remote_len,
            "remote_ready": self.is_remote_ready(),
            "next_publish": self._read_next_publish(),
        }

    # ------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------
    def _auto_publish_scan(self):
        """自动审核发布：从池尾（最老）起找第一条 `pending`，满足时间条件则发布一条。

        判定：`now >= entry.updated_at + deal_queue_auto_approve_delay` 且 `now >= next_publish`。
        一次迭代最多发一条，返回失败静默跳过；任何异常不打断消费主循环。
        """
        if not bool(getattr(self.config, "deal_queue_auto_approve_switch", False)):
            return
        try:
            fields = self.bot.redis_manager.lrange(self._pending_key(), 0, -1) or []
        except Exception as e:
            log(level="WARNING", message=f"同城信息消费者自动审核读取待发布池失败：{e}")
            return
        if not isinstance(fields, list) or not fields:
            return

        delay = int(getattr(self.config, "deal_queue_auto_approve_delay", 60) or 0)
        next_publish = self._read_next_publish()
        now = int(time.time())

        for field in reversed(fields):
            try:
                detail = self.bot.redis_manager.hgetall(self._detail_key(field)) or {}
            except Exception as e:
                log(level="WARNING", message=f"同城信息消费者自动审核读取详情失败：{field}（{e}）")
                continue
            if str(detail.get("status") or "pending") != "pending":
                continue
            if now < self._entry_ts(detail) + delay:
                continue
            if now < next_publish:
                return
            ok, msg = self.publish(field)
            if ok:
                log(message=f"同城信息消费者：自动审核已发布 {field}")
            else:
                log(level="WARNING", message=f"同城信息消费者：自动审核发布跳过 {field}（{msg}）")
            return  # 一次迭代最多发一条

    def publish(self, field):
        """人工确认发布：提交 send_moments 任务，成功回调才回报 PUBLISHED。"""
        detail = self.bot.redis_manager.hgetall(self._detail_key(field))
        if not detail:
            return False, "记录不存在"
        if detail.get("status") == "publishing":
            return False, "该记录正在发布中"
        if not self.is_remote_ready():
            return False, "远程 Redis 不可用"
        try:
            remote_status = self._remote.hget(STATUS_KEY, field)
            if remote_status == "PUBLISHED":
                return False, "该记录已发布，请勿重复操作"
        except Exception as e:
            return False, f"查询回执失败：{e}"

        detail["status"] = "publishing"
        detail["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_detail(field, detail)

        params = {
            "text": detail.get("text", ""),
            "images": [],
            "privacy": getattr(self.config, "deal_queue_privacy", "public") or "public",
            "tags": [],
            "_receipt_field": field,
        }
        try:
            self.bot.task_queue.submit(
                "send_moments", params, priority=5, callback=self._on_publish_result
            )
        except Exception as e:
            detail["status"] = "pending"
            detail["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_detail(field, detail)
            log(level="ERROR", message=f"同城信息消费者提交发布任务失败：{field}（{e}）")
            return False, f"提交发布任务失败：{e}"
        log(message=f"同城信息消费者已提交发布：{field}")
        return True, "已提交发布"

    def _on_publish_result(self, success, result, params):
        """send_moments 任务回调：仅在真正发出后写 PUBLISHED 并移出待发布池。"""
        field = (params or {}).get("_receipt_field")
        if not field:
            return
        # send_moments 处理器不抛异常，需自行判定界面返回是否成功
        actually_ok = bool(success) and bool(TaskQueue._result_is_success(result))
        if actually_ok:
            try:
                self._remote.hset(STATUS_KEY, field, "PUBLISHED")
                log(message=f"同城信息消费者：{field} 已发布，回执已回报 PUBLISHED")
            except Exception as e:
                log(level="ERROR", message=f"同城信息消费者回报回执失败：{field}（{e}）")
            self._local_remove(field)
            now = int(time.time())
            itv_min = int(getattr(self.config, "deal_queue_publish_interval_min", 300) or 300)
            itv_max = int(getattr(self.config, "deal_queue_publish_interval_max", 600) or 600)
            if itv_max < itv_min:
                itv_max = itv_min
            self._write_next_publish(now, now + random.randint(itv_min, itv_max))
        else:
            detail = self.bot.redis_manager.hgetall(self._detail_key(field))
            if detail:
                detail["status"] = "failed"
                detail["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_detail(field, detail)
            log(level="ERROR", message=f"同城信息消费者：{field} 发布失败，保留在待发布池（success={success} result={result}）")

    def discard(self, field):
        """人工丢弃：远程回执置 PUBLISHED（放弃发布），本地清理。"""
        detail = self.bot.redis_manager.hgetall(self._detail_key(field))
        if not detail:
            return False, "记录不存在"
        if not self.is_remote_ready():
            return False, "远程 Redis 不可用"
        try:
            self._remote.hset(STATUS_KEY, field, "PUBLISHED")
        except Exception as e:
            return False, f"写回执失败：{e}"
        self._local_remove(field)
        log(message=f"同城信息消费者：{field} 已丢弃（回执置 PUBLISHED）")
        return True, "已丢弃"

    def re_push(self, field):
        """人工重推：删除远程回执 field，生产者下次轮询将重新入队。"""
        detail = self.bot.redis_manager.hgetall(self._detail_key(field))
        if not detail:
            return False, "记录不存在"
        if not self.is_remote_ready():
            return False, "远程 Redis 不可用"
        try:
            self._remote.hdel(STATUS_KEY, field)
        except Exception as e:
            return False, f"删除回执失败：{e}"
        self._local_remove(field)
        log(message=f"同城信息消费者：{field} 已重推（回执已删除，生产者将重新入队）")
        return True, "已重推"

    def _local_remove(self, field):
        """从本地待发布池移除记录（列表元素 + 详情 Hash）。"""
        try:
            self.bot.redis_manager.lrem(self._pending_key(), 0, field)
        except Exception as e:
            log(level="WARNING", message=f"同城信息消费者本地移除列表失败：{field}（{e}）")
        try:
            self.bot.redis_manager.delete(self._detail_key(field))
        except Exception as e:
            log(level="WARNING", message=f"同城信息消费者本地删除详情失败：{field}（{e}）")
