"""联系人管理相关 API。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("contacts", __name__)

# 联系人消息刷新冷却记录：{chat_name: last_refresh_timestamp}
_contact_message_refresh_cooldowns = {}


@bp.route("/api/contacts", methods=["GET"])
@ws.login_required
def get_contacts():
    from flask import jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "chatlog_client") or not ws.bot.chatlog_client:
            return jsonify({"code": 400, "message": "机器人未启动或未开启 Chatlog 模式", "data": None}), 400
        contacts_result = ws.bot.chatlog_client.search_contact(is_friend=1)
        contacts = contacts_result.get("items", []) if isinstance(contacts_result, dict) else []
        total = len(contacts)
        friends = sum(1 for c in contacts if isinstance(c, dict) and c.get("type") == "friend")
        groups = sum(1 for c in contacts if isinstance(c, dict) and c.get("type") == "group")
        return jsonify({
            "code": 0, "message": "success",
            "data": {"contacts": contacts, "total_count": total, "friend_count": friends, "group_count": groups}
        })
    except Exception as e:
        ws.log("ERROR", f"获取联系人管理完整信息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/contacts/list", methods=["GET"])
@ws.login_required
def get_contacts_list():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "chatlog_manager"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        page = request.args.get("page", 1)
        page_size = request.args.get("page_size", 20)
        try:
            page = max(1, int(page))
            page_size = max(1, min(100, int(page_size)))
        except ValueError:
            page = 1
            page_size = 20
        contacts_map = getattr(ws.bot, "chatlog_contact_map", {})
        contacts = list(contacts_map.values())
        total = len(contacts)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = contacts[start:end]
        return jsonify({
            "code": 0, "message": "success",
            "data": {"list": paginated, "page": page, "page_size": page_size,
                     "total": total, "total_pages": (total + page_size - 1) // page_size}
        })
    except Exception as e:
        ws.log("ERROR", f"获取联系人列表失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/contacts/search", methods=["GET"])
@ws.login_required
def search_contacts():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "chatlog_manager"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        keyword = request.args.get("keyword", "").strip()
        if not keyword:
            return jsonify({"code": 400, "message": "keyword 参数不能为空", "data": None}), 400
        contacts_map = getattr(ws.bot, "chatlog_contact_map", {})
        results = []
        seen = set()
        for contact in contacts_map.values():
            wxid = contact.get("userName", "")
            if wxid in seen:
                continue
            seen.add(wxid)
            nickname = contact.get("nickName", "")
            remark = contact.get("remark", "")
            alias = contact.get("alias", "")
            if keyword in nickname or keyword in remark or keyword in alias:
                results.append(contact)
        return jsonify({"code": 0, "message": "success", "data": results})
    except Exception as e:
        ws.log("ERROR", f"搜索联系人失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/contacts/messages", methods=["GET"])
@ws.login_required
def get_contact_messages():
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        chat_name = request.args.get("chat_name", "").strip()
        if not chat_name:
            return jsonify({"code": 400, "message": "chat_name 参数不能为空", "data": None}), 400
        messages = ws.bot.message_store.get_all_messages(chat_name)
        messages_data = [msg.to_dict() for msg in messages]
        return jsonify({"code": 0, "message": "success", "data": messages_data})
    except Exception as e:
        ws.log("ERROR", f"获取联系人消息记录失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/contacts/refresh", methods=["POST"])
@ws.login_required
def refresh_contacts():
    from flask import jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "chatlog_manager"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        ws.bot.chatlog_manager.refresh_chatlog_contacts()
        contacts_map = getattr(ws.bot, "chatlog_contact_map", {})
        count = len(contacts_map)
        return jsonify({"code": 0, "message": f"联系人缓存已刷新，共 {count} 条记录", "data": {"contact_count": count}})
    except Exception as e:
        ws.log("ERROR", f"刷新联系人缓存失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/contacts/messages/refresh", methods=["POST"])
@ws.login_required
def refresh_contact_messages():
    import time
    from flask import request, jsonify
    try:
        if not ws.bot or not hasattr(ws.bot, "message_store"):
            return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "无效的请求数据", "data": None}), 400
        chat_name = data.get("chat_name", "").strip()
        if not chat_name:
            return jsonify({"code": 400, "message": "chat_name 参数不能为空", "data": None}), 400
        cooldown = getattr(ws.bot.config, "chatlog_message_manual_refresh_cooldown", 60)
        now = time.time()
        last_refresh = _contact_message_refresh_cooldowns.get(chat_name, 0)
        if cooldown > 0 and (now - last_refresh) < cooldown:
            retry_after = int(cooldown - (now - last_refresh)) + 1
            return jsonify({"code": 429, "message": f"刷新冷却中，请 {retry_after} 秒后重试", "data": {"retry_after": retry_after}}), 429
        total_fetched, new_saved = ws.bot.message_store.refresh_messages_from_chatlog(chat_name)
        _contact_message_refresh_cooldowns[chat_name] = time.time()
        return jsonify({"code": 0, "message": "刷新成功", "data": {"total_fetched": total_fetched, "new_saved": new_saved}})
    except Exception as e:
        ws.log("ERROR", f"刷新联系人消息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500