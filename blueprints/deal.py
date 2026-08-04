"""同城信息队列消费者相关 API。"""

from flask import Blueprint

import web_server as ws

bp = Blueprint("deal", __name__)


def _require_bot(attr):
    from flask import jsonify
    bot = ws.bot
    if not bot or not hasattr(bot, attr):
        return jsonify({"code": 400, "message": "机器人未启动", "data": None}), 400
    return None


@bp.route("/api/deals", methods=["GET"])
@ws.login_required
def get_deals():
    from flask import jsonify
    try:
        err = _require_bot("deal_consumer")
        if err:
            return err
        bot = ws.bot
        items = bot.deal_consumer.get_pending()
        stats = bot.deal_consumer.get_stats()
        return jsonify({
            "code": 0,
            "message": "success",
            "data": {
                "items": items,
                "stats": stats,
            }
        })
    except Exception as e:
        ws.log("ERROR", f"获取同城信息待发布列表失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/deals/publish", methods=["POST"])
@ws.login_required
def publish_deal():
    from flask import request, jsonify
    try:
        err = _require_bot("deal_consumer")
        if err:
            return err
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "无效的请求数据", "data": None}), 400
        field = data.get("field")
        if not field:
            return jsonify({"code": 400, "message": "field 参数不能为空", "data": None}), 400
        ok, msg = ws.bot.deal_consumer.publish(field)
        if ok:
            return jsonify({"code": 0, "message": msg, "data": {"field": field}})
        return jsonify({"code": 400, "message": msg, "data": None}), 400
    except Exception as e:
        ws.log("ERROR", f"发布同城信息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/deals/discard", methods=["POST"])
@ws.login_required
def discard_deal():
    from flask import request, jsonify
    try:
        err = _require_bot("deal_consumer")
        if err:
            return err
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "无效的请求数据", "data": None}), 400
        field = data.get("field")
        if not field:
            return jsonify({"code": 400, "message": "field 参数不能为空", "data": None}), 400
        ok, msg = ws.bot.deal_consumer.discard(field)
        if ok:
            return jsonify({"code": 0, "message": msg, "data": {"field": field}})
        return jsonify({"code": 400, "message": msg, "data": None}), 400
    except Exception as e:
        ws.log("ERROR", f"丢弃同城信息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500


@bp.route("/api/deals/re_push", methods=["POST"])
@ws.login_required
def re_push_deal():
    from flask import request, jsonify
    try:
        err = _require_bot("deal_consumer")
        if err:
            return err
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "无效的请求数据", "data": None}), 400
        field = data.get("field")
        if not field:
            return jsonify({"code": 400, "message": "field 参数不能为空", "data": None}), 400
        ok, msg = ws.bot.deal_consumer.re_push(field)
        if ok:
            return jsonify({"code": 0, "message": msg, "data": {"field": field}})
        return jsonify({"code": 400, "message": msg, "data": None}), 400
    except Exception as e:
        ws.log("ERROR", f"重推同城信息失败: {e}")
        return jsonify({"code": 500, "message": str(e), "data": None}), 500
