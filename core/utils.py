import re
import time
import random
from datetime import datetime


SPLIT_SEPARATOR = "||SPLIT||"

SPLIT_PROMPT_TEMPLATE = """\
【回复格式要求】
你的回复将直接发送到即时通讯软件（如微信），请模仿真人聊天可能会拆分多条发送的风格，
你可以自行决定是否将回复拆分为多条消息，以及拆分几条，无需强制拆分。
约束：每条不超过 {max_chars} 字，总条数不超过 {max_count} 条。
若需拆分，在每条消息之间用以下分隔符单独占一行隔开：
||SPLIT||

例如：
好的，我来解释一下。
||SPLIT||
这个问题其实很常见，主要原因是……
||SPLIT||
你可以试试这个方法。

若无需拆分则正常回复，不要添加任何分隔符。
严禁在正文内容中出现 ||SPLIT|| 字样。
如果你想分条回复，一定一定一定要在每个分条直接加上这个分隔符||SPLIT||，不然程序无法处理分条发送。
如果你要换2行来进行分段回复，那请将换两行这个操作改成用分隔符回复的分条回复，以下是示例：
原始内容：
好的，我来解释一下。

这个问题其实很常见，主要原因是……

改动后内容：
好的，我来解释一下。
||SPLIT||
这个问题其实很常见，主要原因是……
【以下是你的角色设定】
{base_prompt}"""


THINK_BLOCK_RE = re.compile(r'<think\b[^>]*>.*?</think>', re.IGNORECASE | re.DOTALL)
LEADING_THINK_RE = re.compile(r'^\s*<think\b[^>]*>', re.IGNORECASE)


def clean_ai_reply_text(text):
    """清理模型回复中的思考标签，避免把推理过程发送给用户。"""
    if text is None:
        return ""
    text = str(text)
    cleaned = THINK_BLOCK_RE.sub("", text)
    removed_think = cleaned != text

    if LEADING_THINK_RE.search(cleaned):
        tail_match = re.search(r'\n\s*\n', cleaned)
        if tail_match:
            cleaned = cleaned[tail_match.end():]
        else:
            cleaned = ""

    lines = [line.rstrip() for line in cleaned.splitlines()]
    cleaned = "\n".join(lines).strip()
    if removed_think:
        cleaned = re.sub(r'\n\s*\n+', '\n', cleaned)
    return cleaned


def now_time(time_format="%Y/%m/%d %H:%M:%S "):
    """获取当前时间字符串（当前暂由公共 log 模块显示时间，此处返回空串）"""
    return ""
    return datetime.now().strftime(time_format)


def split_long_text(text, chunk_size=2000):
    """将超长文本按指定长度切分为列表，用于分段发送"""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def _normalize_chat_max_round_map(raw_map):
    """清洗私聊白名单用户的专属回复轮数上限配置"""
    if not isinstance(raw_map, dict):
        return {}
    clean = {}
    for name, value in raw_map.items():
        name = str(name).strip()
        if not name:
            continue
        try:
            value = int(value)
        except Exception:
            continue
        clean[name] = max(1, min(99999, value))
    return clean


def _coerce_int_range(value, default, min_value, max_value):
    """将配置值转为指定范围内的整数"""
    try:
        value = int(value)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def human_delay(reply_delay_switch, reply_delay_min, reply_delay_max):
    """模拟人工操作随机延迟。reply_delay_switch 关闭时直接跳过。"""
    if not reply_delay_switch:
        return
    lo = min(reply_delay_min, reply_delay_max)
    hi = max(reply_delay_min, reply_delay_max)
    time.sleep(random.randint(lo, hi))


def get_run_time(start_time):
    """计算并返回自 start_time 至今的运行时长，格式：X天X时X分X秒"""
    delta = datetime.now() - start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}天{hours}时{minutes}分{seconds}秒"
