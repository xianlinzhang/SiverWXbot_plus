import os
import re
from logger import log


class CommandHandler:
    """
    命令处理模块
    负责处理管理员命令（添加/删除用户、开关功能、查看状态等）。
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.message_store = bot.message_store if hasattr(bot, 'message_store') else None
        self.wx_lock = bot.wx_lock if hasattr(bot, 'wx_lock') else None

    def process_command(self, chat, message):
        """
        解析并分发管理员指令。
        支持用户/群组管理、模型切换、AI 设定修改、状态查询等。

        :param chat:    管理员聊天窗口子对象
        :param message: 消息对象
        :return:        操作结果
        """
        result = True
        content = message.content

        if content.startswith("/添加用户"):
            result = self.handle_add_user(chat, message)
        elif content.startswith("/删除用户"):
            result = self.handle_remove_user(chat, message)
        elif content == "/当前用户":
            result = chat.SendMsg("当前用户：\n" + ", ".join(self.config.listen_list))
        elif content == "/当前群":
            result = chat.SendMsg("当前群：\n" + ", ".join(self.config.group))
        elif content == "/群机器人状态":
            result = self.handle_group_switch_status(chat, message)
        elif content.startswith("/添加群"):
            result = self.handle_add_group(chat, message)
        elif content.startswith("/删除群"):
            result = self.handle_remove_group(chat, message)
        elif content == "/开启群机器人":
            result = self.handle_enable_group_bot(chat, message)
        elif content == "/关闭群机器人":
            result = self.handle_disable_group_bot(chat, message)
        elif content == "/开启群机器人欢迎语":
            result = self.handle_enable_welcome_msg(chat, message)
        elif content == "/关闭群机器人欢迎语":
            result = self.handle_disable_welcome_msg(chat, message)
        elif content == "/群机器人欢迎语状态":
            result = self.handle_welcome_msg_status(chat, message)
        elif content == "/当前群机器人欢迎语":
            result = chat.SendMsg("当前群机器人欢迎语：\n" + self.config.group_welcome_msg)
        elif content.startswith("/更改群机器人欢迎语为"):
            result = self.handle_change_welcome_msg(chat, message)
        elif content == "/查看接口列表":
            result = self.handle_list_api_configs(chat, message)
        elif content.startswith("/选择接口"):
            result = self.handle_select_api_config(chat, message)
        elif content == "/当前AI设定":
            _default_content = self.config.get_prompt_content(self.config.default_prompt)
            result = chat.SendMsg(f'当前默认AI设定（{self.config.default_prompt}）：\n' + _default_content)
        elif content.startswith("/更改AI设定为") or content.startswith("/更改ai设定为"):
            result = self.handle_change_prompt(chat, message)
        elif content == "/更新配置":
            self.config.refresh_config()
            self.bot.api_cache = {}
            self.bot.init_wx_listeners()
            result = chat.SendMsg(content + ' 完成\n')
        elif content == "/当前版本":
            result = chat.SendMsg(
                content + 'wxbot_' + self.bot.ver + '\n' + self.bot.ver_log + '\n作者:https://www.siver.top'
            )
        elif content in ("/指令", "指令"):
            result = self.send_command_list(chat)
        elif content == "/系统状态指令":
            result = chat.SendMsg(
                '--- 系统状态 ---\n'
                '[/状态] 完整运行状态摘要\n'
                '[/接口测试 内容] 测试当前AI接口\n'
                '[/当前版本] 版本号及更新说明\n'
                '[/更新配置] 重载配置并重初始化监听'
            )
        elif content == "/用户管理指令":
            result = chat.SendMsg(
                '--- 用户管理 ---\n'
                '[/当前用户] 当前监听用户列表\n'
                '[/添加用户***] 添加监听用户\n'
                '[/删除用户***] 移除监听用户'
            )
        elif content == "/群组管理指令":
            result = chat.SendMsg(
                '--- 群组管理 ---\n'
                '[/当前群] 当前监听群列表\n'
                '[/添加群***] / [/删除群***]\n'
                '[/开启群机器人] / [/关闭群机器人]\n'
                '[/群机器人状态]\n'
                '[/开启群机器人欢迎语] / [/关闭群机器人欢迎语]\n'
                '[/群机器人欢迎语状态]\n'
                '[/当前群机器人欢迎语]\n'
                '[/更改群机器人欢迎语为***]'
            )
        elif content == "/Prompt管理指令":
            result = chat.SendMsg(
                '--- Prompt 管理 ---\n'
                '[/Prompt列表] 所有可用Prompt\n'
                '[/当前Prompt] 默认Prompt名称及内容\n'
                '[/切换Prompt ***] 切换默认Prompt\n'
                '[/更改AI设定为***] 修改默认Prompt内容\n'
                '[/当前AI设定] 查看当前默认Prompt内容'
            )
        elif content == "/关键词指令":
            result = chat.SendMsg(
                '--- 关键词回复 ---\n'
                '[/关键词状态] 查看关键词配置及列表\n'
                '[/开启私聊关键词] / [/关闭私聊关键词]\n'
                '[/开启群聊关键词] / [/关闭群聊关键词]\n'
                '[/开启群聊关键词@触发] / [/关闭群聊关键词@触发]'
            )
        elif content == "/记忆指令":
            result = chat.SendMsg(
                '--- 对话记忆 ---\n'
                '[/记忆状态] 查看记忆配置\n'
                '[/开启记忆] / [/关闭记忆]\n'
                '[/清除记忆] 清除管理员对话记忆\n'
                '[/清除用户记忆 ***] 清除指定用户/群记忆\n'
                '[/清除全部记忆] 清除所有对话记忆'
            )
        elif content == "/延迟指令":
            result = chat.SendMsg(
                '--- 回复延迟 ---\n'
                '[/回复延迟状态] 查看回复延迟配置\n'
                '[/开启回复延迟] / [/关闭回复延迟]'
            )
        elif content == "/暂停恢复指令":
            result = chat.SendMsg(
                '--- 只监听不 AI 回复 ---\n'
                '[/自动回复状态] 查看当前只监听状态\n'
                '[/暂停私聊自动回复] 开启私聊只监听不 AI 回复\n'
                '[/恢复私聊自动回复] 关闭私聊只监听不 AI 回复\n'
                '[/暂停群聊自动回复] 开启群聊只监听不 AI 回复\n'
                '[/恢复群聊自动回复] 关闭群聊只监听不 AI 回复\n'
                '开启后监听、记忆、关键词回复和自定义转发保持运行，仅停止调用 AI 接口自动回复'
            )
        elif content == "/图片识别指令":
            result = chat.SendMsg(
                '--- 图片识别 ---\n'
                '[/图片识别状态] 查看私聊/群聊图片识别开关及接口\n'
                '（开关需在面板配置，指令仅支持查看）'
            )
        elif content == "/拆分回复指令":
            result = chat.SendMsg(
                '--- 拆分多条回复 ---\n'
                '[/拆分回复状态] 查看拆分回复配置\n'
                '[/开启私聊拆分回复] / [/关闭私聊拆分回复]\n'
                '[/开启群聊拆分回复] / [/关闭群聊拆分回复]\n'
                '（字数/条数上限需在面板配置）'
            )
        elif content == "/新好友指令":
            result = chat.SendMsg(
                '--- 新好友 ---\n'
                '[/新好友状态] 查看新好友自动通过及回复状态\n'
                '（开关需在面板配置，指令仅支持查看）'
            )
        elif content == "/接口指令":
            result = chat.SendMsg(
                '--- AI接口 & 错误回复 ---\n'
                '[/查看接口列表] 返回所有接口配置\n'
                '[/选择接口 N] 切换至第N个接口\n'
                '[/查看错误回复] 查看接口失败固定回复\n'
                '[/设置错误回复 ***] 修改接口失败固定回复'
            )
        elif content == "/计数器指令":
            _round_sw = "开启" if self.config.chat_max_round_switch else "关闭"
            _round_reset = self.config.chat_max_round_reset_days
            _reset_desc = "不重置" if _round_reset == 0 else f"{_round_reset}天"
            _reply_desc = self.config.chat_max_round_reply or "（空，超限后静默）"
            result = chat.SendMsg(
                '--- 回复计数器 ---\n'
                f'轮数限制开关：{_round_sw}\n'
                f'默认上限：{self.config.chat_max_round_default} 轮\n'
                f'白名单专属上限：{len(self.config.chat_max_round_map)} 个\n'
                f'重置周期：{_reset_desc}\n'
                f'超限话术：{_reply_desc}\n'
                f'超限只回复一次：{"是" if self.config.chat_max_round_reply_once else "否"}\n'
                f'接口失败只回复一次：{"是" if self.config.api_error_reply_once else "否"}\n'
                '[/清除计数 昵称] 清除指定用户的回复计数与通知状态'
            )
        elif content == "/消息存储指令":
            result = chat.SendMsg(
                '--- 消息存储 ---\n'
                '[/消息存储状态] 查看消息存储配置及统计\n'
                '[/开启私聊回复确认] / [/关闭私聊回复确认]\n'
                '[/待确认列表] 查看所有待确认的回复\n'
                '[/确认回复 ID] 确认并发送指定待确认回复\n'
                '[/取消回复 ID] 取消指定待确认回复\n'
                '[/查看未读消息] 查看所有未读消息\n'
                '[/标记已读 ID] 将指定消息标记为已读\n'
                '[/标记未读 ID] 将指定消息标记为未读'
            )
        elif content == "/微信锁指令":
            result = chat.SendMsg(
                '--- 微信界面操作锁 ---\n'
                '[/微信锁状态] 查看微信锁当前状态\n'
                '[/占用微信锁] 手动占用微信锁\n'
                '[/释放微信锁] 手动释放微信锁\n'
                '[/强制释放微信锁] 强制释放微信锁（无视占用者）\n'
                '[/开启微信锁] / [/关闭微信锁]'
            )
        elif content == "/状态":
            result = self._build_status_msg(chat, message)
        elif content == "/关键词状态":
            priv = "开启" if self.config.chat_keyword_switch else "关闭"
            grp = "开启" if self.config.group_keyword_switch else "关闭"
            at = "是" if self.config.group_keyword_at_only else "否"
            cnt = len(self.config.keyword_dict)
            keys = ", ".join(self.config.keyword_dict.keys()) if self.config.keyword_dict else "（无）"
            result = chat.SendMsg(
                f"私聊关键词：{priv}\n"
                f"群聊关键词：{grp}\n"
                f"群聊仅@触发：{at}\n"
                f"关键词数量：{cnt} 个\n"
                f"关键词列表：{keys}"
            )
        elif content == "/开启群聊关键词@触发":
            self.config.set_config('group_keyword_at_only', True)
            result = chat.SendMsg("群聊关键词已设为：仅被@时触发")
        elif content == "/关闭群聊关键词@触发":
            self.config.set_config('group_keyword_at_only', False)
            result = chat.SendMsg("群聊关键词已设为：无论是否@均触发")
        elif content == "/记忆状态":
            sw = "开启" if self.config.memory_switch else "关闭"
            result = chat.SendMsg(
                f"对话记忆：{sw}\n"
                f"上下文条数：{self.config.memory_context_count} 条\n"
                f"最大存储：{self.config.memory_max_count} 条"
            )
        elif content == "/开启记忆":
            self.config.set_config('memory_switch', True)
            result = chat.SendMsg("对话记忆已开启")
        elif content == "/关闭记忆":
            self.config.set_config('memory_switch', False)
            result = chat.SendMsg("对话记忆已关闭")
        elif content == "/回复延迟状态":
            sw = "开启" if self.config.reply_delay_switch else "关闭"
            result = chat.SendMsg(
                f"回复延迟：{sw}\n"
                f"延迟范围：{self.config.reply_delay_min}~{self.config.reply_delay_max}s"
            )
        elif content == "/开启回复延迟":
            self.config.set_config('reply_delay_switch', True)
            result = chat.SendMsg(f"回复延迟已开启（{self.config.reply_delay_min}~{self.config.reply_delay_max}s）")
        elif content == "/关闭回复延迟":
            self.config.set_config('reply_delay_switch', False)
            result = chat.SendMsg("回复延迟已关闭")
        elif content == "/暂停私聊自动回复":
            self.config.set_config('chat_listen_only', True)
            result = chat.SendMsg("私聊已开启只监听不 AI 回复；监听、记忆、关键词回复和自定义转发保持运行。发送 /恢复私聊自动回复 可关闭")
        elif content == "/恢复私聊自动回复":
            self.config.set_config('chat_listen_only', False)
            result = chat.SendMsg("私聊只监听不 AI 回复已关闭，私聊 AI 自动回复已恢复")
        elif content == "/暂停群聊自动回复":
            self.config.set_config('group_listen_only', True)
            result = chat.SendMsg("群聊已开启只监听不 AI 回复；监听、记忆、关键词回复和自定义转发保持运行。发送 /恢复群聊自动回复 可关闭")
        elif content == "/恢复群聊自动回复":
            self.config.set_config('group_listen_only', False)
            result = chat.SendMsg("群聊只监听不 AI 回复已关闭，群聊 AI 自动回复已恢复")
        elif content == "/自动回复状态":
            chat_st = "只监听不 AI 回复" if self.config.chat_listen_only else "AI 自动回复开启"
            group_st = "只监听不 AI 回复" if self.config.group_listen_only else "AI 自动回复开启"
            result = chat.SendMsg(
                f"--- 自动回复状态 ---\n"
                f"私聊：{chat_st}\n"
                f"群聊：{group_st}"
            )
        elif content.startswith("/接口测试"):
            message_re = message
            message_re.content = re.sub("/接口测试", "", message.content).strip()
            result = self.bot.wx_send_ai(chat, message_re)
        elif content == "/Prompt列表":
            result = self.handle_list_prompts(chat, message)
        elif content == "/当前Prompt":
            name = self.config.default_prompt
            body = self.config.get_prompt_content(name)
            result = chat.SendMsg(f"当前默认Prompt（{name}）：\n{body}")
        elif content.startswith("/切换Prompt"):
            result = self.handle_switch_prompt(chat, message)
        elif content == "/清除记忆":
            result = self.handle_clear_memory(chat, message)
        elif content.startswith("/清除用户记忆"):
            result = self.handle_clear_user_memory(chat, message)
        elif content == "/清除全部记忆":
            result = self.handle_clear_all_memory(chat, message)
        elif content == "/图片识别状态":
            result = self.handle_image_recognition_status(chat, message)
        elif content == "/拆分回复状态":
            result = self.handle_split_reply_status(chat, message)
        elif content == "/开启私聊拆分回复":
            self.config.set_config('chat_split_reply_switch', True)
            result = chat.SendMsg(f"私聊拆分回复已开启（单条≤{self.config.chat_split_max_chars}字，最多{self.config.chat_split_max_count}条）")
        elif content == "/关闭私聊拆分回复":
            self.config.set_config('chat_split_reply_switch', False)
            result = chat.SendMsg("私聊拆分回复已关闭")
        elif content == "/开启群聊拆分回复":
            self.config.set_config('group_split_reply_switch', True)
            result = chat.SendMsg(f"群聊拆分回复已开启（单条≤{self.config.group_split_max_chars}字，最多{self.config.group_split_max_count}条）")
        elif content == "/关闭群聊拆分回复":
            self.config.set_config('group_split_reply_switch', False)
            result = chat.SendMsg("群聊拆分回复已关闭")
        elif content == "/开启私聊关键词":
            self.config.set_config('chat_keyword_switch', True)
            result = chat.SendMsg("私聊关键词回复已开启")
        elif content == "/关闭私聊关键词":
            self.config.set_config('chat_keyword_switch', False)
            result = chat.SendMsg("私聊关键词回复已关闭")
        elif content == "/开启群聊关键词":
            self.config.set_config('group_keyword_switch', True)
            result = chat.SendMsg("群聊关键词回复已开启")
        elif content == "/关闭群聊关键词":
            self.config.set_config('group_keyword_switch', False)
            result = chat.SendMsg("群聊关键词回复已关闭")
        elif content == "/新好友状态":
            result = self.handle_new_friend_status(chat, message)
        elif content == "/查看错误回复":
            result = chat.SendMsg(f"接口失败固定回复：{self.config.api_error_reply}")
        elif content.startswith("/设置错误回复"):
            new_err = re.sub("/设置错误回复", "", content).strip()
            if new_err:
                self.config.set_config('api_error_reply', new_err)
                result = chat.SendMsg(f"接口失败固定回复已更新：{new_err}")
            else:
                result = chat.SendMsg("请提供回复内容，如：/设置错误回复 在忙，我稍后回复您")
        elif content.startswith("/清除计数"):
            target = re.sub("/清除计数", "", content).strip()
            if not target:
                result = chat.SendMsg("请提供用户昵称，如：/清除计数 张三")
            elif self.bot.reply_count_store.clear_user(target):
                result = chat.SendMsg(f"已清除 {target} 的回复计数与通知状态")
            else:
                result = chat.SendMsg(f"未找到 {target} 的计数记录（可能尚未触发过回复）")
        elif content == "/消息存储状态":
            result = self.handle_message_store_status(chat, message)
        elif content == "/开启私聊回复确认":
            self.config.set_config('chat_reply_confirm_switch', True)
            result = chat.SendMsg("私聊回复确认已开启")
        elif content == "/关闭私聊回复确认":
            self.config.set_config('chat_reply_confirm_switch', False)
            result = chat.SendMsg("私聊回复确认已关闭")
        elif content == "/待确认列表":
            result = self.handle_pending_confirm_list(chat, message)
        elif content.startswith("/确认回复"):
            result = self.handle_confirm_reply(chat, message)
        elif content.startswith("/取消回复"):
            result = self.handle_cancel_reply(chat, message)
        elif content == "/查看未读消息":
            result = self.handle_unread_messages(chat, message)
        elif content.startswith("/标记已读"):
            result = self.handle_mark_read(chat, message)
        elif content.startswith("/标记未读"):
            result = self.handle_mark_unread(chat, message)
        elif content == "/微信锁状态":
            result = self.handle_wx_lock_status(chat, message)
        elif content == "/占用微信锁":
            result = self.handle_acquire_wx_lock(chat, message)
        elif content == "/释放微信锁":
            result = self.handle_release_wx_lock(chat, message)
        elif content == "/强制释放微信锁":
            result = self.handle_force_release_wx_lock(chat, message)
        elif content == "/开启微信锁":
            self.config.set_config('wx_lock_enabled', True)
            result = chat.SendMsg("微信界面操作锁已开启")
        elif content == "/关闭微信锁":
            self.config.set_config('wx_lock_enabled', False)
            result = chat.SendMsg("微信界面操作锁已关闭")
        else:
            if message.attr != "self":
                result = self.bot.wx_send_ai(chat, message)

        return result

    def _build_status_msg(self, chat, message):
        """
        构建并发送机器人当前状态摘要信息。
        """
        wx_nickname = self.bot.wx.nickname if self.wx else "未知"
        send_msg = f"账号：{wx_nickname}\n"
        send_msg += "运行时间：" + self.config.get_run_time(self.bot.start_time) + "\n"
        send_msg += f"当前接口：{self.config.api_index + 1}/{len(self.config.api_configs)}  SDK：{self.config.api_sdk}  模型：{self.bot.api.DS_NOW_MOD}\n"
        send_msg += f"已收消息：{self.bot.msg_received_count} 条  已回复：{self.bot.msg_replied_count} 条\n"
        if self.bot.last_msg_time:
            send_msg += f"最近消息：{self.bot.last_msg_sender}（{self.bot.last_msg_time}）\n"

        if self.config.AllListen_switch:
            send_msg += "当前模式：黑名单模式\n"
            send_msg += "当前黑名单：" + ", ".join(self.config.listen_list) + "\n"
        else:
            send_msg += "当前模式：白名单模式\n"
            send_msg += "当前白名单：" + ", ".join(self.config.listen_list) + "\n"

        if self.config.group_switch:
            send_msg += "当前群机器人状态：开启\n"
            send_msg += "当前群：" + ", ".join(self.config.group) + "\n"
            if self.config.group_welcome:
                send_msg += f"当前群机器人欢迎语状态：开启 欢迎概率：{self.config.group_welcome_random}\n"
            else:
                send_msg += "当前群机器人欢迎语状态：关闭\n"
        else:
            send_msg += "当前群机器人状态：关闭\n"

        send_msg += "当前私聊关键词回复状态：" + ("开启\n" if self.config.chat_keyword_switch else "关闭\n")
        send_msg += "当前群聊关键词回复状态：" + ("开启\n" if self.config.group_keyword_switch else "关闭\n")
        if self.config.group_keyword_switch:
            send_msg += "群聊关键词仅@触发：" + ("是\n" if self.config.group_keyword_at_only else "否\n")
        send_msg += f"关键词数量：{len(self.config.keyword_dict)} 个\n"
        if self.config.keyword_dict:
            send_msg += "当前关键词：" + ", ".join(self.config.keyword_dict.keys()) + "\n"

        send_msg += "对话记忆：" + ("开启" if self.config.memory_switch else "关闭")
        if self.config.memory_switch:
            send_msg += f"  上下文条数：{self.config.memory_context_count}\n"
        else:
            send_msg += "\n"

        send_msg += "回复延迟：" + ("开启" if self.config.reply_delay_switch else "关闭")
        if self.config.reply_delay_switch:
            send_msg += f"  延迟范围：{self.config.reply_delay_min}~{self.config.reply_delay_max}s\n"
        else:
            send_msg += "\n"

        send_msg += "当前定时消息状态：" + ("开启\n" if self.config.scheduled_msg_switch else "关闭\n")
        send_msg += "私聊图片识别：" + ("开启" if self.config.chat_image_recognition_switch else "关闭")
        send_msg += "  群聊图片识别：" + ("开启\n" if self.config.group_image_recognition_switch else "关闭\n")
        send_msg += "私聊拆分回复：" + ("开启" if self.config.chat_split_reply_switch else "关闭")
        send_msg += "  群聊拆分回复：" + ("开启\n" if self.config.group_split_reply_switch else "关闭\n")
        send_msg += "新好友自动通过：" + ("开启" if self.config.new_frined_switch else "关闭")
        send_msg += "  自动回复：" + ("开启\n" if self.config.new_frien_reply_switch else "关闭\n")
        send_msg += f"当前默认Prompt：{self.config.default_prompt}\n"
        send_msg += f"接口失败回复：{self.config.api_error_reply}\n"

        return chat.SendMsg(send_msg)

    def handle_add_user(self, chat, message):
        """处理 /添加用户 指令：将用户加入监听列表并注册监听"""
        user_to_add = re.sub("/添加用户", "", message.content).strip()
        self.config.add_user(user_to_add)
        if not self.config.AllListen_switch:
            result = self.bot.wx.AddListenChat(nickname=user_to_add, callback=self.bot.message_handle_callback)
            if result:
                log(message=f"添加用户 {user_to_add} 监听完成")
                return chat.SendMsg('添加用户完成\n' + ", ".join(self.config.listen_list))
            else:
                self.config.remove_user(user_to_add)
                log(level="ERROR", message=f"添加用户 {user_to_add} 监听失败, {result['message']}")
                return chat.SendMsg(
                    f"添加用户失败\n{result['message']}\n" + ", ".join(self.config.listen_list)
                )
        else:
            return chat.SendMsg('添加用户完成(黑名单)\n' + ", ".join(self.config.listen_list))

    def handle_remove_user(self, chat, message):
        """处理 /删除用户 指令：移除用户的监听注册并从配置中删除"""
        user_to_remove = re.sub("/删除用户", "", message.content).strip()
        self.bot.wx.RemoveListenChat(user_to_remove)
        self.config.remove_user(user_to_remove)
        return chat.SendMsg('删除用户完成\n' + ", ".join(self.config.listen_list))

    def handle_group_switch_status(self, chat, message):
        """处理 /群机器人状态 指令：返回当前群机器人开关状态"""
        if self.config.group_switch:
            result = chat.SendMsg(message.content + '为关闭')
        else:
            result = chat.SendMsg(message.content + '为开启')
        return result

    def handle_add_group(self, chat, message):
        """处理 /添加群 指令：将群组加入监听列表并注册监听"""
        new_group = re.sub("/添加群", "", message.content).strip()
        self.config.add_group(new_group)
        if self.config.group_switch:
            result = self.bot.wx.AddListenChat(nickname=new_group, callback=self.bot.message_handle_callback)
            if result:
                log(message=f"添加群组 {new_group} 监听完成")
                return chat.SendMsg('添加群完成\n' + ", ".join(self.config.group))
            else:
                self.config.remove_group(new_group)
                log(level="ERROR", message=f"添加群组 {new_group} 监听失败, {result['message']}")
                return chat.SendMsg(
                    f"添加群失败\n{result['message']}\n" + ", ".join(self.config.group)
                )
        else:
            return chat.SendMsg('添加群完成(群机器人未开启)\n' + ", ".join(self.config.group))

    def handle_remove_group(self, chat, message):
        """处理 /删除群 指令：移除群组的监听注册并从配置中删除"""
        group_to_remove = re.sub("/删除群", "", message.content).strip()
        self.bot.wx.RemoveListenChat(group_to_remove)
        self.config.remove_group(group_to_remove)
        return chat.SendMsg('删除群完成\n' + ", ".join(self.config.group))

    def handle_enable_group_bot(self, chat, message):
        """处理 /开启群机器人 指令：开启群机器人并重新初始化监听器"""
        try:
            self.config.set_config(id='group_switch', new_content=True)
            self.bot.init_wx_listeners()
            return chat.SendMsg(message.content + ' 完成\n' + '当前群：\n' + ", ".join(self.config.group))
        except Exception as e:
            self.config.set_config('group_switch', False)
            self.bot.init_wx_listeners()
            chat.SendMsg(
                message.content
                + ' 失败\n请重新配置群名称或者检查机器人号是否在群或者群名中是否含有非法中文字符\n'
                + '当前群:' + ", ".join(self.config.group)
                + '\n当前群机器人状态:' + str(self.config.group_switch)
            )

    def handle_disable_group_bot(self, chat, message):
        """处理 /关闭群机器人 指令：关闭群机器人并移除所有群组监听"""
        self.config.set_config(id='group_switch', new_content=False)
        for user in self.config.group:
            self.bot.wx.RemoveListenChat(user)
        return chat.SendMsg(message.content + ' 完成\n' + '当前群：\n' + ", ".join(self.config.group))

    def handle_enable_welcome_msg(self, chat, message):
        """处理 /开启群机器人欢迎语 指令"""
        self.config.group_welcome = True
        self.config.set_config('group_welcome', True)
        return chat.SendMsg(message.content + ' 完成\n' + '当前群：\n' + ", ".join(self.config.group))

    def handle_disable_welcome_msg(self, chat, message):
        """处理 /关闭群机器人欢迎语 指令"""
        self.config.group_welcome = False
        self.config.set_config('group_welcome', False)
        return chat.SendMsg(message.content + ' 完成\n' + '当前群：\n' + ", ".join(self.config.group))

    def handle_welcome_msg_status(self, chat, message):
        """处理 /群机器人欢迎语状态 指令：返回当前欢迎语开关状态"""
        status = "开启" if self.config.group_welcome else "关闭"
        return chat.SendMsg(f"/群机器人欢迎语状态 为{status}\n当前群：\n" + ", ".join(self.config.group))

    def handle_change_welcome_msg(self, chat, message):
        """处理 /更改群机器人欢迎语为 指令：更新群欢迎语内容"""
        new_welcome = re.sub("/更改群机器人欢迎语为", "", message.content).strip()
        self.config.set_config('group_welcome_msg', new_welcome)
        return chat.SendMsg('群机器人欢迎语已更新\n' + self.config.group_welcome_msg)

    def handle_list_api_configs(self, chat, message):
        """处理 /查看接口列表 指令：返回所有接口配置的摘要"""
        lines = ["接口列表："]
        for i, cfg in enumerate(self.config.api_configs):
            mark = "▶ " if i == self.config.api_index else "   "
            lines.append(f"{mark}{i + 1}. {cfg.get('sdk', '')} | {cfg.get('model', '')} | {cfg.get('url', '')}")
        return chat.SendMsg('\n'.join(lines))

    def handle_select_api_config(self, chat, message):
        """处理 /选择接口 N 指令：切换到第 N 个接口配置（1-indexed）"""
        num_str = re.sub("/选择接口", "", message.content).strip()
        try:
            n = int(num_str)
        except ValueError:
            return chat.SendMsg("接口序号无效，请输入数字，如：/选择接口 2")
        idx = n - 1
        if idx < 0 or idx >= len(self.config.api_configs):
            return chat.SendMsg(f"接口 {n} 不存在，当前共 {len(self.config.api_configs)} 个接口")
        self.config.config['api_index'] = idx
        self.config.save_config()
        self.config.refresh_config()
        self.bot.api = self.bot._init_api()
        self.bot.api_cache = {}
        cfg = self.config.api_configs[idx]
        return chat.SendMsg(f"已切换至接口 {n}\nSDK：{cfg.get('sdk', '')}\n模型：{cfg.get('model', '')}")

    def handle_change_prompt(self, chat, message):
        """处理 /更改AI设定为 指令：更新默认 prompt 文件内容"""
        if "AI设定" in message.content:
            new_prompt = re.sub("/更改AI设定为", "", message.content).strip()
        else:
            new_prompt = re.sub("/更改ai设定为", "", message.content).strip()
        target = os.path.join(self.config.prompt_dir, f'{self.config.default_prompt}.md')
        try:
            with open(target, 'w', encoding='utf-8') as f:
                f.write(new_prompt)
            log(message=f"默认 prompt 已更新：{target}")
        except Exception as e:
            log(level="ERROR", message=f"更新默认 prompt 文件失败: {e}")
            return chat.SendMsg(f'AI设定更新失败：{e}')
        return chat.SendMsg(f'默认AI设定（{self.config.default_prompt}）已更新\n' + new_prompt)

    def handle_list_prompts(self, chat, message):
        """处理 /Prompt列表 指令：列出所有可用 Prompt 名称"""
        try:
            files = sorted([f[:-3] for f in os.listdir(self.config.prompt_dir) if f.endswith('.md')])
        except Exception:
            files = []
        if not files:
            return chat.SendMsg("当前没有可用的 Prompt")
        current = self.config.default_prompt
        lines = ["可用 Prompt 列表（* 为当前默认）："]
        for name in files:
            mark = "* " if name == current else "  "
            lines.append(f"{mark}{name}")
        return chat.SendMsg('\n'.join(lines))

    def handle_switch_prompt(self, chat, message):
        """处理 /切换Prompt xxx 指令：切换默认 Prompt"""
        name = re.sub("/切换Prompt", "", message.content).strip()
        if not name:
            return chat.SendMsg("请提供 Prompt 名称，如：/切换Prompt 默认")
        path = os.path.join(self.config.prompt_dir, f'{name}.md')
        if not os.path.exists(path):
            try:
                files = sorted([f[:-3] for f in os.listdir(self.config.prompt_dir) if f.endswith('.md')])
            except Exception:
                files = []
            available = '、'.join(files) if files else '（无）'
            return chat.SendMsg(f"Prompt「{name}」不存在\n可用 Prompt：{available}")
        self.config.set_config('default_prompt', name)
        return chat.SendMsg(f"默认 Prompt 已切换为：{name}")

    def handle_clear_memory(self, chat, message):
        """处理 /清除记忆 指令：清除管理员（当前聊天）的对话记忆"""
        if not self.bot.memory_manager:
            return chat.SendMsg("记忆功能未初始化")
        self.bot.memory_manager.clear_messages(self.config.cmd)
        return chat.SendMsg(f"已清除「{self.config.cmd}」的对话记忆")

    def handle_clear_user_memory(self, chat, message):
        """处理 /清除用户记忆 xxx 指令：清除指定用户/群的记忆"""
        name = re.sub("/清除用户记忆", "", message.content).strip()
        if not name:
            return chat.SendMsg("请提供用户或群名称，如：/清除用户记忆 张三")
        if not self.bot.memory_manager:
            return chat.SendMsg("记忆功能未初始化")
        self.bot.memory_manager.clear_messages(name)
        return chat.SendMsg(f"已清除「{name}」的对话记忆")

    def handle_clear_all_memory(self, chat, message):
        """处理 /清除全部记忆 指令：清除所有对话记忆"""
        if not self.bot.memory_manager:
            return chat.SendMsg("记忆功能未初始化")
        count = self.bot.memory_manager.clear_all_messages()
        return chat.SendMsg(f"已清除所有对话记忆（共 {count} 个会话）")

    def handle_image_recognition_status(self, chat, message):
        """处理 /图片识别状态 指令：返回私聊和群聊图片识别开关及接口信息"""
        def api_label(idx):
            if 0 <= idx < len(self.config.api_configs):
                cfg = self.config.api_configs[idx]
                return f"接口{idx + 1}（{cfg.get('model', '')}）"
            return f"接口{idx + 1}"
        chat_sw = "开启" if self.config.chat_image_recognition_switch else "关闭"
        group_sw = "开启" if self.config.group_image_recognition_switch else "关闭"
        lines = [
            "--- 图片识别状态 ---",
            f"私聊图片识别：{chat_sw}  识别接口：{api_label(self.config.chat_image_recognition_api)}",
            f"群聊图片识别：{group_sw}  识别接口：{api_label(self.config.group_image_recognition_api)}",
        ]
        return chat.SendMsg('\n'.join(lines))

    def handle_split_reply_status(self, chat, message):
        """处理 /拆分回复状态 指令：返回私聊和群聊拆分回复配置"""
        chat_sw = "开启" if self.config.chat_split_reply_switch else "关闭"
        group_sw = "开启" if self.config.group_split_reply_switch else "关闭"
        lines = [
            "--- 拆分多条回复状态 ---",
            f"私聊拆分回复：{chat_sw}  单条≤{self.config.chat_split_max_chars}字  最多{self.config.chat_split_max_count}条",
            f"群聊拆分回复：{group_sw}  单条≤{self.config.group_split_max_chars}字  最多{self.config.group_split_max_count}条",
        ]
        return chat.SendMsg('\n'.join(lines))

    def handle_new_friend_status(self, chat, message):
        """处理 /新好友状态 指令：返回新好友自动通过和自动回复配置"""
        accept = "开启" if self.config.new_frined_switch else "关闭"
        reply = "开启" if self.config.new_frien_reply_switch else "关闭"
        use_name = "是" if self.config.new_friend_remark_use_nickname else "否"
        prefix_time = "是" if self.config.new_friend_remark_prefix_timestamp else "否"
        suffix_time = "是" if self.config.new_friend_remark_suffix_timestamp else "否"
        msgs = self.config.new_frien_msg if self.config.new_frien_msg else ["（无）"]
        lines = [
            "--- 新好友状态 ---",
            f"自动通过好友申请：{accept}",
            f"自动回复新好友：{reply}",
            f"备注采用昵称：{use_name}",
            f"备注前缀：{self.config.new_friend_remark_prefix or '（空）'}  前缀加时间戳：{prefix_time}",
            f"备注后缀：{self.config.new_friend_remark_suffix or '（空）'}  后缀加时间戳：{suffix_time}",
            "自动回复消息：",
        ] + [f"  · {m}" for m in msgs]
        return chat.SendMsg('\n'.join(lines))

    def handle_message_store_status(self, chat, message):
        """处理 /消息存储状态 指令：返回消息存储配置及统计"""
        if not self.message_store:
            return chat.SendMsg("消息存储功能未初始化")
        
        stats = self.message_store.get_stats()
        confirm_sw = "开启" if self.config.chat_reply_confirm_switch else "关闭"
        
        lines = [
            "--- 消息存储状态 ---",
            f"私聊回复确认：{confirm_sw}",
            f"确认等待超时：{self.config.chat_reply_confirm_wait_timeout}秒",
            f"单会话最大存储：{self.config.message_store_max_count}条",
            f"总消息数：{stats.get('total_count', 0)}",
            f"会话数：{stats.get('chat_count', 0)}",
            f"待确认回复：{stats.get('pending_count', 0)}",
            f"未读消息：{stats.get('unread_count', 0)}",
        ]
        return chat.SendMsg('\n'.join(lines))

    def handle_pending_confirm_list(self, chat, message):
        """处理 /待确认列表 指令：查看所有待确认的回复"""
        if not self.message_store:
            return chat.SendMsg("消息存储功能未初始化")
        
        pending = self.message_store.get_pending_confirms()
        if not pending:
            return chat.SendMsg("暂无待确认的回复")
        
        lines = ["--- 待确认回复列表 ---"]
        for p in pending[:10]:
            lines.append(f"ID: {p.get('id', '')}")
            lines.append(f"  会话: {p.get('chat_name', '')}")
            lines.append(f"  发送者: {p.get('sender', '')}")
            lines.append(f"  消息: {p.get('content', '')[:50]}...")
            lines.append(f"  待发送回复: {p.get('pending_reply', '')[:50]}...")
            lines.append(f"  等待时间: {p.get('pending_time', '')}")
            lines.append("")
        
        if len(pending) > 10:
            lines.append(f"... 还有 {len(pending) - 10} 条待确认回复")
        
        return chat.SendMsg('\n'.join(lines))

    def handle_confirm_reply(self, chat, message):
        """处理 /确认回复 ID 指令：确认并发送指定待确认回复"""
        if not self.message_store:
            return chat.SendMsg("消息存储功能未初始化")
        
        msg_id = re.sub("/确认回复", "", message.content).strip()
        if not msg_id:
            return chat.SendMsg("请提供消息ID，如：/确认回复 abc123")
        
        result = self.message_store.confirm_reply(msg_id)
        if result:
            return chat.SendMsg(f"已确认并发送消息 {msg_id} 的回复")
        else:
            return chat.SendMsg(f"未找到消息 {msg_id} 或该消息无需确认")

    def handle_cancel_reply(self, chat, message):
        """处理 /取消回复 ID 指令：取消指定待确认回复"""
        if not self.message_store:
            return chat.SendMsg("消息存储功能未初始化")
        
        msg_id = re.sub("/取消回复", "", message.content).strip()
        if not msg_id:
            return chat.SendMsg("请提供消息ID，如：/取消回复 abc123")
        
        result = self.message_store.cancel_reply(msg_id)
        if result:
            return chat.SendMsg(f"已取消消息 {msg_id} 的待确认回复")
        else:
            return chat.SendMsg(f"未找到消息 {msg_id} 或该消息无需确认")

    def handle_unread_messages(self, chat, message):
        """处理 /查看未读消息 指令：查看所有未读消息"""
        if not self.message_store:
            return chat.SendMsg("消息存储功能未初始化")
        
        unread = self.message_store.get_unread_messages()
        if not unread:
            return chat.SendMsg("暂无未读消息")
        
        lines = ["--- 未读消息列表 ---"]
        for msg in unread[:10]:
            lines.append(f"ID: {msg.get('id', '')}")
            lines.append(f"  会话: {msg.get('chat_name', '')}")
            lines.append(f"  发送者: {msg.get('sender', '')}")
            lines.append(f"  消息: {msg.get('content', '')[:50]}...")
            lines.append(f"  时间: {msg.get('message_time', '')}")
            lines.append("")
        
        if len(unread) > 10:
            lines.append(f"... 还有 {len(unread) - 10} 条未读消息")
        
        return chat.SendMsg('\n'.join(lines))

    def handle_mark_read(self, chat, message):
        """处理 /标记已读 ID 指令：将指定消息标记为已读"""
        if not self.message_store:
            return chat.SendMsg("消息存储功能未初始化")
        
        msg_id = re.sub("/标记已读", "", message.content).strip()
        if not msg_id:
            return chat.SendMsg("请提供消息ID，如：/标记已读 abc123")
        
        result = self.message_store.set_read(msg_id)
        if result:
            return chat.SendMsg(f"消息 {msg_id} 已标记为已读")
        else:
            return chat.SendMsg(f"未找到消息 {msg_id}")

    def handle_mark_unread(self, chat, message):
        """处理 /标记未读 ID 指令：将指定消息标记为未读"""
        if not self.message_store:
            return chat.SendMsg("消息存储功能未初始化")
        
        msg_id = re.sub("/标记未读", "", message.content).strip()
        if not msg_id:
            return chat.SendMsg("请提供消息ID，如：/标记未读 abc123")
        
        result = self.message_store.set_unread(msg_id)
        if result:
            return chat.SendMsg(f"消息 {msg_id} 已标记为未读")
        else:
            return chat.SendMsg(f"未找到消息 {msg_id}")

    def handle_wx_lock_status(self, chat, message):
        """处理 /微信锁状态 指令：查看微信锁当前状态"""
        if not self.wx_lock:
            return chat.SendMsg("微信锁功能未初始化")
        
        status = self.wx_lock.get_status()
        enabled = "开启" if self.config.wx_lock_enabled else "关闭"
        
        lines = [
            "--- 微信界面操作锁状态 ---",
            f"锁开关：{enabled}",
            f"锁状态：{'已占用' if status.get('held', False) else '空闲'}",
        ]
        
        if status.get('held', False):
            lines.append(f"占用者：{status.get('holder', '未知')}")
            lines.append(f"占用时间：{status.get('hold_time', '未知')}")
            lines.append(f"已占用：{status.get('held_duration', '0秒')}")
        
        lines.append(f"超时时间：{self.config.wx_lock_timeout}秒")
        return chat.SendMsg('\n'.join(lines))

    def handle_acquire_wx_lock(self, chat, message):
        """处理 /占用微信锁 指令：手动占用微信锁"""
        if not self.wx_lock:
            return chat.SendMsg("微信锁功能未初始化")
        
        if not self.config.wx_lock_enabled:
            return chat.SendMsg("微信锁已关闭，请先开启")
        
        result = self.wx_lock.acquire(holder="manual", timeout=5)
        if result:
            return chat.SendMsg("微信锁已成功占用")
        else:
            return chat.SendMsg("微信锁获取失败，可能被其他任务占用中")

    def handle_release_wx_lock(self, chat, message):
        """处理 /释放微信锁 指令：手动释放微信锁"""
        if not self.wx_lock:
            return chat.SendMsg("微信锁功能未初始化")
        
        result = self.wx_lock.release(holder="manual")
        if result:
            return chat.SendMsg("微信锁已成功释放")
        else:
            return chat.SendMsg("微信锁未被占用或占用者不匹配")

    def handle_force_release_wx_lock(self, chat, message):
        """处理 /强制释放微信锁 指令：强制释放微信锁"""
        if not self.wx_lock:
            return chat.SendMsg("微信锁功能未初始化")
        
        self.wx_lock.force_release()
        return chat.SendMsg("微信锁已强制释放")

    def send_command_list(self, chat):
        """发送全量指令帮助列表"""
        commands = (
            '指令目录（发送对应指令查看详细）：\n'
            '/系统状态指令\n'
            '/用户管理指令\n'
            '/群组管理指令\n'
            '/Prompt管理指令\n'
            '/关键词指令\n'
            '/记忆指令\n'
            '/延迟指令\n'
            '/暂停恢复指令\n'
            '/图片识别指令\n'
            '/拆分回复指令\n'
            '/新好友指令\n'
            '/接口指令\n'
            '/计数器指令\n'
            '/消息存储指令\n'
            '/微信锁指令\n'
            '作者:https://www.siver.top'
        )
        return chat.SendMsg(commands)
