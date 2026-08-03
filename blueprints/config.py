"""域3：配置 读写 / API 测试 / 备份。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("config", __name__)


@bp.route("/save_config", methods=["POST"])
@ws.login_required
def save_config_route():
    from flask import request, jsonify
    try:
        config_data = request.get_json()
        if not config_data:
            return jsonify({"status": "error", "message": "无效的配置数据"})

        current_config = ws.read_config() or {}
        merged_config = {**current_config, **config_data}

        if "api_configs" in merged_config:
            for _k in ("api_sdk", "api_key", "base_url", "model1", "model2", "api_sdk_list"):
                merged_config.pop(_k, None)

        ws.coerce_bool_fields(merged_config)
        ws.coerce_list_fields(merged_config)
        ws.coerce_float_fields(merged_config)
        ws.coerce_dict_fields(merged_config)

        if ws.save_config(merged_config):
            ws.update_config_status = True
            return jsonify({"status": "success", "message": "配置保存成功"})
        return jsonify({"status": "error", "message": "配置保存失败"})
    except Exception as e:
        ws.log("ERROR", f"保存配置出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/test_api_config", methods=["POST"])
@ws.login_required
def test_api_config_route():
    import time
    from flask import request, jsonify
    started = time.time()
    try:
        data = request.get_json() or {}
        cfg = data.get("api_config") or {}
        if not isinstance(cfg, dict):
            return jsonify({"status": "error", "message": "接口配置格式无效"})

        tmp_config = ws._TempAPIConfig(cfg)
        if tmp_config.api_sdk not in ("DusAPI", "OpenAI SDK", "Dify", "Coze"):
            return jsonify({"status": "error", "message": "请选择有效的 SDK"})
        if not tmp_config.api_key:
            return jsonify({"status": "error", "message": "API Key 不能为空"})
        if not tmp_config.base_url:
            return jsonify({"status": "error", "message": "Base URL 不能为空"})
        if not tmp_config.model1:
            return jsonify({"status": "error", "message": "模型名称不能为空"})

        api = ws._build_test_api_client(tmp_config)
        reply = api.chat("请只回复 OK", stream=False, prompt=tmp_config.prompt, history=[])
        raw_reply = str(reply or "")
        cleaned_reply = ws.clean_ai_reply_text(raw_reply)
        cleaned = cleaned_reply != raw_reply

        if not raw_reply or raw_reply == "API返回错误，请稍后再试":
            return jsonify({
                "status": "error",
                "message": "接口有响应，但未返回有效文本，请检查模型名称、接口地址或服务商兼容性"
            })

        elapsed_ms = int((time.time() - started) * 1000)
        return jsonify({
            "status": "success",
            "data": {
                "reply": cleaned_reply or "（清洗后为空：接口可能只返回了思考内容）",
                "raw_length": len(raw_reply),
                "cleaned": cleaned,
                "elapsed_ms": elapsed_ms,
            }
        })
    except Exception as e:
        msg = str(e)
        if len(msg) > 800:
            msg = msg[:800] + "..."
        return jsonify({"status": "error", "message": f"接口测试失败：{msg}"})


@bp.route("/load_config")
@ws.login_required
def load_config():
    from flask import jsonify
    config = ws.read_config()
    if not config:
        return jsonify({"status": "error", "message": "无法读取配置文件"})
    return jsonify({"status": "success", "config": config})


@bp.route("/get_admin_config")
@ws.login_required
def get_admin_config():
    import json
    from flask import jsonify
    try:
        with open(ws.ADMIN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({
            "status": "success",
            "username": data.get("username", ""),
            "force_admin_change_required": ws.is_force_admin_change_required(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/save_admin_config", methods=["POST"])
@ws.login_required
def save_admin_config():
    import json
    from flask import request, jsonify, session
    try:
        was_force_required = ws.is_force_admin_change_required()
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        if not username or not password:
            return jsonify({"status": "error", "message": "用户名和密码不能为空"})
        if ws.is_force_admin_change_required() and username == ws.DEFAULT_ADMIN_USERNAME and password == ws.DEFAULT_ADMIN_PASSWORD:
            return jsonify({"status": "error", "message": "远程访问时不能继续使用默认账号密码，请修改后再保存"})
        new_creds = {"username": username, "password_hash": ws.hash_password(password)}
        with open(ws.ADMIN_FILE, "w", encoding="utf-8") as f:
            json.dump(new_creds, f, ensure_ascii=False, indent=4)
        ws.USERS = new_creds
        session["username"] = username
        ws.log("SUCCESS", f"后台账号已更新，用户名：{username}")
        message = "账号密码已保存，下次登录生效"
        force_admin_change_required = ws.is_force_admin_change_required()
        if was_force_required and not force_admin_change_required:
            message = "账号密码已保存，当前会话限制已解除"
        return jsonify({
            "status": "success",
            "message": message,
            "force_admin_change_required": force_admin_change_required,
            "username": username,
        })
    except Exception as e:
        ws.log("ERROR", f"保存账号密码失败: {e}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/get_email_config")
@ws.login_required
def get_email_config():
    from flask import jsonify
    try:
        with open(ws.EMAIL_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
        return jsonify({
            "status": "success",
            "host": lines[0] if len(lines) > 0 else "",
            "port": lines[1] if len(lines) > 1 else "",
            "user": lines[2] if len(lines) > 2 else "",
            "pass": lines[3] if len(lines) > 3 else "",
        })
    except FileNotFoundError:
        return jsonify({"status": "success", "host": "", "port": "", "user": "", "pass": ""})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/save_email_config", methods=["POST"])
@ws.login_required
def save_email_config():
    from flask import request, jsonify
    try:
        data = request.get_json()
        host = data.get("host", "").strip()
        port = data.get("port", "").strip()
        user = data.get("user", "").strip()
        pwd = data.get("pass", "").strip()
        if not all([host, port, user, pwd]):
            return jsonify({"status": "error", "message": "所有字段均不能为空"})
        content = f"{host}\n{port}\n{user}\n{pwd}\n"
        with open(ws.EMAIL_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        ws.log("SUCCESS", f"邮件配置已更新，SMTP: {host}:{port}，账号: {user}")
        return jsonify({"status": "success", "message": "邮件配置已保存"})
    except Exception as e:
        ws.log("ERROR", f"保存邮件配置失败: {e}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/get_webhook_config")
@ws.login_required
def get_webhook_config():
    from flask import jsonify
    try:
        config = ws.webhook_send.load_config(ws.WEBHOOK_FILE)
        return jsonify({"status": "success", **config})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/save_webhook_config", methods=["POST"])
@ws.login_required
def save_webhook_config():
    from flask import request, jsonify
    try:
        data = request.get_json() or {}
        config = ws.webhook_send.save_config(data, ws.WEBHOOK_FILE)
        ws.log("SUCCESS", f"Webhook 配置已更新，启用状态: {config.get('enabled')}")
        return jsonify({"status": "success", "message": "Webhook 配置已保存", "config": config})
    except Exception as e:
        ws.log("ERROR", f"保存 Webhook 配置失败: {e}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/test_webhook", methods=["POST"])
@ws.login_required
def test_webhook():
    from flask import request, jsonify
    try:
        data = request.get_json() or {}
        ok, message = ws.webhook_send.send_webhook("SiverWXbot_plus 测试通知", "这是一条 Webhook 测试消息。", data)
        return jsonify({"status": "success" if ok else "error", "message": message})
    except Exception as e:
        ws.log("ERROR", f"测试 Webhook 失败: {e}")
        return jsonify({"status": "error", "message": str(e)})