#!/usr/bin/env python3
"""
朋友圈功能测试脚本
支持两种测试方式：
1. 直接API调用测试
2. 通过任务队列测试（推荐，与项目实际运行方式一致）
"""

import argparse
import os
import sys
import time
from datetime import datetime

try:
    from wxautox4 import WeChat
except ImportError:
    print("错误：无法导入 wxautox4，请确保已安装依赖")
    sys.exit(1)


class MockBot:
    """模拟机器人对象，用于初始化任务队列"""
    
    def __init__(self, wx):
        self.wx = wx
        self.config = type('Config', (), {'redis_enabled': False})()


def test_get_moments(wx):
    """测试获取朋友圈动态列表（直接API调用）"""
    print("\n" + "=" * 50)
    print("测试：获取朋友圈动态列表")
    print("=" * 50)
    
    try:
        moments = wx.GetMoments(count=10)
        print(f"成功获取 {len(moments)} 条朋友圈动态")
        
        if moments:
            for i, moment in enumerate(moments[:5], 1):
                print(f"\n{i}. 发布者: {moment.get('nickname', '未知')}")
                content = moment.get('content', '')
                if content:
                    print(f"   内容: {content[:50]}..." if len(content) > 50 else f"   内容: {content}")
                else:
                    print(f"   内容: （无文字内容）")
                print(f"   图片数: {moment.get('image_count', 0)}")
                print(f"   时间: {moment.get('time', '未知')}")
        
        return True
    except Exception as e:
        print(f"获取朋友圈失败: {e}")
        return False


def test_send_text_moment_direct(wx, text):
    """测试发送纯文字朋友圈（直接API调用）"""
    print("\n" + "=" * 50)
    print("测试：发送纯文字朋友圈（直接调用）")
    print("=" * 50)
    
    if not text:
        text = f"测试朋友圈 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    print(f"准备发送内容: {text}")
    
    try:
        result = wx.SendMoments(text=text)
        print(f"发送结果: {result}")
        
        if result and hasattr(result, 'success') and result.success:
            print("✓ 纯文字朋友圈发送成功")
            return True
        else:
            print("✗ 纯文字朋友圈发送失败")
            return False
    except Exception as e:
        print(f"发送纯文字朋友圈失败: {e}")
        return False


def test_send_image_moment_direct(wx, image_paths):
    """测试发送带图片的朋友圈（直接API调用）"""
    print("\n" + "=" * 50)
    print("测试：发送带图片的朋友圈（直接调用）")
    print("=" * 50)
    
    if not image_paths:
        print("未提供图片路径，跳过此测试")
        return True
    
    valid_images = []
    for img_path in image_paths:
        if os.path.exists(img_path):
            valid_images.append(img_path)
            print(f"✓ 图片存在: {img_path}")
        else:
            print(f"✗ 图片不存在: {img_path}")
    
    if not valid_images:
        print("没有有效的图片路径，跳过此测试")
        return True
    
    text = f"测试图片朋友圈 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    print(f"准备发送 {len(valid_images)} 张图片，文字内容: {text}")
    
    try:
        result = wx.SendMoments(text=text, images=valid_images)
        print(f"发送结果: {result}")
        
        if result and hasattr(result, 'success') and result.success:
            print("✓ 带图片朋友圈发送成功")
            return True
        else:
            print("✗ 带图片朋友圈发送失败")
            return False
    except Exception as e:
        print(f"发送带图片朋友圈失败: {e}")
        return False


def test_like_moment_direct(wx, nickname):
    """测试点赞朋友圈（直接API调用）"""
    print("\n" + "=" * 50)
    print("测试：点赞朋友圈（直接调用）")
    print("=" * 50)
    
    if not nickname:
        print("未提供点赞对象，跳过此测试")
        return True
    
    print(f"准备点赞发布者: {nickname}")
    
    try:
        result = wx.LikeMoment(nickname)
        print(f"点赞结果: {result}")
        
        if result and hasattr(result, 'success') and result.success:
            print("✓ 点赞成功")
            return True
        else:
            print("✗ 点赞失败")
            return False
    except Exception as e:
        print(f"点赞失败: {e}")
        return False


def test_send_moments_via_queue(wx, text, images=None):
    """测试通过任务队列发送朋友圈"""
    print("\n" + "=" * 50)
    print("测试：通过任务队列发送朋友圈")
    print("=" * 50)
    
    if images is None:
        images = []
    
    if not text:
        text = f"队列测试朋友圈 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    print(f"准备通过队列发送，内容: {text}")
    if images:
        print(f"图片数量: {len(images)}")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from core.task_queue import TaskQueue
        from core.redis_manager import RedisManager
        
        mock_bot = MockBot(wx)
        mock_bot.redis_manager = RedisManager(mock_bot.config)
        
        task_queue = TaskQueue(mock_bot)
        
        params = {'text': text}
        if images:
            params['images'] = images
        
        task_id = task_queue.submit(
            task_type='send_moments',
            params=params,
            priority=5
        )
        
        print(f"✓ 任务已提交，任务ID: {task_id}")
        print("等待任务执行...")
        
        for _ in range(30):
            time.sleep(1)
            status = task_queue.get_queue_status()
            pending = status.get('pending_count', 0)
            current = status.get('current_task')
            
            if pending == 0 and not current:
                break
        
        history = task_queue.get_history(limit=1)
        if history:
            task = history[0]
            print(f"任务状态: {task.status}")
            if task.status == 'completed':
                print("✓ 通过任务队列发送朋友圈成功")
                task_queue.stop()
                return True
            elif task.error:
                print(f"✗ 任务执行失败: {task.error}")
                task_queue.stop()
                return False
        
        task_queue.stop()
        print("✗ 任务执行超时或未完成")
        return False
        
    except Exception as e:
        print(f"通过任务队列发送失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_like_moment_via_queue(wx, nickname):
    """测试通过任务队列点赞朋友圈"""
    print("\n" + "=" * 50)
    print("测试：通过任务队列点赞朋友圈")
    print("=" * 50)
    
    if not nickname:
        print("未提供点赞对象，跳过此测试")
        return True
    
    print(f"准备通过队列点赞发布者: {nickname}")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from core.task_queue import TaskQueue
        from core.redis_manager import RedisManager
        
        mock_bot = MockBot(wx)
        mock_bot.redis_manager = RedisManager(mock_bot.config)
        
        task_queue = TaskQueue(mock_bot)
        
        task_id = task_queue.submit(
            task_type='like_moments',
            params={'moment_id': nickname},
            priority=5
        )
        
        print(f"✓ 任务已提交，任务ID: {task_id}")
        print("等待任务执行...")
        
        for _ in range(15):
            time.sleep(1)
            status = task_queue.get_queue_status()
            pending = status.get('pending_count', 0)
            current = status.get('current_task')
            
            if pending == 0 and not current:
                break
        
        history = task_queue.get_history(limit=1)
        if history:
            task = history[0]
            print(f"任务状态: {task.status}")
            if task.status == 'completed':
                print("✓ 通过任务队列点赞成功")
                task_queue.stop()
                return True
            elif task.error:
                print(f"✗ 任务执行失败: {task.error}")
                task_queue.stop()
                return False
        
        task_queue.stop()
        print("✗ 任务执行超时或未完成")
        return False
        
    except Exception as e:
        print(f"通过任务队列点赞失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description='微信朋友圈功能测试')
    
    parser.add_argument('--get', action='store_true', help='测试获取朋友圈列表（直接调用）')
    parser.add_argument('--send-text', type=str, default='', help='测试发送纯文字朋友圈（直接调用）')
    parser.add_argument('--send-image', nargs='+', default=[], help='测试发送带图片的朋友圈（直接调用）')
    parser.add_argument('--like', type=str, default='', help='测试点赞朋友圈（直接调用）')
    
    parser.add_argument('--queue-send', action='store_true', help='测试通过任务队列发送朋友圈')
    parser.add_argument('--queue-like', type=str, default='', help='测试通过任务队列点赞朋友圈')
    
    parser.add_argument('--all', action='store_true', help='执行所有测试（直接调用方式）')
    parser.add_argument('--all-queue', action='store_true', help='执行所有测试（任务队列方式）')
    
    parser.add_argument('--nickname', type=str, default=None, help='微信昵称（多账号时指定）')
    parser.add_argument('--text', type=str, default='', help='自定义朋友圈文字内容')
    parser.add_argument('--images', nargs='+', default=[], help='自定义图片路径')
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("微信朋友圈功能测试")
    print("=" * 50)
    
    try:
        print("正在连接微信...")
        wx = WeChat(nickname=args.nickname)
        print(f"✓ 成功连接微信，当前账号: {wx.nickname}")
    except Exception as e:
        print(f"✗ 连接微信失败: {e}")
        print("请确保微信已登录且主窗口已打开")
        sys.exit(1)
    
    results = []
    
    if args.all or args.get:
        results.append(('获取朋友圈', test_get_moments(wx)))
    
    if args.all or args.send_text:
        confirm = input("\n即将发送朋友圈，请确认 (y/n): ").strip().lower()
        if confirm == 'y':
            text = args.send_text or args.text
            results.append(('发送纯文字朋友圈', test_send_text_moment_direct(wx, text)))
        else:
            print("取消发送")
    
    if args.all or args.send_image:
        confirm = input("\n即将发送带图片的朋友圈，请确认 (y/n): ").strip().lower()
        if confirm == 'y':
            images = args.send_image or args.images
            results.append(('发送带图片朋友圈', test_send_image_moment_direct(wx, images)))
        else:
            print("取消发送")
    
    if args.all or args.like:
        confirm = input("\n即将点赞朋友圈，请确认 (y/n): ").strip().lower()
        if confirm == 'y':
            results.append(('点赞朋友圈', test_like_moment_direct(wx, args.like)))
        else:
            print("取消点赞")
    
    if args.all_queue or args.queue_send:
        confirm = input("\n即将通过任务队列发送朋友圈，请确认 (y/n): ").strip().lower()
        if confirm == 'y':
            text = args.text or ''
            images = args.images or []
            results.append(('队列发送朋友圈', test_send_moments_via_queue(wx, text, images)))
        else:
            print("取消发送")
    
    if args.all_queue or args.queue_like:
        confirm = input("\n即将通过任务队列点赞朋友圈，请确认 (y/n): ").strip().lower()
        if confirm == 'y':
            results.append(('队列点赞朋友圈', test_like_moment_via_queue(wx, args.queue_like)))
        else:
            print("取消点赞")
    
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{test_name}: {status}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if total > 0:
        wx.Moment.Close()
        print("已返回聊天界面")


if __name__ == "__main__":
    main()