"""集中式配置字段强制器。

每个配置字段只需在 `FIELD_HANDLERS` 集中登记一次。暴露五个 `coerce_*_fields`
函数，分别对应原 web_server 中 `_coerce_bool/list/float/int_range/dict_fields`，
由调用方保持原有的「按调用点选子集」顺序（save_config 全跑；save_config_route 不含 int_range）。

新增面板配置开关字段：1) 在此表补一行登记；2) 前端模板加对应控件（唯一另做处）。
"""

import json


# 各字段对应的强制处理器类型。
#   bool        -> 按字符串 on/true/1 或 bool() 归一
#   list        -> 字符串 → 单元素列表；逐项剔空
#   float       -> (lo, hi, default) 限区间，非法回退默认
#   int         -> (lo, hi, default) 限区间，非法回退默认
#   dict_*      -> dict 收敛器（见 _DICT_HANDLERS）
FIELD_HANDLERS = {
    # ---------- 布尔开关 ----------
    'AllListen_switch': 'bool',
    'AllListen_filter_mute': 'bool',
    'chat_listen_only': 'bool',
    'group_switch': 'bool',
    'group_listen_only': 'bool',
    'group_reply_at': 'bool',
    'group_reply_at_msg': 'bool',
    'group_reply_quote': 'bool',
    'group_welcome': 'bool',
    'new_friend_switch': 'bool',
    'new_friend_reply_switch': 'bool',
    'new_friend_remark_use_nickname': 'bool',
    'new_friend_remark_prefix_timestamp': 'bool',
    'new_friend_remark_suffix_timestamp': 'bool',
    'chat_keyword_switch': 'bool',
    'group_keyword_switch': 'bool',
    'group_keyword_at_only': 'bool',
    'scheduled_msg_switch': 'bool',
    'random_msg_switch': 'bool',
    'scheduled_moments_switch': 'bool',
    'moments_like_switch': 'bool',
    'random_moments_switch': 'bool',
    'everyday_start_stop_bot_switch': 'bool',
    'memory_switch': 'bool',
    'reply_delay_switch': 'bool',
    'clean_ai_reply_switch': 'bool',
    'chat_image_recognition_switch': 'bool',
    'group_image_recognition_switch': 'bool',
    'custom_forward_switch': 'bool',
    'chat_split_reply_switch': 'bool',
    'group_split_reply_switch': 'bool',
    'siver_panel_enabled': 'bool',
    'api_error_reply_once': 'bool',
    'chat_max_round_switch': 'bool',
    'chat_max_round_reply_once': 'bool',

    # ---------- 列表 ----------
    'listen_list': 'list',
    'group': 'list',
    'new_friend_msg': 'list',
    'new_friend_tags': 'list',
    'scheduled_msg_list': 'list',
    'random_msg_list': 'list',
    'scheduled_moments_list': 'list',
    'random_moments_list': 'list',
    'custom_forward_list': 'list',

    # ---------- 浮点区间 ----------
    'group_welcome_random': ('float', 0.0, 1.0, 1.0),

    # ---------- 整型区间 ----------
    'new_friend_check_min': ('int', 60, 3600, 60),
    'new_friend_check_max': ('int', 60, 3600, 300),
    'chat_max_round_default': ('int', 1, 99999, 99),
    'chat_max_round_reset_days': ('int', 0, 365, 0),

    # ---------- 字典 ----------
    'keyword_dict': 'dict_keywords',
    'group_api_map': 'dict_int_nonneg',
    'chat_api_map': 'dict_int_minus1',
    'chat_max_round_map': 'dict_int_round',
    'chat_prompt_map': 'dict_nonempty_str',
    'group_prompt_map': 'dict_nonempty_str',
}


def _coerce_bool(merged_config, field):
    v = merged_config[field]
    if isinstance(v, str):
        merged_config[field] = v.lower() in ('on', 'true', '1')
    else:
        merged_config[field] = bool(v)


def _coerce_list(merged_config, field):
    if not isinstance(merged_config[field], list):
        if isinstance(merged_config[field], str):
            merged_config[field] = [merged_config[field]] if merged_config[field] else []
        else:
            merged_config[field] = []
    merged_config[field] = [item for item in merged_config[field] if str(item).strip()]


def _coerce_float(merged_config, field, lo, hi, default):
    try:
        val = float(merged_config[field])
        merged_config[field] = max(lo, min(hi, val))
    except (TypeError, ValueError):
        merged_config[field] = default


def _coerce_int(merged_config, field, lo, hi, default):
    try:
        val = int(merged_config[field])
        merged_config[field] = max(lo, min(hi, val))
    except (TypeError, ValueError):
        merged_config[field] = default


def _read_json_dict(value):
    try:
        obj = json.loads(value)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _coerce_dict_keywords(merged_config, field):
    kd = merged_config[field]
    if isinstance(kd, str):
        obj = _read_json_dict(kd)
        if obj is not None:
            merged_config[field] = obj
            kd = obj
    if isinstance(kd, list):
        out = {}
        for item in kd:
            if isinstance(item, dict):
                key = str(item.get('key', '')).strip()
                val = str(item.get('value', ''))
                if key:
                    out[key] = val
        merged_config[field] = out
        kd = out
    if not isinstance(merged_config[field], dict):
        merged_config[field] = {}


def _coerce_dict_int_map(merged_config, field, allow_negative):
    raw = merged_config[field]
    if isinstance(raw, dict):
        clean = {}
        for k, v in raw.items():
            k = str(k).strip()
            try:
                vi = int(v)
                if k and vi >= allow_negative:
                    clean[k] = vi
            except (ValueError, TypeError):
                pass
        merged_config[field] = clean
    else:
        merged_config[field] = {}


def _coerce_dict_round_map(merged_config, field):
    raw = merged_config[field]
    if isinstance(raw, dict):
        clean = {}
        for k, v in raw.items():
            k = str(k).strip()
            try:
                vi = int(v)
                if k:
                    clean[k] = max(1, min(99999, vi))
            except (ValueError, TypeError):
                pass
        merged_config[field] = clean
    else:
        merged_config[field] = {}


def _coerce_dict_str_map(merged_config, field):
    raw = merged_config[field]
    if isinstance(raw, dict):
        clean = {}
        for k, v in raw.items():
            k = str(k).strip()
            v = str(v).strip()
            if k and v:
                clean[k] = v
        merged_config[field] = clean
    else:
        merged_config[field] = {}


_DICT_HANDLERS = {
    'dict_keywords': _coerce_dict_keywords,
    'dict_int_nonneg': lambda cfg, f: _coerce_dict_int_map(cfg, f, 0),
    'dict_int_minus1': lambda cfg, f: _coerce_dict_int_map(cfg, f, -1),
    'dict_int_round': _coerce_dict_round_map,
    'dict_nonempty_str': _coerce_dict_str_map,
}


def _iter_fields(rule):
    for field, r in FIELD_HANDLERS.items():
        if r == rule:
            yield field


def coerce_bool_fields(merged_config):
    for field in _iter_fields('bool'):
        if field in merged_config:
            _coerce_bool(merged_config, field)


def coerce_list_fields(merged_config):
    for field in _iter_fields('list'):
        if field in merged_config:
            _coerce_list(merged_config, field)


def coerce_float_fields(merged_config, original_config=None):
    for field, rule in FIELD_HANDLERS.items():
        if not isinstance(rule, tuple) or rule[0] != 'float' or field not in merged_config:
            continue
        kind, lo, hi, default = rule
        # 非法值回退：优先取原配置中的现值，其次用表中 default
        fallback = default
        if original_config and field in original_config:
            try:
                fallback = float(original_config[field])
            except (TypeError, ValueError):
                fallback = default
        _coerce_float(merged_config, field, lo, hi, fallback)


def coerce_int_range_fields(merged_config):
    for field, rule in FIELD_HANDLERS.items():
        if not isinstance(rule, tuple) or rule[0] != 'int' or field not in merged_config:
            continue
        kind, lo, hi, default = rule
        _coerce_int(merged_config, field, lo, hi, default)


def coerce_dict_fields(merged_config):
    for field, rule in FIELD_HANDLERS.items():
        if rule in _DICT_HANDLERS and field in merged_config:
            _DICT_HANDLERS[rule](merged_config, field)