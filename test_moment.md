# 微信朋友圈功能测试脚本使用说明

## 概述

`test_moment.py` 是用于测试微信朋友圈功能的独立脚本，支持两种测试方式：

1. **直接 API 调用** - 直接调用 `wxautox4` 提供的接口，适合快速验证功能
2. **任务队列调用** - 通过项目的任务队列提交任务，与项目实际运行方式一致

## 测试功能

| 功能 | 直接调用 | 队列调用 |
|------|---------|---------|
| 获取朋友圈列表 | ✅ | - |
| 发送纯文字朋友圈 | ✅ | ✅ |
| 发送带图片朋友圈 | ✅ | ✅ |
| 点赞朋友圈 | ✅ | ✅ |

## 前置条件

1. 微信已登录且主窗口已打开
2. 已安装项目依赖（`wxautox4`、`redis` 等）
3. 运行脚本前请确保微信界面可见

## 使用方法

### 获取朋友圈列表

```bash
python test_moment.py --get
```

### 发送纯文字朋友圈（直接调用）

```bash
python test_moment.py --send-text "今天天气真好！"
```

### 发送带图片朋友圈（直接调用）

```bash
python test_moment.py --send-image "D:/Images/photo1.jpg" "D:/Images/photo2.jpg"
```

### 点赞朋友圈（直接调用）

```bash
python test_moment.py --like "张三"
```

### 通过任务队列发送朋友圈

```bash
python test_moment.py --queue-send --text "你好，世界"
```

### 通过任务队列点赞朋友圈

```bash
python test_moment.py --queue-like "张三"
```

### 执行所有直接调用测试

```bash
python test_moment.py --all
```

### 执行所有队列测试

```bash
python test_moment.py --all-queue
```

## 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `--get` | flag | 获取朋友圈列表（直接调用） |
| `--send-text` | string | 发送纯文字朋友圈（直接调用） |
| `--send-image` | list | 发送带图片朋友圈（直接调用） |
| `--like` | string | 点赞朋友圈（直接调用） |
| `--queue-send` | flag | 通过任务队列发送朋友圈 |
| `--queue-like` | string | 通过任务队列点赞朋友圈 |
| `--all` | flag | 执行所有直接调用测试 |
| `--all-queue` | flag | 执行所有队列测试 |
| `--nickname` | string | 指定微信昵称（多账号时使用） |
| `--text` | string | 自定义朋友圈文字内容 |
| `--images` | list | 自定义图片路径 |

## 项目中的任务队列流程

项目中朋友圈操作的实际执行流程：

1. **提交任务** → `task_queue.submit('send_moments', params)`
2. **队列存储** → 任务存入 Redis（或本地文件 fallback）
3. **工作线程** → 后台线程轮询队列，按优先级执行
4. **执行处理** → `_handle_send_moments()` 调用 `wx.SendMoments()`
5. **结果记录** → 任务状态更新到历史记录

核心代码位于 `core/task_queue.py`:

```python
def _handle_send_moments(self, params: Dict[str, Any]) -> Any:
    text = params.get('text', '')
    images = params.get('images', [])
    privacy = params.get('privacy', 'public')
    tags = params.get('tags', [])
    return self.bot.wx.SendMoments(text=text, images=images, privacy=privacy, tags=tags)
```

## 注意事项

1. **发送操作需确认**：发送朋友圈和点赞操作会有二次确认提示，防止误操作
2. **图片路径**：使用绝对路径，支持 .png、.jpg、.jpeg、.gif、.bmp、.webp 格式
3. **图片数量**：微信朋友圈最多支持9张图片
4. **队列测试超时**：队列测试最多等待30秒，超时后自动结束
5. **测试完成后**：脚本会自动返回聊天界面

## 示例输出

```
==================================================
微信朋友圈功能测试
==================================================
正在连接微信...
✓ 成功连接微信，当前账号: 我的昵称

==================================================
测试：获取朋友圈动态列表
==================================================
成功获取 8 条朋友圈动态

1. 发布者: 张三
   内容: 今天去了一个很棒的地方...
   图片数: 3
   时间: 2小时前

2. 发布者: 李四
   内容: （无文字内容）
   图片数: 1
   时间: 5小时前

==================================================
测试结果汇总
==================================================
获取朋友圈: ✓ 通过

总计: 1/1 通过
已返回聊天界面
```

## 文件结构

```
test_moment.py        # 测试脚本
test_moment.md        # 本说明文档
core/
├── task_queue.py     # 任务队列实现
└── redis_manager.py  # Redis 管理器
wxautox4/
├── wx.py             # WeChat 类（含朋友圈接口）
└── moment.py         # 朋友圈底层实现
```