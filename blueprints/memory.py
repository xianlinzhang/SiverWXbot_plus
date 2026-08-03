"""记忆管理 + 备份相关 API。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("memory", __name__)


@bp.route("/api/backup_now", methods=["POST"])
@ws.login_required
def backup_now():
    from flask import jsonify
    try:
        path = ws._do_backup()
        return jsonify({"status": "success", "message": "备份成功！", "path": path})
    except Exception as e:
        ws.log("ERROR", f"手动备份失败: {e}")
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/memory/list")
@ws.login_required
def memory_list():
    import os
    from flask import jsonify
    try:
        if not os.path.exists(ws.MEMORY_BASE):
            return jsonify({"status": "success", "wx_ids": []})
        wx_ids = [d for d in os.listdir(ws.MEMORY_BASE) if os.path.isdir(os.path.join(ws.MEMORY_BASE, d))]
        return jsonify({"status": "success", "wx_ids": wx_ids})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/memory/chats/<wx_id>")
@ws.login_required
def memory_chats(wx_id):
    import os
    from flask import jsonify
    try:
        wx_path = os.path.join(ws.MEMORY_BASE, wx_id)
        if not os.path.exists(wx_path):
            return jsonify({"status": "success", "chats": []})
        wx_abs = os.path.abspath(wx_path)
        chats = []
        for d in os.listdir(wx_path):
            if not ws._safe_is_dir(wx_abs, d):
                continue
            chat_path = os.path.join(wx_path, d)
            display_name = ws._memory_read_original_name(chat_path, d)
            chats.append({"name": display_name, "storage_name": d})
        return jsonify({"status": "success", "chats": chats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/memory/data/<wx_id>/<chat_name>")
@ws.login_required
def memory_data(wx_id, chat_name):
    import os
    import json
    from flask import jsonify
    try:
        dir_abs = os.path.abspath(os.path.join(ws.MEMORY_BASE, wx_id))
        _, chat_dir_normal = ws._memory_find_chat_dir(dir_abs, chat_name)
        if os.name == "nt":
            chat_dir = "\\\\?\\" + chat_dir_normal
        else:
            chat_dir = chat_dir_normal
        if not os.path.exists(chat_dir):
            return jsonify({"status": "success", "messages": []})
        mem_files = [f for f in os.listdir(chat_dir) if f.endswith("_memory.json")]
        if not mem_files:
            return jsonify({"status": "success", "messages": []})
        if os.name == "nt":
            file_path = "\\\\?\\" + chat_dir_normal + "\\" + mem_files[0]
        else:
            file_path = os.path.join(chat_dir, mem_files[0])
        with open(file_path, "r", encoding="utf-8") as f:
            messages = json.load(f)
        return jsonify({"status": "success", "messages": messages if isinstance(messages, list) else []})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/memory/delete_wx/<wx_id>", methods=["DELETE"])
@ws.login_required
def memory_delete_wx(wx_id):
    import os
    import shutil
    from flask import jsonify
    try:
        if os.name == "nt":
            wx_path = "\\\\?\\" + os.path.abspath(os.path.join(ws.MEMORY_BASE, wx_id))
        else:
            wx_path = os.path.join(ws.MEMORY_BASE, wx_id)
        if os.path.exists(wx_path):
            shutil.rmtree(wx_path)
        ws.log("SUCCESS", f"已删除微信号 {wx_id} 的所有记忆")
        return jsonify({"status": "success", "message": "已删除"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@bp.route("/memory/delete_chat/<wx_id>/<chat_name>", methods=["DELETE"])
@ws.login_required
def memory_delete_chat(wx_id, chat_name):
    import os
    import shutil
    from flask import jsonify
    try:
        parent_abs = os.path.abspath(os.path.join(ws.MEMORY_BASE, wx_id))
        _, chat_path_normal = ws._memory_find_chat_dir(parent_abs, chat_name)
        if os.name == "nt":
            chat_path = "\\\\?\\" + chat_path_normal
        else:
            chat_path = chat_path_normal
        if os.path.exists(chat_path):
            shutil.rmtree(chat_path)
        ws.log("SUCCESS", f"已删除 {wx_id}/{chat_name} 的记忆")
        return jsonify({"status": "success", "message": "已删除"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})