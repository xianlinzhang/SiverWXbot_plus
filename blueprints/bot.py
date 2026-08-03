"""机器人 启停 / 授权 / 更新 / 状态 / siver-panel 状态。

注意：bot / bot_thread 全局对象驻留 web_server，此处一律通过 ws.<attr> 读写，
绝不用 Python `global`（那只会绑定本模块全局，不会改 web_server 的）。
"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("bot", __name__)


@bp.route("/start_bot", methods=["POST"])
@ws.login_required
def start_bot():
    import threading
    from flask import jsonify
    ws.log("INFO", "机器人启动请求已接收")

    if ws.bot_thread and ws.bot_thread.is_alive():
        ws.log("WARNING", "状态：机器人已在运行")
        return jsonify({"status": "success", "message": "机器人已在运行"})

    def run_bot():
        import pythoncom
        ws.pythoncom.CoInitialize()
        try:
            if ws.bot:
                try:
                    ws.bot.stop()
                    ws.log("INFO", "已清理上次残留的 WeChat 监听")
                except Exception as _e:
                    ws.log("WARNING", f"清理旧监听时出错（可忽略）: {_e}")
            ws.bot = ws.WXBot()
            ws.bot.run()
        finally:
            ws.pythoncom.CoUninitialize()
            ws._restore_sleep()

    try:
        ws.bot_thread = ws.threading.Thread(target=run_bot, daemon=True)
        ws.bot_thread.start()
        ws._prevent_sleep()
    except Exception as e:
        ws.log("ERROR", f"启动机器人失败: {str(e)}")

    return jsonify({"status": "success", "message": "机器人启动命令已发送"})


@bp.route("/stop_bot", methods=["POST"])
@ws.login_required
def stop_bot():
    from flask import jsonify
    ws.log("INFO", "机器人停止请求已接收")
    if ws.bot_thread and ws.bot_thread.is_alive():
        if ws.bot.stop_wxbot():
            ws.log("SUCCESS", "机器人已停止")
            ws.bot_thread = None
            ws.bot = None
            ws._restore_sleep()
            return jsonify({"status": "success", "message": "机器人已停止"})
        ws.log("ERROR", "停止机器人失败")
        return jsonify({"status": "error", "message": "停止机器人失败"})
    ws.log("WARNING", "状态：机器人未运行")
    return jsonify({"status": "error", "message": "机器人未运行"})


@bp.route("/check_activate")
@ws.login_required
def check_activate():
    from flask import jsonify
    try:
        return jsonify({"status": "success", "data": {"activated": bool(True)}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/activate", methods=["POST"])
@ws.login_required
def activate():
    from flask import request, jsonify
    try:
        data = request.get_json()
        code = (data.get("code") or "").strip()
        if not code:
            return jsonify({"status": "error", "message": "激活码不能为空"})
        from wxautox4.utils.useful import authenticate
        result = authenticate(code)
        if result:
            ws.log("SUCCESS", "wxautox4 激活成功")
            return jsonify({"status": "success", "message": "激活成功！"})
        ws.log("WARNING", "wxautox4 激活失败，激活码无效或已过期")
        return jsonify({"status": "error", "message": "激活失败，激活码无效或已过期"})
    except Exception as e:
        ws.log("ERROR", f"激活出错: {e}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/check_update")
@ws.login_required
def check_update():
    from flask import jsonify
    try:
        import wxbot_core as wxbot_mod
        local_version = getattr(wxbot_mod, "version", "")
        machine_code = "11111"
        data = {}
        data["local_version"] = ws.BOT_VERSION
        data["machine_code"] = machine_code
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/get_status")
@ws.login_required
def get_status():
    from flask import jsonify
    if ws.bot_thread and ws.bot_thread.is_alive() and ws.bot:
        try:
            status = ws.bot.get_status()
            status["bot_running"] = True
            return jsonify({"status": "success", "data": status})
        except Exception as e:
            return jsonify({"status": "success", "data": {"bot_running": True, "error": str(e)}})
    return jsonify({"status": "success", "data": {"bot_running": False}})


@bp.route("/api/siver-panel/status")
@ws.login_required
def get_siver_panel_status():
    from flask import jsonify
    if ws.siver_panel_manager is None:
        return jsonify({"status": "error", "message": "SiverPanel 客户端未初始化"})
    return jsonify({"status": "success", "data": ws.siver_panel_manager.get_status()})


@bp.route("/api/siver-panel/connect", methods=["POST"])
@ws.login_required
def connect_siver_panel():
    from flask import jsonify
    if ws.siver_panel_manager is None:
        return jsonify({"status": "error", "message": "SiverPanel 客户端未初始化"})
    try:
        status = ws.siver_panel_manager.connect(manual=True)
        if status.get("state") == "error" and status.get("last_error_code") == "default_admin_credentials_block_remote_connect":
            return jsonify({
                "status": "error",
                "message": status.get("last_message") or "远程连接已被安全策略拦截",
                "error_code": status.get("last_error_code") or "default_admin_credentials_block_remote_connect",
                "data": status,
            })
        return jsonify({"status": "success", "message": status.get("last_message") or "正在发起远程连接", "data": status})
    except Exception as e:
        ws.log("ERROR", f"SiverPanel 手动连接失败: {e}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/api/siver-panel/disconnect", methods=["POST"])
@ws.login_required
def disconnect_siver_panel():
    from flask import jsonify
    if ws.siver_panel_manager is None:
        return jsonify({"status": "error", "message": "SiverPanel 客户端未初始化"})
    try:
        status = ws.siver_panel_manager.disconnect(reason="manual_disconnect")
        return jsonify({"status": "success", "message": status.get("last_message") or "远程访问服务已断开", "data": status})
    except Exception as e:
        ws.log("ERROR", f"SiverPanel 断开连接失败: {e}")
        return jsonify({"status": "error", "message": str(e)})