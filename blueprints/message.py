"""消息管理相关 API + 发送消息。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("message", __name__)


@bp.route("/api/messages", methods=["GET"])
@ws.login_required
def get_messages():
    from flask import jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        pending = ws.bot.message_store.get_pending_confirm()
        stats = ws.bot.message_store.get_stats()
        return jsonify({
            "code": 0,
            "message": "success",
            "data": {
                "pending_confirm": pending,
                "pending_count": stats.get("pending_confirm", 0),
                "processed_count": stats.get("processed", 0),
                "replied_count": stats.get("replied", 0),
                "total_count": stats.get("total", 0)
            }
        })
    except Exception as e:
        ws.log("ERROR", f"获取消息管理完整信息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/messages/pending_confirm", methods=["GET"])
@ws.login_required
def get_pending_confirm_messages():
    from flask import jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        messages = ws.bot.message_store.get_pending_confirm()
        messages_data = [msg.to_dict() for msg in messages]
        return jsonify({"code": 0, "message": "success", "data": messages_data})
    except Exception as e:
        ws.log("ERROR", f"获取待确认消息列表失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/messages/confirm", methods=["POST"])
@ws.login_required
def confirm_message():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "无效的请求数据", "data": None}), 400
        chat_name = data.get("chat_name")
        message_id = data.get("message_id")
        if not chat_name or not message_id:
            return jsonify({"code": 400, "message": "chat_name 和 message_id 参数不能为空", "data": None}), 400
        record = ws.bot.message_store.confirm_message(chat_name, message_id)
        if record:
            return jsonify({"code": 0, "message": "消息确认成功", "data": record.to_dict()})
        return jsonify({"code": 404, "message": "消息不存在", "data": None}), 404
    except Exception as e:
        ws.log("ERROR", f"确认消息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/messages/reject", methods=["POST"])
@ws.login_required
def reject_message():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "无效的请求数据", "data": None}), 400
        chat_name = data.get("chat_name")
        message_id = data.get("message_id")
        if not chat_name or not message_id:
            return jsonify({"code": 400, "message": "chat_name 和 message_id 参数不能为空", "data": None}), 400
        record = ws.bot.message_store.reject_message(chat_name, message_id)
        if record:
            return jsonify({"code": 0, "message": "消息已拒绝", "data": record.to_dict()})
        return jsonify({"code": 404, "message": "消息不存在", "data": None}), 404
    except Exception as e:
        ws.log("ERROR", f"拒绝消息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/messages/search", methods=["GET"])
@ws.login_required
def search_messages():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        keyword = request.args.get("keyword", "").strip()
        chat_name = request.args.get("chat_name", "").strip()
        if not keyword:
            return jsonify({"code": 400, "message": "keyword 参数不能为空", "data": None}), 400
        chat_name_param = chat_name if chat_name else None
        messages = ws.bot.message_store.search_messages(keyword, chat_name_param)
        messages_data = [msg.to_dict() for msg in messages]
        return jsonify({"code": 0, "message": "success", "data": messages_data})
    except Exception as e:
        ws.log("ERROR", f"搜索消息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/messages/stats", methods=["GET"])
@ws.login_required
def get_messages_stats():
    import os
    import json
    from flask import jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        stats = {
            "pending": 0, "processed": 0, "replied": 0,
            "confirmed": 0, "rejected": 0, "total": 0
        }
        base_dir = os.path.join(ws.bot.message_store.base_path, ws.bot.message_store.wx_id)
        if os.path.exists(base_dir):
            for storage_dir in os.listdir(base_dir):
                storage_path = os.path.join(base_dir, storage_dir)
                if os.path.isdir(storage_path):
                    msg_file = os.path.join(storage_path, f"{storage_dir}_messages.json")
                    if os.path.exists(msg_file):
                        try:
                            with open(msg_file, "r", encoding="utf-8") as f:
                                messages = json.load(f)
                            if isinstance(messages, list):
                                for msg_data in messages:
                                    status = msg_data.get("status", "pending")
                                    if status in stats:
                                        stats[status] += 1
                                    stats["total"] += 1
                        except Exception:
                            continue
        return jsonify({"code": 0, "message": "success", "data": stats})
    except Exception as e:
        ws.log("ERROR", f"获取消息统计失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/messages/history", methods=["GET"])
@ws.login_required
def get_messages_history():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        chat_name = request.args.get("chat_name", "").strip()
        wxid = request.args.get("wxid", "").strip()
        if not chat_name:
            return jsonify({"code": 400, "message": "chat_name 参数不能为空", "data": None}), 400
        history = ws.bot.message_store.get_history(chat_name, wxid=wxid)
        return jsonify({"code": 0, "message": "success", "data": history})
    except Exception as e:
        ws.log("ERROR", f"获取消息历史失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/send_message", methods=["POST"])
@ws.login_required
def send_message():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "task_queue"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        data = request.get_json() if request.is_json else request.form
        chat_name = data.get("chat_name", "").strip()
        content = data.get("content", "").strip()
        if not chat_name:
            return jsonify({"code": 400, "message": "chat_name 参数不能为空", "data": None}), 400
        if not content:
            return jsonify({"code": 400, "message": "content 参数不能为空", "data": None}), 400
        task_id = ws.bot.task_queue.submit("send_message", {"chat_name": chat_name, "content": content})
        return jsonify({"code": 0, "message": "消息已加入发送队列", "data": {"task_id": task_id}})
    except Exception as e:
        ws.log("ERROR", f"发送消息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500