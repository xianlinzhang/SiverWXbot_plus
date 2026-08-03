# -*- coding: utf-8 -*-
"""
版本号单一事实源（Single Source of Truth）。

发版时只改这里（version / version_log），然后运行：
    python scripts/update_version.py
自动同步 docs/version.json 并打印仍需手动的文档位置。

各消费方（wxbot_core / core.ai_api / web_server / 面板）一律从本模块读取，
不得再各自维护独立的版本字符串，避免手工多写造成版本漂移。
"""
version = "V4.7.27"
version_log = "V4.7.27 - 优化远程访问、关闭SESSION_COOKIE_HTTPONLY方便内外网访问、优化面板接口测试"