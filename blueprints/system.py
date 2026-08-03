"""系统 misc：redis 状态/stats、日志、文件选择、机器人启停/授权/更新/状态。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("system", __name__)


@bp.after_request
def _apply_security_headers(response):
    return ws.apply_panel_security_headers(response)


@bp.route("/get_logs")
@ws.login_required
def get_logs():
    from flask import request, jsonify
    after_id_raw = str(request.args.get("after_id", "") or "").strip()
    after_id = None
    if after_id_raw:
        try:
            after_id = max(0, int(after_id_raw))
        except ValueError:
            after_id = None
    return jsonify(ws.logger.get_logs_after(after_id, limit=50))


@bp.route("/pick_image_file", methods=["GET"])
@ws.login_required
def pick_image_file():
    import os
    from flask import jsonify
    try:
        import tkinter as tk
        from tkinter import filedialog
        path = ""
        with ws._tk_lock:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.lift()
            path = filedialog.askopenfilename(
                parent=root,
                title="选择图片文件",
                filetypes=[
                    ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.PNG *.JPG *.JPEG"),
                    ("所有文件", "*.*"),
                ]
            )
            root.destroy()
        if path:
            path = os.path.normpath(path)
            return jsonify({"status": "success", "path": path})
        return jsonify({"status": "cancel"})
    except Exception as e:
        ws.log("ERROR", f"文件选择框出错: {e}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/api/redis/status", methods=["GET"])
@ws.login_required
def get_redis_status():
    from flask import jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "redis_manager"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        rm = ws.bot.redis_manager
        return jsonify({
            "code": 0, "message": "success",
            "data": {
                "host": rm.config.get("host", "unknown"),
                "port": rm.config.get("port", "unknown"),
                "db": rm.config.get("db", "unknown"),
                "available": rm.is_available(),
                "mode": "redis" if rm.is_available() else "local_fallback"
            }
        })
    except Exception as e:
        ws.log("ERROR", f"获取 Redis 状态失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/redis/stats", methods=["GET"])
@ws.login_required
def get_redis_stats():
    from flask import jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "redis_manager"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        rm = ws.bot.redis_manager
        if not rm.is_available():
            return jsonify({"code": 0, "message": "success", "data": {"message": "Redis 不可用，使用本地存储"}})
        client = rm._client if hasattr(rm, "_client") else None
        if not client:
            return jsonify({"code": 0, "message": "success", "data": {"message": "Redis 客户端未初始化"}})
        try:
            keys = client.keys("wxbot:*")
            keys_count = len(keys)
            tasks_keys = client.keys("wxbot:*:tasks:*")
            messages_keys = client.keys("wxbot:*:messages:*")
            contacts_keys = client.keys("wxbot:*:contacts:*")
            memory_keys = client.keys("wxbot:*:memory:*")
            return jsonify({
                "code": 0, "message": "success",
                "data": {
                    "keys_count": keys_count, "tasks": len(tasks_keys),
                    "messages": len(messages_keys), "contacts": len(contacts_keys),
                    "memory": len(memory_keys)
                }
            })
        except Exception as e:
            ws.log("WARNING", f"获取 Redis 统计失败: {e}")
            return jsonify({"code": 0, "message": "success", "data": {"message": f"获取统计失败: {str(e)}"}})
    except Exception as e:
        ws.log("ERROR", f"获取 Redis 统计信息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500