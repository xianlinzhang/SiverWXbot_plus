"""P2 structural-split：web_server 路由按域拆分为 blueprint。

各 blueprint 仅注册路由，共享辅助函数/状态均驻留 web_server.py，
在函数内 `import web_server as ws` 引用，避免循环 import。
web_server.create_app() 在此聚合注册全部 blueprint。
"""

from flask import Blueprint


def _lazy_bp(name, url_prefix=None):
    return Blueprint(name, __name__, url_prefix=url_prefix)


def build_blueprints():
    """惰性构建并返回全部 blueprint 列表。（web_server.create_app 调用）"""
    from . import auth, config, prompt, bot, task, message, memory, contacts, system
    return [
        auth.bp,
        config.bp,
        prompt.bp,
        bot.bp,
        task.bp,
        message.bp,
        memory.bp,
        contacts.bp,
        system.bp,
    ]