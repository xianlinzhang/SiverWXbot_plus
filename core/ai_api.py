import os
import json
import time
import base64
import hashlib
import mimetypes
import requests
from openai import OpenAI
from cozepy import Coze
from cozepy.auth import TokenAuth
from cozepy import Message, ChatEventType
from cozepy import COZE_CN_BASE_URL
from logger import log

from core._version import version
from core.dify_client import Client


class OpenAIAPI:
    """
    OpenAI 兼容接口封装类
    适用于所有兼容 OpenAI SDK 格式的 AI 服务（如 DeepSeek、通义等）。
    """

    def __init__(self, config):
        self.config = config
        self.DS_NOW_MOD = config.model1
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=30.0,
            max_retries=2,
            default_headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*"
            }
        )

    @staticmethod
    def _image_to_data_url(image_path: str = "", image_url: str = "") -> str:
        if image_path:
            mime_type, _ = mimetypes.guess_type(image_path)
            if mime_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                mime_type = "image/jpeg"
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
            return f"data:{mime_type};base64,{image_data}"
        if image_url:
            return image_url
        raise ValueError("image_path 和 image_url 不能同时为空")

    @classmethod
    def _build_chat_image_block(cls, image_path: str = "", image_url: str = "") -> dict:
        return {
            "type": "image_url",
            "image_url": {"url": cls._image_to_data_url(image_path, image_url)}
        }

    @classmethod
    def _build_responses_image_block(cls, image_path: str = "", image_url: str = "") -> dict:
        return {
            "type": "input_image",
            "image_url": {"url": cls._image_to_data_url(image_path, image_url)}
        }

    def chat(self, message, model=None, stream=False, prompt=None, history=None,
             image_path: str = "", image_url: str = "", user_key=None):
        """
        调用 OpenAI 兼容接口获取 AI 回复。

        :param message: 用户输入的消息内容
        :param model:   指定模型，为 None 时使用当前默认模型
        :param stream:  是否使用流式输出
        :param prompt:  系统提示词，为 None 时使用配置中的 prompt
        :param history: 历史消息列表（MemoryManager.get_messages 返回值）
        :param image_path: 本地图片路径，优先于 image_url
        :param image_url:  图片 URL，image_path 为空时使用
        :return:        AI 回复的文本字符串
        """
        if model is None:
            model = self.DS_NOW_MOD
        if prompt is None:
            prompt = self.config.prompt

        messages = [{"role": "system", "content": prompt}]
        if history:
            for h in history:
                role = "assistant" if h.get('attr') == 'self' else "user"
                t = h.get('time', '')
                raw = h.get('content', '')
                sender = h.get('sender', '')
                if role == 'user' and sender:
                    content = f"[{t}] {sender}: {raw}" if t else f"{sender}: {raw}"
                else:
                    content = f"[{t}] {raw}" if t else raw
                messages.append({"role": role, "content": content})
        if image_path or image_url:
            user_content = [
                {"type": "text", "text": message},
                self._build_chat_image_block(image_path, image_url),
            ]
        else:
            user_content = message
        messages.append({"role": "user", "content": user_content})

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=stream,
            )
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            log(level="WARN", message=f"Chat Completions API 调用失败 [{error_type}]: {error_msg}")
            log(level="INFO", message="尝试备用方案（Responses API）")
            return self._try_responses_api(message, model, stream, prompt, image_path, image_url)

        try:
            if stream:
                reasoning_content = ""
                content = ""
                chunk_count = 0

                for chunk in response:
                    chunk_count += 1

                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    if not hasattr(choice, 'delta'):
                        continue

                    delta = choice.delta

                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        reasoning_content += delta.reasoning_content

                    if hasattr(delta, 'content') and delta.content:
                        content += delta.content

                result = content.strip() if content.strip() else reasoning_content.strip()
                if result:
                    log(message=f"API 流式返回成功（共 {chunk_count} 个块）：{result[:100]}...")
                    return result
                else:
                    log(level="WARN", message=f"流式响应为空（收到 {chunk_count} 个块），尝试备用方案")
                    return self._try_responses_api(message, model, stream, prompt, image_path, image_url)
            else:
                if response.choices and len(response.choices) > 0:
                    message_obj = response.choices[0].message

                    if hasattr(message_obj, 'content') and message_obj.content:
                        output = message_obj.content
                        log(message=f"API 非流式返回成功：{output[:100]}...")
                        return output
                    else:
                        log(level="WARN", message="非流式响应内容为空，尝试备用方案")
                        return self._try_responses_api(message, model, stream, prompt, image_path, image_url)
                else:
                    log(level="WARN", message="响应中没有 choices，尝试备用方案")
                    return self._try_responses_api(message, model, stream, prompt, image_path, image_url)
        except Exception as e:
            error_type = type(e).__name__
            log(level="WARN", message=f"解析 API 响应出错 [{error_type}]: {str(e)}，尝试备用方案")
            return self._try_responses_api(message, model, stream, prompt, image_path, image_url)

    def _try_responses_api(self, message, model, stream, prompt, image_path="", image_url=""):
        """
        备用方案：使用 Responses API 调用。
        当 Chat Completions API 返回非 JSON 格式时自动降级到此方案。
        注意：备用方案暂不支持流式输出，统一使用非流式模式。
        """
        try:
            if stream:
                log(level="WARN", message="备用方案不支持流式输出，将使用非流式模式")

            log(message=f"备用方案：使用 Responses API, model={model}")
            if image_path or image_url:
                input_text = f"这是prompt，请不要把这个当做用户输入：{prompt}\n\n这是用户消息，你需要参照prompt来回复用户消息：{message}" if prompt and prompt.strip() else message
                input_payload = [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": input_text},
                        self._build_responses_image_block(image_path, image_url),
                    ],
                }]
            else:
                input_payload = f"这是prompt，请不要把这个当做用户输入：{prompt}\n\n这是用户消息，你需要参照prompt来回复用户消息：{message}" if prompt and prompt.strip() else message

            response = self.client.responses.create(
                model=model,
                input=input_payload,
                reasoning={"effort": "none"}
            )

            if response.output and len(response.output) > 0:
                output_item = response.output[0]
                if hasattr(output_item, 'content') and output_item.content:
                    text = output_item.content[0].text
                    log(message=f"备用方案返回成功：{text[:100]}...")
                    return text

            log(level="WARN", message="备用方案响应内容为空")
            return "API返回错误，请稍后再试"

        except Exception as e:
            log(level="ERROR", message=f"备用方案也失败 [{type(e).__name__}]: {str(e)}")
            return "API返回错误，请稍后再试"


class DifyAPI:
    """
    Dify 平台 API 封装类
    基于 core.dify_client（官方类型化客户端）调用自部署/云端的 Dify。
    支持 chat（Chat App / Chatflow，真实服务端会话）与 workflow（Workflow App）两类应用。
    """

    _KNOWN_ENDPOINTS = ("/chat-messages", "/completion-messages", "/workflows/run")

    def __init__(self, config):
        self.config = config
        self.DS_NOW_MOD = getattr(config, 'model1', '')
        self.api_key = getattr(config, 'api_key', '')
        self.base_url = (getattr(config, 'base_url', '') or '').strip()
        self.app_type = getattr(config, 'app_type', 'chat') or 'chat'
        self.workflow_input_key = getattr(config, 'workflow_input_key', 'query') or 'query'
        self.workflow_output_key = getattr(config, 'workflow_output_key', 'text') or 'text'
        self.api_base = self._resolve_api_base(self.base_url)
        self.client = Client(
            api_key=self.api_key,
            api_base=self.api_base,
        )
        self.request_timeout = max(5, int(getattr(config, 'ai_request_timeout', 120)))
        self._redis = None

    @classmethod
    def _resolve_api_base(cls, base_url):
        """
        从完整端点地址解析出 Dify 服务根地址（api_base）。
        base_url 可能带 /chat-messages 等端点尾缀、尾斜杠或 query 参数。
        """
        if not base_url:
            return base_url
        # 去除 query / fragment
        if '?' in base_url or '#' in base_url:
            base_url = base_url.split('?', 1)[0].split('#', 1)[0]
        base_url = base_url.rstrip('/')
        # 剥掉已知端点尾缀
        for ep in cls._KNOWN_ENDPOINTS:
            if base_url.endswith(ep):
                base_url = base_url[: -len(ep)].rstrip('/')
                break
        return base_url

    def _get_redis(self):
        """惰性创建 RedisManager（message_store 模式），受 redis_enabled 开关控制。"""
        if self._redis is not None:
            return self._redis
        self._redis = False
        try:
            if not getattr(self.config, 'redis_enabled', False):
                return False
            from core.redis_manager import RedisManager
            redis_config = {
                'host': getattr(self.config, 'redis_host', 'localhost'),
                'port': getattr(self.config, 'redis_port', 6379),
                'db': getattr(self.config, 'redis_db', 0),
                'password': getattr(self.config, 'redis_password', None),
                'timeout': getattr(self.config, 'redis_timeout', 5),
                'retry_count': getattr(self.config, 'redis_retry_count', 3),
                'fallback': getattr(self.config, 'redis_fallback', True),
                'fallback_path': getattr(self.config, 'redis_fallback_path', './fallback_redis.json'),
            }
            self._redis = RedisManager(redis_config)
        except Exception as e:
            log(level="WARN", message=f"Dify 会话存储初始化失败，本次不续会话: {e}")
            self._redis = False
        return self._redis

    def _conv_redis_key(self, user_key):
        return "dify:conv:" + hashlib.md5(
            f"{self.api_base}|{self.api_key}".encode('utf-8')
        ).hexdigest() + ":" + str(user_key)

    def _dify_user(self, user_key):
        return f"wxbot_{hashlib.md5(str(user_key).encode('utf-8')).hexdigest()[:12]}"

    def _resolve_conv_id(self, user_key):
        """读取该会话已持久化的 conversation_id；无会话/不可用返回空串。"""
        if not user_key:
            return ""
        redis = self._get_redis()
        if not redis:
            return ""
        try:
            value = redis.get(self._conv_redis_key(user_key))
            return str(value) if value else ""
        except Exception as e:
            log(level="WARN", message=f"Dify 读取会话失败: {e}")
            return ""

    def _save_conv_id(self, user_key, conversation_id):
        """持久化 conversation_id；无会话/不可用静默跳过，不影响回复。"""
        if not user_key or not conversation_id:
            return
        redis = self._get_redis()
        if not redis:
            return
        try:
            redis.set(self._conv_redis_key(user_key), conversation_id)
        except Exception as e:
            log(level="WARN", message=f"Dify 保存会话失败: {e}")

    def _chat_chatflow(self, query, user_key=None):
        """chat 型：真实服务端会话（conversation_id 持久化复用）。"""
        from core.dify_client.models import ChatRequest, ResponseMode

        conversation_id = self._resolve_conv_id(user_key)
        req = ChatRequest(
            query=query,
            response_mode=ResponseMode.BLOCKING,
            user=self._dify_user(user_key or "default"),
            conversation_id=conversation_id or "",
        )
        resp = self.client.chat_messages(req, timeout=self.request_timeout)
        if resp.conversation_id:
            self._save_conv_id(user_key, resp.conversation_id)
        return resp.answer

    def _chat_workflow(self, message, prompt=None, user_key=None, model=None, history=None):
        """
        workflow 型：入参按 workflow_input_key 键值映射传入，出参按 workflow_output_key 提取。
        workflow_input_key 支持多键映射，如 "msgs=$message,prompt=$prompt"；
        占位符见 _build_workflow_inputs。未用占位符则取值原样。
        """
        from core.dify_client.models import ResponseMode, WorkflowsRunRequest

        inputs = self._build_workflow_inputs(message, prompt, user_key=user_key, model=model, history=history)
        req = WorkflowsRunRequest(
            inputs=inputs,
            response_mode=ResponseMode.BLOCKING,
            user=self._dify_user(user_key or "default"),
        )
        resp = self.client.run_workflows(req, timeout=self.request_timeout)
        outputs = resp.data.outputs or {} if resp.data else {}
        value = outputs.get(self.workflow_output_key)
        if value is None:
            raise ValueError(
                f"工作流输出缺少变量 [{self.workflow_output_key}]，可用输出: {list(outputs.keys())}"
            )
        text = str(value)
        if not text.strip():
            raise ValueError(f"工作流输出变量 [{self.workflow_output_key}] 为空")
        return text

    def _build_workflow_inputs(self, message, prompt=None, user_key=None, model=None, history=None):
        """
        解析 workflow_input_key 键值映射并填充 inputs。

        格式：以逗号分隔的 key=value 对；value 支持占位符：
          $message  - 用户消息
          $prompt   - 提示词（chat() 的 prompt 实参）
          $model    - 模型名（可能为空）
          $user_key - 会话身份（如微信 chat_name，可能为空）
          $history  - 历史消息（渲染为 "角色: 内容" 多行文本，可能为空）
          $time     - 当前时间 YYYY-MM-DD HH:MM:SS
          $date     - 当前日期 YYYY-MM-DD
        例如 "msgs=$message,prompt=$prompt"。未用占位符则取值原样。
        解析结果为空时退化为 {"query": message}，保持向后兼容。
        """
        import time as _time

        spec = (self.workflow_input_key or "query").strip()
        inputs = {}
        now = _time.localtime()
        for pair in spec.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if "$message" in value:
                value = value.replace("$message", message)
            if "$prompt" in value:
                value = value.replace("$prompt", prompt or "")
            if "$model" in value:
                value = value.replace("$model", model or "")
            if "$user_key" in value:
                value = value.replace("$user_key", user_key or "")
            if "$history" in value:
                value = value.replace("$history", self._render_workflow_history(history))
            if "$time" in value:
                value = value.replace("$time", _time.strftime("%Y-%m-%d %H:%M:%S", now))
            if "$date" in value:
                value = value.replace("$date", _time.strftime("%Y-%m-%d", now))
            inputs[key] = value
        if not inputs:
            inputs[self.workflow_input_key or "query"] = message
        return inputs

    def _render_workflow_history(self, history):
        """把 history 渲染为多行文本（复用 chat() 的拼接风格）。"""
        if not history:
            return ""
        return "\n".join([
            f"[{h.get('time', '')}] {'助手' if h.get('attr') == 'self' else h.get('sender', '用户')}: {h.get('content', '')}"
            for h in history
        ])

    def chat(self, message, model=None, stream=True, prompt=None, history=None, user_key=None):
        """
        调用 Dify 接口，返回 AI 回复文本。

        :param message: 用户输入内容
        :param history: 历史消息列表（拼接为上下文前缀，行为与重构前一致）
        :param user_key: 会话身份标识（如微信 chat_name），用于 conversation_id 隔离持久化
        :return:        AI 回复字符串
        """
        query = message
        if history:
            ctx = "\n".join([
                f"[{h.get('time', '')}] {'助手' if h.get('attr') == 'self' else h.get('sender', '用户')}: {h.get('content', '')}"
                for h in history
            ])
            query = f"[历史对话]\n{ctx}\n[当前消息]\n{message}"

        try:
            if self.app_type == "workflow":
                result = self._chat_workflow(message, prompt=prompt, user_key=user_key, model=model, history=history)
            else:
                result = self._chat_chatflow(query, user_key=user_key)
            log(message=f"AI回复: {result[:100]}")
            return result
        except Exception as e:
            log(level="ERROR", message=f"Dify API 调用失败 [{type(e).__name__}]: {str(e)}")
            return "API返回错误，请稍后再试"


class CozeAPI:
    """
    扣子（Coze）平台 API 封装类
    使用扣子官方 Python SDK（cozepy）进行流式对话。
    """

    def __init__(self, config):
        self.config = config
        self.DS_NOW_MOD = config.model1
        self.bot_id     = config.model1
        self.user_id    = "SiverWxBot"
        self.api_key    = config.api_key
        self.base_url   = COZE_CN_BASE_URL
        self.coze = Coze(
            auth=TokenAuth(token=self.api_key),
            base_url=self.base_url,
        )

    def chat(self, message, model=None, stream=True, prompt=None, history=None, user_key=None):
        """
        调用扣子流式接口获取 AI 回复，并拼接完整的回答文本。

        :param message: 用户输入内容
        :param history: 历史消息列表
        :return:        AI 回复字符串
        """
        additional_messages = []
        if history:
            for h in history:
                t = h.get('time', '')
                raw = h.get('content', '')
                sender = h.get('sender', '')
                if h.get('attr') == 'self':
                    content = f"[{t}] {raw}" if t else raw
                    try:
                        additional_messages.append(Message.build_assistant_answer(content))
                    except Exception:
                        additional_messages.append(Message.build_user_question_text(f"[助手]: {content}"))
                else:
                    if sender:
                        content = f"[{t}] {sender}: {raw}" if t else f"{sender}: {raw}"
                    else:
                        content = f"[{t}] {raw}" if t else raw
                    additional_messages.append(Message.build_user_question_text(content))
        additional_messages.append(Message.build_user_question_text(message))
        chunk_message = ""
        try:
            for event in self.coze.chat.stream(
                bot_id=self.bot_id,
                user_id=self.user_id + str(time.time()),
                additional_messages=additional_messages,
            ):
                if event.event == ChatEventType.CONVERSATION_MESSAGE_DELTA:
                    chunk_message += event.message.content

                if event.event == ChatEventType.CONVERSATION_CHAT_COMPLETED:
                    log(f"token消耗:{event.chat.usage.token_count}")

            log(f"扣子回复：{chunk_message}")
            return chunk_message
        except Exception as e:
            log(level="ERROR", message=f"❌ 调用Coze接口错误: {e}")
            return "API返回错误，请稍后再试"


class DusAPI:
    """
    DusAPI 兼容接口封装类
    根据模型名称自动选择协议：
    - 包含 'claude' → Anthropic 格式（x-api-key + /v1/messages）
    - 包含 'gpt'    → GPT/OpenAI 格式（Bearer + /v1/chat/completions）
    """

    def __init__(self, config):
        self.config = config
        self.DS_NOW_MOD = config.model1
        self.api_key = config.api_key
        self.base_url = config.base_url.rstrip('/')

    @staticmethod
    def build_image_block(image_path: str = "", image_url: str = "") -> dict:
        """根据本地路径或 URL 构建 Anthropic image content block"""
        if image_path:
            mime_type, _ = mimetypes.guess_type(image_path)
            if mime_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                mime_type = "image/jpeg"
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": image_data,
                },
            }
        elif image_url:
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": image_url,
                },
            }
        else:
            raise ValueError("image_path 和 image_url 不能同时为空")

    @staticmethod
    def _build_gpt_image_block(image_path: str = "", image_url: str = "") -> dict:
        """根据本地路径或 URL 构建 GPT/Responses API image input block"""
        if image_path:
            mime_type, _ = mimetypes.guess_type(image_path)
            if mime_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                mime_type = "image/jpeg"
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
            return {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{image_data}"
            }
        elif image_url:
            return {
                "type": "input_image",
                "image_url": image_url
            }
        else:
            raise ValueError("image_path 和 image_url 不能同时为空")

    @staticmethod
    def _extract_gpt_text(response_data: dict):
        """提取 GPT/Responses API 非流式返回文本"""
        try:
            output_text = response_data.get("output_text")
            if isinstance(output_text, str) and output_text:
                return output_text

            output = response_data.get("output", [])
            result_parts = []

            if isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "message":
                        continue

                    content = item.get("content", [])
                    if not isinstance(content, list):
                        continue

                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") in ("output_text", "text"):
                            text = block.get("text")
                            if text:
                                result_parts.append(text)

            if result_parts:
                return "".join(result_parts)

            return None
        except Exception:
            return None

    def _stream_claude_text(self, api_endpoint, headers, payload) -> str:
        """Anthropic 流式接收并拼接为完整文本"""
        response = requests.post(
            api_endpoint,
            headers=headers,
            json=payload,
            timeout=600,
            stream=True
        )
        response.raise_for_status()
        response.encoding = 'utf-8'

        result_parts = []

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if not raw_line.startswith("data:"):
                continue

            data_str = raw_line[5:].strip()
            if not data_str:
                continue

            try:
                data = json.loads(data_str)
            except Exception:
                continue

            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                text = delta.get("text")
                if text:
                    result_parts.append(text)
            elif data.get("type") == "message_stop":
                break

        return "".join(result_parts)

    def _stream_gpt_text(self, api_endpoint, headers, payload) -> str:
        """GPT/Responses API 流式接收并拼接为完整文本"""
        response = requests.post(
            api_endpoint,
            headers=headers,
            json=payload,
            timeout=600,
            stream=True
        )
        response.encoding = 'utf-8'

        if response.status_code >= 400:
            raise Exception(
                f"GPT接口请求失败，status={response.status_code}, "
                f"response={response.text}, payload={json.dumps(payload, ensure_ascii=False)[:3000]}"
            )

        result_parts = []

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if not raw_line.startswith("data:"):
                continue

            data_str = raw_line[5:].strip()
            if not data_str:
                continue
            if data_str == "[DONE]":
                break

            try:
                data = json.loads(data_str)
            except Exception:
                continue

            event_type = data.get("type")

            if event_type in (
                "response.output_text.delta",
                "response.refusal.delta",
            ):
                delta = data.get("delta")
                if isinstance(delta, str) and delta:
                    result_parts.append(delta)

            elif event_type == "response.completed":
                try:
                    output_text = data.get("response", {}).get("output_text")
                    if isinstance(output_text, str) and output_text:
                        if not result_parts:
                            result_parts.append(output_text)
                except Exception:
                    pass

        return "".join(result_parts)

    def chat(self, message, model=None, stream=True, prompt=None, history=None,
             image_path: str = "", image_url: str = "", user_key=None):
        """
        发送消息并返回回复文本。
        :param image_path: 本地图片路径，优先于 image_url
        :param image_url:  图片 URL，image_path 为空时使用

        stream=False -> 普通非流式请求并返回完整字符串
        stream=True  -> 走流式请求，但在 chat 内部收集完整后返回完整字符串
        """
        if model is None:
            model = self.DS_NOW_MOD
        if prompt is None:
            prompt = self.config.prompt

        retry_delays = [2, 4, 8, 16, 32]
        max_retries = 5
        last_error = None

        if 'claude' in model.lower():
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                'user-agent': f'siver-wxbot-panel/{version}'
            }

            if image_path or image_url:
                user_content = [
                    self.build_image_block(image_path, image_url),
                    {"type": "text", "text": message},
                ]
            else:
                user_content = message

            messages = []
            if history:
                for h in history:
                    role = "assistant" if h.get('attr') == 'self' else "user"
                    t = h.get('time', '')
                    raw = h.get('content', '')
                    sender = h.get('sender', '')
                    if role == 'user' and sender:
                        content = f"[{t}] {sender}: {raw}" if t else f"{sender}: {raw}"
                    else:
                        content = f"[{t}] {raw}" if t else raw
                    messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": user_content})

            payload = {
                "model": model,
                "max_tokens": 200000,
                "system": prompt,
                "messages": messages,
            }

            api_endpoint = f"{self.base_url}/v1/messages"

            if stream:
                payload["stream"] = True

                for attempt in range(max_retries + 1):
                    try:
                        result = self._stream_claude_text(api_endpoint, headers, payload)
                        if result:
                            if attempt > 0:
                                log(message=f"DusAPI Claude 流式第 {attempt} 次重试成功：{result[:100]}...")
                            else:
                                log(message=f"DusAPI Claude 流式返回成功：{result[:100]}...")
                            return result
                        else:
                            raise ValueError("DusAPI Claude 流式响应中未找到文本内容")

                    except Exception as e:
                        last_error = e
                        if attempt < max_retries:
                            delay = retry_delays[attempt]
                            log(level="WARNING", message=f"DusAPI Claude 流式第 {attempt + 1} 次失败（{type(e).__name__}: {e}），{delay}s 后重试...")
                            time.sleep(delay)
                        else:
                            log(level="ERROR", message=f"DusAPI Claude 流式已重试 {max_retries} 次，最终失败: {last_error}")

                return "API返回错误，请稍后再试"

            for attempt in range(max_retries + 1):
                try:
                    response = requests.post(api_endpoint, headers=headers, json=payload, timeout=600)
                    response.raise_for_status()
                    response.encoding = 'utf-8'
                    response_data = response.json()

                    result = response_data['content'][0]['text']

                    if attempt > 0:
                        log(message=f"DusAPI Claude 第 {attempt} 次重试成功：{result[:100]}...")
                    else:
                        log(message=f"DusAPI Claude 返回成功：{result[:100]}...")
                    return result

                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = retry_delays[attempt]
                        log(level="WARNING", message=f"DusAPI Claude 第 {attempt + 1} 次失败（{type(e).__name__}: {e}），{delay}s 后重试...")
                        time.sleep(delay)
                    else:
                        log(level="ERROR", message=f"DusAPI Claude 已重试 {max_retries} 次，最终失败: {last_error}")

            return "API返回错误，请稍后再试"

        elif 'gpt' in model.lower():
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
                'user-agent': f'siver-wxbot-panel/{version}'
            }

            input_items = []

            if prompt:
                input_items.append({
                    "role": "system",
                    "content": prompt
                })

            if history:
                for h in history:
                    role = "assistant" if h.get('attr') == 'self' else "user"
                    t = h.get('time', '')
                    raw = h.get('content', '')
                    sender = h.get('sender', '')
                    if role == 'user' and sender:
                        content = f"[{t}] {sender}: {raw}" if t else f"{sender}: {raw}"
                    else:
                        content = f"[{t}] {raw}" if t else raw
                    input_items.append({
                        "role": role,
                        "content": content
                    })

            if image_path or image_url:
                user_content = [
                    {"type": "input_text", "text": message},
                    self._build_gpt_image_block(image_path, image_url),
                ]
            else:
                user_content = message

            input_items.append({
                "role": "user",
                "content": user_content
            })

            payload = {
                "model": model,
                "input": input_items,
                "max_output_tokens": 200000,
            }

            api_endpoint = f"{self.base_url}/v1/responses"

            if stream:
                payload["stream"] = True

                for attempt in range(max_retries + 1):
                    try:
                        result = self._stream_gpt_text(api_endpoint, headers, payload)
                        if result:
                            if attempt > 0:
                                log(message=f"DusAPI GPT 流式第 {attempt} 次重试成功：{result[:100]}...")
                            else:
                                log(message=f"DusAPI GPT 流式返回成功：{result[:100]}...")
                            return result
                        else:
                            raise ValueError("DusAPI GPT 流式响应中未找到文本内容")

                    except Exception as e:
                        last_error = e
                        if attempt < max_retries:
                            delay = retry_delays[attempt]
                            log(level="WARNING", message=f"DusAPI GPT 流式第 {attempt + 1} 次失败（{type(e).__name__}: {e}），{delay}s 后重试...")
                            time.sleep(delay)
                        else:
                            log(level="ERROR", message=f"DusAPI GPT 流式已重试 {max_retries} 次，最终失败: {last_error}")

                return "API返回错误，请稍后再试"

            for attempt in range(max_retries + 1):
                try:
                    response = requests.post(api_endpoint, headers=headers, json=payload, timeout=600)
                    response.raise_for_status()
                    response.encoding = 'utf-8'
                    response_data = response.json()

                    result = self._extract_gpt_text(response_data)
                    if result is None:
                        raise ValueError(f"DusAPI GPT 响应中未找到文本内容：{response_data}")

                    if attempt > 0:
                        log(message=f"DusAPI GPT 第 {attempt} 次重试成功：{result[:100]}...")
                    else:
                        log(message=f"DusAPI GPT 返回成功：{result[:100]}...")
                    return result

                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = retry_delays[attempt]
                        log(level="WARNING", message=f"DusAPI GPT 第 {attempt + 1} 次失败（{type(e).__name__}: {e}），{delay}s 后重试...")
                        time.sleep(delay)
                    else:
                        log(level="ERROR", message=f"DusAPI GPT 已重试 {max_retries} 次，最终失败: {last_error}")

            return "API返回错误，请稍后再试"

        else:
            log(level="WARNING", message=f"DusAPI 未识别的模型名称：{model}，无法路由到对应协议")
            return "API返回错误，请稍后再试"
