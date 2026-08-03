"""Prompt 文件管理路由。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("prompt", __name__)


@bp.route("/list_prompts")
@ws.login_required
def list_prompts_route():
    from flask import jsonify
    return jsonify({"status": "success", "prompts": ws._get_prompts_list()})


@bp.route("/save_prompt", methods=["POST"])
@ws.login_required
def save_prompt_route():
    import re
    import tempfile
    import os
    from flask import request, jsonify
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "msg": "无效请求"})
        name = str(data.get("name", "")).strip()
        content = str(data.get("content", ""))
        old_name = str(data.get("old_name", "")).strip()
        if name.lower().endswith(".md"):
            name = name[:-3].strip()
        if not name:
            return jsonify({"status": "error", "msg": "Prompt 名称不能为空"})
        if not re.fullmatch(r"[\u4e00-\u9fff\w\s\-]+", name):
            return jsonify({"status": "error", "msg": "Prompt 名称含非法字符（只允许中文、字母、数字、空格、_ 和 -）"})
        ws._ensure_prompt_dir()
        if old_name and old_name != name:
            old_path = os.path.join(ws.PROMPT_DIR, f"{old_name}.md")
            if os.path.exists(old_path):
                os.remove(old_path)
        target = os.path.join(ws.PROMPT_DIR, f"{name}.md")
        tmp_fd, tmp_path = tempfile.mkstemp(dir=ws.PROMPT_DIR, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tf:
                tf.write(content)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise
        ws.log("SUCCESS", f"Prompt 已保存：{name}.md")
        return jsonify({"status": "success"})
    except Exception as e:
        ws.log("ERROR", f"保存 Prompt 失败: {e}")
        return jsonify({"status": "error", "msg": str(e)})


@bp.route("/delete_prompt", methods=["POST"])
@ws.login_required
def delete_prompt_route():
    import os
    from flask import request, jsonify
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "msg": "无效请求"})
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"status": "error", "msg": "名称不能为空"})
        ws._ensure_prompt_dir()
        md_files = [f for f in os.listdir(ws.PROMPT_DIR) if f.endswith(".md")]
        if len(md_files) <= 1:
            return jsonify({"status": "error", "msg": "不允许删除最后一个 Prompt"})
        target = os.path.join(ws.PROMPT_DIR, f"{name}.md")
        if os.path.exists(target):
            os.remove(target)
        ws.log("SUCCESS", f"Prompt 已删除：{name}.md")
        return jsonify({"status": "success"})
    except Exception as e:
        ws.log("ERROR", f"删除 Prompt 失败: {e}")
        return jsonify({"status": "error", "msg": str(e)})