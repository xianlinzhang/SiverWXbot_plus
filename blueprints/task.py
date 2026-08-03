"""任务队列相关 API。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("task", __name__)


def _require_bot(attr):
    from flask import jsonify
    bot = ws.bot
    if not bot or not hasattr(bot, attr):
        return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
    return None


@bp.route("/api/tasks", methods=["GET"])
@ws.login_required
def get_tasks():
    from flask import jsonify
    try:
        err = _require_bot("task_queue")
        if err:
            return err
        bot = ws.bot
        status = bot.task_queue.get_queue_status()
        pending_tasks = bot.task_queue.get_pending_tasks()
        history = bot.task_queue.get_history(limit=50)
        return jsonify({
            "code": 0,
            "message": "success",
            "data": {
                "pending_count": status.get("pending_count", 0),
                "current_task": status.get("current_task", None),
                "success_count": status.get("success_count", 0),
                "failed_count": status.get("failed_count", 0),
                "pending_tasks": [task.to_dict() for task in pending_tasks],
                "task_history": [task.to_dict() for task in history]
            }
        })
    except Exception as e:
        ws.log("ERROR", f"获取任务队列完整信息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/tasks/status", methods=["GET"])
@ws.login_required
def get_tasks_status():
    from flask import jsonify
    try:
        err = _require_bot("task_queue")
        if err:
            return err
        status = ws.bot.task_queue.get_queue_status()
        return jsonify({"code": 0, "message": "success", "data": status})
    except Exception as e:
        ws.log("ERROR", f"获取任务队列状态失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/tasks/pending", methods=["GET"])
@ws.login_required
def get_pending_tasks():
    from flask import jsonify
    try:
        err = _require_bot("task_queue")
        if err:
            return err
        tasks = ws.bot.task_queue.get_pending_tasks()
        tasks_data = [task.to_dict() for task in tasks]
        return jsonify({"code": 0, "message": "success", "data": tasks_data})
    except Exception as e:
        ws.log("ERROR", f"获取待执行任务列表失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/tasks/history", methods=["GET"])
@ws.login_required
def get_tasks_history():
    from flask import request, jsonify
    try:
        err = _require_bot("task_queue")
        if err:
            return err
        limit = request.args.get("limit", 50)
        try:
            limit = int(limit)
        except ValueError:
            limit = 50
        tasks = ws.bot.task_queue.get_history(limit=limit)
        tasks_data = [task.to_dict() for task in tasks]
        return jsonify({"code": 0, "message": "success", "data": tasks_data})
    except Exception as e:
        ws.log("ERROR", f"获取任务历史记录失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/tasks/cancel", methods=["POST"])
@ws.login_required
def cancel_task():
    from flask import request, jsonify
    try:
        err = _require_bot("task_queue")
        if err:
            return err
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "无效的请求数据", "data": None}), 400
        task_id = data.get("task_id")
        if not task_id:
            return jsonify({"code": 400, "message": "task_id 参数不能为空", "data": None}), 400
        success = ws.bot.task_queue.cancel_task(task_id)
        if success:
            return jsonify({"code": 0, "message": "任务取消成功", "data": {"task_id": task_id}})
        return jsonify({"code": 404, "message": "任务不存在或已执行", "data": None}), 404
    except Exception as e:
        ws.log("ERROR", f"取消任务失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/tasks/clear", methods=["POST"])
@ws.login_required
def clear_tasks_queue():
    from flask import jsonify
    try:
        err = _require_bot("task_queue")
        if err:
            return err
        count = ws.bot.task_queue.clear_queue()
        return jsonify({"code": 0, "message": f"队列已清空，共取消 {count} 个任务", "data": {"cleared_count": count}})
    except Exception as e:
        ws.log("ERROR", f"清空任务队列失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500