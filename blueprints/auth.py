"""域2：鉴权 / 登录 / 安全头 / 登录限流 / dashboard 渲染。

共享辅助函数驻留 web_server，此处惰性 `import web_server as ws` 引用。
"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("auth", __name__)


@bp.route("/api/check_auth")
def check_auth():
    from flask import jsonify, session
    return jsonify({"authenticated": session.get("logged_in", False)})


@bp.route("/", methods=["GET", "POST"])
def login():
    from flask import request, render_template, redirect, session
    if session.get("logged_in"):
        return redirect(ws.absolute_url_for("auth.dashboard"))
    logout_success = request.args.get("logout") == "success"
    error = None

    if request.method == "POST":
        client_ip = ws.get_client_ip()
        blocked, remaining = ws.is_login_ip_banned(client_ip)
        if blocked:
            ws.log("WARNING", f"登录被拒绝：IP {client_ip} 仍处于封禁期，剩余 {remaining}s")
            return render_template("login.html", error=f"登录失败次数过多，请 {remaining} 秒后再试", logout_success=logout_success)

        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if username == ws.USERS["username"] and ws.verify_password(password, ws.USERS["password_hash"]):
            ws.clear_login_failures(client_ip)
            session["logged_in"] = True
            session["username"] = username
            session.permanent = True
            ws.log("SUCCESS", f"用户 {username} 登录成功")
            next_page = request.args.get("next") or ws.absolute_url_for("auth.dashboard")
            if not ws.is_safe_redirect_target(next_page):
                next_page = ws.absolute_url_for("auth.dashboard")
            return redirect(next_page)
        else:
            ws.record_login_failure(client_ip)
            ws.log("WARNING", f"登录失败: 用户名或密码错误 (用户名: {username})")
            return render_template("login.html", error="用户名或密码错误")

    return render_template("login.html", error=error, logout_success=logout_success)


@bp.route("/logout")
def logout():
    from flask import session, redirect
    session.clear()
    session.pop("logged_in", None)
    session.pop("username", None)
    return redirect(ws.absolute_url_for("auth.login"))


@bp.route("/dashboard")
@ws.login_required
def dashboard(**kwargs):
    import json
    import os
    from flask import render_template, jsonify, request

    _ = (jsonify, request)
    config = ws.read_config()
    if not config:
        return render_template("error.html", message="无法读取配置文件")

    # 旧配置迁移：只要旧字段存在就迁移并写回磁盘（无论 api_configs 是否已有）
    if "api_sdk" in config:
        config["api_configs"] = [
            {"sdk": config.get("api_sdk", ""), "key": config.get("api_key", ""),
             "url": config.get("base_url", ""), "model": config.get("model1", "")},
            {"sdk": config.get("api_sdk", ""), "key": config.get("api_key", ""),
             "url": config.get("base_url", ""), "model": config.get("model2", "")},
        ]
        config["api_index"] = 0
        for old_key in ("api_sdk", "api_key", "base_url", "model1", "model2", "api_sdk_list"):
            config.pop(old_key, None)
        try:
            with open(ws.CONFIG_FILE, "w", encoding="utf-8") as _f:
                json.dump(config, _f, ensure_ascii=False, indent=4)
            ws.log("SUCCESS", "旧 API 配置已自动迁移为新格式并保存")
        except Exception as _e:
            ws.log("ERROR", f"迁移配置写入失败: {_e}")
    config.setdefault("api_configs", [
        {"sdk": "", "key": "", "url": "", "model": ""},
        {"sdk": "", "key": "", "url": "", "model": ""},
    ])
    config.setdefault("api_index", 0)

    for _k, _v in [
        ("group_api_map", {}), ("group_welcome_random", 1.0),
        ("chat_listen_only", False), ("group_listen_only", False),
        ("chat_keyword_switch", False), ("group_keyword_switch", False),
        ("group_keyword_at_only", False), ("keyword_dict", {}),
        ("scheduled_msg_switch", config.get("everyday_msg_switch", False)),
        ("scheduled_msg_list", []), ("scheduled_moments_switch", False),
        ("scheduled_moments_list", []), ("moments_like_switch", False),
        ("moments_like_min", 60), ("moments_like_max", 120),
        ("random_moments_switch", False), ("random_moments_list", []),
    ]:
        config.setdefault(_k, _v)

    # 旧配置迁移：everyday_msg_dict -> scheduled_msg_list
    if not config.get("scheduled_msg_list") and config.get("everyday_msg_dict"):
        import uuid
        migrated = []
        for target, tasks in config.get("everyday_msg_dict", {}).items():
            for task in tasks:
                migrated.append({
                    "id": str(uuid.uuid4())[:8],
                    "enabled": True,
                    "targets": [target],
                    "time": task.get("time", "08:00"),
                    "repeat_type": "daily",
                    "weekdays": [],
                    "dates": [],
                    "msgs": task.get("msgs", []),
                })
        config["scheduled_msg_list"] = migrated
    # 旧配置迁移：target(str) -> targets(list)
    _target_migrated = False
    for task in config.get("scheduled_msg_list", []):
        if "targets" not in task:
            old = task.pop("target", "")
            task["targets"] = [old] if old else []
            _target_migrated = True
    if _target_migrated:
        try:
            with open(ws.CONFIG_FILE, "w", encoding="utf-8") as _f:
                json.dump(config, _f, ensure_ascii=False, indent=4)
            ws.log("SUCCESS", "定时消息发送目标格式已自动迁移 target -> targets")
        except Exception as _e:
            ws.log("ERROR", f"迁移定时消息目标格式写入失败: {_e}")
    for _k, _v in [
        ("everyday_start_stop_bot_switch", False), ("everyday_start_bot_time", "08:00"),
        ("everyday_stop_bot_time", "23:00"), ("memory_switch", True),
        ("memory_max_count", 3000), ("memory_context_count", 1000),
        ("reply_delay_switch", True), ("reply_delay_min", 1), ("reply_delay_max", 5),
        ("clean_ai_reply_switch", True), ("new_friend_remark_use_nickname", True),
        ("new_friend_remark_prefix_timestamp", False), ("new_friend_remark_suffix_timestamp", False),
        ("chat_image_recognition_switch", False), ("chat_image_recognition_api", 0),
        ("group_image_recognition_switch", False), ("group_image_recognition_api", 0),
        ("custom_forward_switch", False), ("custom_forward_list", []),
    ]:
        config.setdefault(_k, _v)

    for _k, _v in [
        ("siver_panel_enabled", False), ("siver_panel_activation_code", ""),
        ("siver_panel_activation_code_applied_hash", ""), ("siver_panel_activation_code_failed_hash", ""),
        ("siver_panel_slug", ""), ("siver_panel_install_id", ""),
        ("siver_panel_machine_fingerprint", ""), ("siver_panel_device_id", ""),
        ("siver_panel_device_secret", ""),
    ]:
        config.setdefault(_k, _v)
    if config.get("siver_panel_base_url") == ws.LEGACY_SIVER_PANEL_BASE_URL:
        config["siver_panel_base_url"] = ws.SIVER_PANEL_BASE_URL
    if config.get("siver_panel_ws_url") == ws.LEGACY_SIVER_PANEL_WS_URL:
        config["siver_panel_ws_url"] = ws.SIVER_PANEL_WS_URL
    for _k, _v in [
        ("siver_panel_base_url", ws.SIVER_PANEL_BASE_URL),
        ("siver_panel_ws_url", ws.SIVER_PANEL_WS_URL),
        ("siver_panel_panel_url", ""), ("siver_panel_service_expire_at", ""),
        ("siver_panel_last_error_code", ""), ("siver_panel_last_error_message", ""),
    ]:
        config.setdefault(_k, _v)

    if ws._migrate_prompt_from_config(config):
        try:
            with open(ws.CONFIG_FILE, "w", encoding="utf-8") as _f:
                json.dump(config, _f, ensure_ascii=False, indent=4)
            ws.log("SUCCESS", "旧 prompt 字段已迁移，config.json 已更新")
        except Exception as _e:
            ws.log("ERROR", f"迁移后写回 config.json 失败: {_e}")
    ws._ensure_prompt_dir()
    prompts = ws._get_prompts_list()
    for _k, _v in [
        ("default_prompt", "默认"), ("chat_prompt_map", {}), ("chat_api_map", {}),
        ("chat_max_round_map", {}), ("group_prompt_map", {}),
        ("api_error_reply", "在忙，我稍后回复您"), ("api_error_reply_once", False),
        ("chat_max_round_switch", False), ("chat_max_round_default", 99),
        ("chat_max_round_reset_days", 0), ("chat_max_round_reply", ""),
        ("chat_max_round_reply_once", False), ("chat_split_reply_switch", False),
        ("chat_split_max_chars", 100), ("chat_split_max_count", 4),
        ("group_reply_at_msg", True), ("group_reply_quote", False),
        ("group_split_reply_switch", False), ("group_split_max_chars", 100),
        ("group_split_max_count", 4), ("chatlog_listen_switch", False),
        ("chatlog_url", "http://127.0.0.1:5030"), ("chatlog_polling_interval", 2),
        ("chatlog_request_timeout", 5), ("chatlog_context_switch", False),
        ("chatlog_context_count", 50), ("chatlog_reply_delay", 60),
    ]:
        config.setdefault(_k, _v)

    force_admin_change_required = ws.is_force_admin_change_required()
    return render_template(
        "dashboard.html",
        config=config,
        logs=ws.logger.get_recent_logs(limit=50),
        prompts=prompts,
        force_admin_change_required=force_admin_change_required,
        remote_connect_block_required=ws.is_remote_connect_block_required(),
    )


def get_logs():
    pass