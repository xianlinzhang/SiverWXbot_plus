import random
import re
import time
from datetime import datetime, timedelta
from logger import log


class WXUtils:
    """
    微信辅助功能模块
    负责处理新好友验证、群欢迎语、定时消息等辅助功能。
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.wx_lock = bot.wx_lock if hasattr(bot, 'wx_lock') else None

    def find_new_group_friend(self, msg, flag):
        """
        从系统消息中解析出新加入群聊的成员昵称。

        :param msg:  系统消息文本
        :param flag: 引号索引（1=扫码加入，3=邀请加入）
        :return:     新成员昵称字符串
        """
        text = msg
        try:
            first_quote_content = text.split('"')[flag]
        except Exception:
            first_quote_content = text.split('"')[1]
        return first_quote_content

    def send_group_welcome_msg(self, chat, message):
        """
        处理群系统消息，若检测到新成员加入则按概率发送欢迎语。

        :param chat:    聊天窗口子对象
        :param message: 系统消息对象
        :return:        发送结果
        """
        result = True
        log(message=f"{chat.who} 系统消息:" + message.content)

        try:
            if self.wx_lock:
                self.wx_lock.acquire(holder=f"send_group_welcome_{chat.who}")

            if "加入群聊" in message.content and random.random() < self.config.group_welcome_random:
                new_friend = self.find_new_group_friend(message.content, 1)
                log(message=f"{chat.who} 新群友:" + new_friend)
                time.sleep(5)
                result = chat.SendMsg(msg=self.config.group_welcome_msg, at=new_friend)

            elif "加入了群聊" in message.content and random.random() < self.config.group_welcome_random:
                new_friend = self.find_new_group_friend(message.content, 3)
                log(message=f"{chat.who} 新群友:" + new_friend)
                time.sleep(5)
                result = chat.SendMsg(msg=self.config.group_welcome_msg, at=new_friend)
        finally:
            if self.wx_lock:
                self.wx_lock.release(holder=f"send_group_welcome_{chat.who}")

        return result

    def is_image_path(self, s: str) -> bool:
        """
        判断字符串是否为有效的图片文件完整路径。
        支持 Windows（C:\\...）和 Unix（/home/...）风格路径。

        :param s: 待判断的字符串
        :return:  True 表示是图片路径，False 则不是
        """
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
        if not s.lower().endswith(image_extensions):
            return False
        pattern = re.compile(
            r'^('
            r'([A-Za-z]:[\\/])'
            r'|'
            r'(/[^/]+)'
            r')'
            r'.+'
            r'\.(png|jpg|jpeg|gif|bmp|webp)$',
            re.IGNORECASE,
        )
        return bool(pattern.match(s))

    @staticmethod
    def _remark_unit_len(text):
        """按微信备注近似限制计算长度：ASCII 算 1，中文和特殊字符算 2。"""
        total = 0
        for ch in str(text or ""):
            try:
                total += len(ch.encode("gbk"))
            except UnicodeEncodeError:
                total += 2
        return total

    @classmethod
    def _truncate_remark_units(cls, text, max_units):
        """按备注长度单位裁剪，不截断字符。"""
        if max_units <= 0:
            return ""
        result = []
        used = 0
        for ch in str(text or ""):
            try:
                unit = len(ch.encode("gbk"))
            except UnicodeEncodeError:
                unit = 2
            if used + unit > max_units:
                break
            result.append(ch)
            used += unit
        return "".join(result)

    def build_new_friend_remark(self, nickname):
        """根据面板配置生成新好友备注，并裁剪到微信备注长度限制内。"""
        max_units = 32
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        leading = timestamp if self.config.new_friend_remark_prefix_timestamp else ""
        prefix = str(self.config.new_friend_remark_prefix or "")
        name = str(nickname or "") if self.config.new_friend_remark_use_nickname else ""
        suffix = str(self.config.new_friend_remark_suffix or "")
        trailing = timestamp if self.config.new_friend_remark_suffix_timestamp else ""

        fixed_left = leading + prefix
        fixed_right = suffix + trailing
        fixed_units = self._remark_unit_len(fixed_left) + self._remark_unit_len(fixed_right)
        if fixed_units <= max_units:
            name_units = max_units - fixed_units
            remark = fixed_left + self._truncate_remark_units(name, name_units) + fixed_right
        else:
            trailing_units = self._remark_unit_len(trailing)
            available_main_units = max(0, max_units - trailing_units)
            main = self._truncate_remark_units(fixed_left + suffix, available_main_units)
            remark = main + trailing
        if not remark:
            fallback = str(nickname or "新好友") if self.config.new_friend_remark_use_nickname else "新好友"
            remark = self._truncate_remark_units(fallback, max_units)
        return remark

    def Pass_New_Friends(self):
        """
        检测并批量通过新好友请求，通过后按需自动发送打招呼消息。
        """
        try:
            if self.wx_lock:
                self.wx_lock.acquire(holder="Pass_New_Friends")

            NewFriends = self.bot.wx.GetNewFriends(acceptable=True)
            time.sleep(1)
            if len(NewFriends) != 0:
                log(message="以下是新朋友：\n" + str(NewFriends))
                for new in NewFriends:
                    new_name = self.build_new_friend_remark(new.name)
                    tags = self.config.new_friend_tags if self.config.new_friend_tags else None
                    new.accept(remark=new_name, tags=tags)
                    log(message="已通过" + new_name + "的好友请求")
                    self.bot.wx.SwitchToChat()
                    time.sleep(5)
                    if self.config.new_frien_reply_switch:
                        for msg in self.config.new_frien_msg:
                            if self.is_image_path(msg):
                                self.bot.wx.SendFiles(who=new_name, filepath=msg)
                            else:
                                self.bot.wx.SendMsg(who=new_name, msg=msg)
                            self.config.human_delay()
                    self.bot.wx.ChatWith(who='文件传输助手')
                    time.sleep(1)
                    self.bot.wx.SwitchToContact()
                time.sleep(1)
            self.bot.wx.SwitchToChat()
            time.sleep(1)
        finally:
            if self.wx_lock:
                self.wx_lock.release(holder="Pass_New_Friends")

    def send_scheduled_msg(self, targets, msgs, repeat_type, weekdays, dates, task_id):
        """
        定时触发的消息发送函数，根据 repeat_type 判断今天是否需要发送。

        :param targets:     接收消息的用户/群组昵称列表
        :param msgs:        要发送的消息列表
        :param repeat_type: 重复类型 (once/daily/weekly/monthly/custom)
        :param weekdays:    每周几发送 (1=周一 ... 7=周日)
        :param dates:       自定义日期列表 (["2026-03-20", ...]) 或每月几号 ([1, 15, ...])
        :param task_id:     任务ID，用于 once 类型执行后自动禁用
        """
        now = datetime.now()
        should_send = False

        if repeat_type == 'daily':
            should_send = True
        elif repeat_type == 'weekly':
            should_send = now.isoweekday() in weekdays
        elif repeat_type == 'monthly':
            should_send = now.day in dates
        elif repeat_type == 'custom':
            today_str = now.strftime('%Y-%m-%d')
            should_send = today_str in dates
        elif repeat_type == 'once':
            today_str = now.strftime('%Y-%m-%d')
            should_send = today_str in dates
        else:
            should_send = True

        if not should_send:
            return None

        log(message=f"定时消息时间到（{repeat_type}），目标：{targets}，正在发送...")
        try:
            if self.wx_lock:
                self.wx_lock.acquire(holder=f"send_scheduled_msg_{task_id}")

            for user in targets:
                for msg in msgs:
                    log(message=f"正在向 {user} 发送定时消息：{msg}")
                    try:
                        if self.is_image_path(msg):
                            result = self.bot.wx.SendFiles(who=user, filepath=msg)
                        else:
                            result = self.bot.wx.SendMsg(msg=msg, who=user)
                        self.config.human_delay()
                        if not result:
                            log(level="ERROR", message=f"定时消息发送失败：{result['message']}")
                            self.bot.is_err(
                                self.bot.wx.nickname + f" wxbot定时消息发送失败！",
                                f"{user} 定时消息发送失败：{result['message']}",
                            )
                    except Exception as e:
                        log(level="ERROR", message=f"定时消息发送失败：{e}")
                        self.bot.is_err(
                            self.bot.wx.nickname + f" wxbot定时消息发送失败！",
                            f"{user} 定时消息发送失败：{e}",
                        )
        finally:
            if self.wx_lock:
                self.wx_lock.release(holder=f"send_scheduled_msg_{task_id}")

        if repeat_type == 'once':
            for task in self.config.scheduled_msg_list:
                if task.get('id') == task_id:
                    task['enabled'] = False
                    break
            self.config.config['scheduled_msg_list'] = self.config.scheduled_msg_list
            self.config.save_config()
            log(message=f"一次性定时任务 {task_id} 已执行完毕，自动禁用")
            return None

    def send_scheduled_moments(self, text, images, privacy, tags, repeat_type, weekdays, dates, task_id):
        """
        定时触发的朋友圈发送函数，根据 repeat_type 判断今天是否需要发送。

        :param text:        朋友圈文字内容
        :param images:     图片路径列表
        :param privacy:    可见范围 (public/friends_only/tagged/friends_except)
        :param tags:       可见/不可见的标签列表
        :param repeat_type: 重复类型 (once/daily/weekly/monthly/custom)
        :param weekdays:   每周几发送
        :param dates:      自定义日期列表或每月几号
        :param task_id:    任务ID
        """
        now = datetime.now()
        should_send = False

        if repeat_type == 'daily':
            should_send = True
        elif repeat_type == 'weekly':
            should_send = now.isoweekday() in weekdays
        elif repeat_type == 'monthly':
            should_send = now.day in dates
        elif repeat_type == 'custom':
            today_str = now.strftime('%Y-%m-%d')
            should_send = today_str in dates
        elif repeat_type == 'once':
            today_str = now.strftime('%Y-%m-%d')
            should_send = today_str in dates
        else:
            should_send = True

        if not should_send:
            return None

        log(message=f"定时朋友圈时间到（{repeat_type}），正在发送...")
        try:
            if self.wx_lock:
                self.wx_lock.acquire(holder=f"send_scheduled_moments_{task_id}")

            result = self.bot.wx.SendMoments(text=text, images=images, privacy=privacy, tags=tags)
            log(message=f"定时朋友圈发送成功：{result}")
        except Exception as e:
            log(level="ERROR", message=f"定时朋友圈发送失败：{e}")
            self.bot.is_err(
                self.bot.wx.nickname + f" wxbot定时朋友圈发送失败！",
                f"定时朋友圈发送失败：{e}",
            )
        finally:
            if self.wx_lock:
                self.wx_lock.release(holder=f"send_scheduled_moments_{task_id}")

        if repeat_type == 'once':
            for task in self.config.scheduled_moments_list:
                if task.get('id') == task_id:
                    task['enabled'] = False
                    break
            self.config.config['scheduled_moments_list'] = self.config.scheduled_moments_list
            self.config.save_config()
            log(message=f"一次性定时朋友圈任务 {task_id} 已执行完毕，自动禁用")
            return None

    def _do_moments_like(self):
        """执行随机朋友圈点赞操作。"""
        try:
            if self.wx_lock:
                self.wx_lock.acquire(holder="_do_moments_like")

            moments = self.bot.wx.GetMoments(count=self.config.moments_like_count)
            if moments:
                liked_count = 0
                for moment in moments:
                    if liked_count >= self.config.moments_like_count:
                        break
                    if not moment.get('liked', False):
                        result = self.bot.wx.LikeMoment(moment.get('id', ''))
                        if result:
                            liked_count += 1
                            log(message=f"点赞朋友圈成功：{moment.get('nickname', '')}")
                log(message=f"随机朋友圈点赞完成，共点赞 {liked_count} 条")
        except Exception as e:
            log(level="ERROR", message=f"随机朋友圈点赞出错：{e}")
        finally:
            if self.wx_lock:
                self.wx_lock.release(holder="_do_moments_like")

    def _check_random_moments(self):
        """检查是否需要发送随机朋友圈。"""
        now = datetime.now()
        if self.bot._random_moments_state.get('next_time') and now >= self.bot._random_moments_state['next_time']:
            try:
                if self.wx_lock:
                    self.wx_lock.acquire(holder="_check_random_moments")

                templates = self.config.random_moments_list
                if templates:
                    template = random.choice(templates)
                    text = template.get('text', '')
                    images = template.get('images', [])
                    privacy = template.get('privacy', 'public')
                    tags = template.get('tags', [])
                    result = self.bot.wx.SendMoments(text=text, images=images, privacy=privacy, tags=tags)
                    log(message=f"随机朋友圈发送成功：{result}")
            except Exception as e:
                log(level="ERROR", message=f"随机朋友圈发送出错：{e}")
            finally:
                if self.wx_lock:
                    self.wx_lock.release(holder="_check_random_moments")
            self.bot._random_moments_state['next_time'] = None

        if not self.bot._random_moments_state.get('next_time'):
            min_interval = self.config.random_moments_min_interval * 60
            max_interval = self.config.random_moments_max_interval * 60
            delay_seconds = random.randint(min_interval, max_interval)
            self.bot._random_moments_state['next_time'] = now + timedelta(seconds=delay_seconds)
            log(message=f"随机朋友圈下次触发：{self.bot._random_moments_state['next_time'].strftime('%H:%M:%S')}（{delay_seconds // 60} 分钟后）")

    def _check_random_msg(self):
        """检查是否需要发送随机消息。"""
        now = datetime.now()
        for target, state in list(self.bot._random_msg_state.items()):
            if state.get('next_time') and now >= state['next_time']:
                try:
                    if self.wx_lock:
                        self.wx_lock.acquire(holder=f"_check_random_msg_{target}")

                    msgs = self.config.random_msg_list.get(target, [])
                    if msgs:
                        msg = random.choice(msgs)
                        if self.is_image_path(msg):
                            result = self.bot.wx.SendFiles(who=target, filepath=msg)
                        else:
                            result = self.bot.wx.SendMsg(who=target, msg=msg)
                        log(message=f"随机消息发送成功：{target}")
                except Exception as e:
                    log(level="ERROR", message=f"随机消息发送出错：{target} - {e}")
                finally:
                    if self.wx_lock:
                        self.wx_lock.release(holder=f"_check_random_msg_{target}")
                self.bot._random_msg_state[target]['next_time'] = None

            if not self.bot._random_msg_state[target].get('next_time'):
                min_interval = self.config.random_msg_min_interval * 60
                max_interval = self.config.random_msg_max_interval * 60
                delay_seconds = random.randint(min_interval, max_interval)
                self.bot._random_msg_state[target]['next_time'] = now + timedelta(seconds=delay_seconds)
                log(message=f"随机消息下次触发 [{target}]：{self.bot._random_msg_state[target]['next_time'].strftime('%H:%M:%S')}（{delay_seconds // 60} 分钟后）")
