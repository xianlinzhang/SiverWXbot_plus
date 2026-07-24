import os
import json
import time
import base64
import mimetypes
import requests
from openai import OpenAI
from cozepy import Coze
from cozepy.auth import TokenAuth
from cozepy import Message, ChatEventType
from cozepy import COZE_CN_BASE_URL
from logger import log

version = "V4.7.27"


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
             image_path: str = "", image_url: str = ""):
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
    通过 HTTP 请求调用 Dify 对话工作流接口。
    """

    def __init__(self, config):
        self.config = config
        self.DS_NOW_MOD = config.model1
        self.api_key = "Bearer " + config.api_key
        self.base_url = config.base_url

    def chat(self, message, model=None, stream=True, prompt=None, history=None):
        """
        调用 Dify 对话接口，返回 AI 回复文本。

        :param message: 用户输入内容
        :param history: 历史消息列表（Dify 不支持多轮消息，拼接为上下文前缀）
        :return:        AI 回复字符串
        """
        query = message
        if history:
            ctx = "\n".join([
                f"[{h.get('time', '')}] {'助手' if h.get('attr') == 'self' else h.get('sender', '用户')}: {h.get('content', '')}"
                for h in history
            ])
            query = f"[历史对话]\n{ctx}\n[当前消息]\n{message}"
        response = self.run_dify_conversation(
            query=query,
            response_mode="blocking",
        )

        if "event" in response and response["event"] == "message":
            result = self.handle_blocking_response(response)
            log(message=f"🤖 AI回复: {result['answer']}")
            log(message=f"会话ID: {result['conversation_id']}")
            return result['answer']
        else:
            log(level="ERROR", message=f"❌ 错误: {response.get('error', 'Unknown error')}")
            return "API返回错误，请稍后再试"

    def handle_blocking_response(self, response_data):
        """
        解析阻塞模式（blocking）的 Dify API 响应。

        :param response_data: Dify 返回的 JSON 数据字典
        :return:              包含 success、answer 等字段的结果字典
        """
        if response_data.get("event") == "message":
            return {
                "success": True,
                "conversation_id":   response_data.get("conversation_id"),
                "answer":            response_data.get("answer", ""),
                "message_id":        response_data.get("message_id"),
                "metadata":          response_data.get("metadata", {}),
                "usage":             response_data.get("usage", {}),
                "retriever_resources": response_data.get("retriever_resources", []),
            }
        else:
            return {
                "success": False,
                "error":        f"Unexpected event type: {response_data.get('event')}",
                "raw_response": response_data,
            }

    def run_dify_conversation(
        self,
        query=str,
        inputs={},
        conversation_id=None,
        files=[],
        auto_generate_name=True,
        response_mode="blocking",
    ):
        """
        执行 Dify 对话工作流 API 请求。
        官方文档：https://docs.dify.ai/api/chat-messages

        :param query:               用户输入/提问内容
        :param inputs:              App 中定义的变量值
        :param conversation_id:     会话 ID（多轮对话时传入）
        :param files:               文件列表（支持 Vision 能力时使用）
        :param auto_generate_name:  是否自动生成对话标题
        :param response_mode:       响应模式（blocking / streaming）
        :return:                    API 响应数据字典
        """
        url = self.base_url
        headers = {
            "Authorization": self.api_key,
            "Content-Type":  "application/json",
        }
        payload = {
            "inputs":             inputs,
            "query":              query,
            "response_mode":      response_mode,
            "user":               "api-user",
            "conversation_id":    conversation_id,
            "auto_generate_name": auto_generate_name,
        }

        if files:
            payload["files"] = files

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            if response_mode == "blocking":
                return response.json()
            else:
                return {"raw_stream": response.text}
        except requests.exceptions.RequestException as e:
            error_info = {
                "error_type": "request_error",
                "message":    str(e),
            }
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    error_info.update({
                        "status_code": e.response.status_code,
                        "error_code":  error_data.get("code", "unknown"),
                        "api_message": error_data.get("message", "No error details"),
                    })
                except Exception:
                    error_info["response_text"] = e.response.text
            return {"success": False, "error": error_info}


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

    def chat(self, message, model=None, stream=True, prompt=None, history=None):
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
             image_path: str = "", image_url: str = ""):
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
