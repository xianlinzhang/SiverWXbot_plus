from http import HTTPStatus
from typing import Union

import httpx
import httpx_sse

import json as std_json
from core.dify_client import models


class DifyAPIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"status_code={status}, code={code}, {message}")
        self.status = status
        self.code = code
        self.message = message


class DifyInvalidParam(DifyAPIError):
    pass


class DifyNotChatApp(DifyAPIError):
    pass


class DifyResourceNotFound(DifyAPIError):
    pass


class DifyAppUnavailable(DifyAPIError):
    pass


class DifyProviderNotInitialize(DifyAPIError):
    pass


class DifyProviderQuotaExceeded(DifyAPIError):
    pass


class DifyModelCurrentlyNotSupport(DifyAPIError):
    pass


class DifyCompletionRequestError(DifyAPIError):
    pass


class DifyInternalServerError(DifyAPIError):
    pass


class DifyNoFileUploaded(DifyAPIError):
    pass


class DifyTooManyFiles(DifyAPIError):
    pass


class DifyUnsupportedPreview(DifyAPIError):
    pass


class DifyUnsupportedEstimate(DifyAPIError):
    pass


class DifyFileTooLarge(DifyAPIError):
    pass


class DifyUnsupportedFileType(DifyAPIError):
    pass


class DifyS3ConnectionFailed(DifyAPIError):
    pass


class DifyS3PermissionDenied(DifyAPIError):
    pass


class DifyS3FileTooLarge(DifyAPIError):
    pass


SPEC_CODE_ERRORS = {
    # completion & chat & workflow
    "invalid_param": DifyInvalidParam,
    "not_chat_app": DifyNotChatApp,
    "app_unavailable": DifyAppUnavailable,
    "provider_not_initialize": DifyProviderNotInitialize,
    "provider_quota_exceeded": DifyProviderQuotaExceeded,
    "model_currently_not_support": DifyModelCurrentlyNotSupport,
    "completion_request_error": DifyCompletionRequestError,
    # files upload
    "no_file_uploaded": DifyNoFileUploaded,
    "too_many_files": DifyTooManyFiles,
    "unsupported_preview": DifyUnsupportedPreview,
    "unsupported_estimate": DifyUnsupportedEstimate,
    "file_too_large": DifyFileTooLarge,
    "unsupported_file_type": DifyUnsupportedFileType,
    "s3_connection_failed": DifyS3ConnectionFailed,
    "s3_permission_denied": DifyS3PermissionDenied,
    "s3_file_too_large": DifyS3FileTooLarge,
}


def raise_for_status(response: Union[httpx.Response, httpx_sse.ServerSentEvent]):
    if isinstance(response, httpx.Response):
        if response.is_success:
            return

        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            # 非 JSON 响应，防止 json() 报错
            text = response.text
            raise DifyAPIError(
                status=response.status_code,
                code="non_json_response",
                message=f"Non-JSON response received: {text[:200]}..."  # 取前200字符用于调试
            )

        try:
            json = response.json()
        except std_json.JSONDecodeError:
            # 容错处理：捕获无法解析为 JSON 的情况
            text = response.text
            raise DifyAPIError(
                status=response.status_code,
                code="invalid_json",
                message=f"Failed to parse JSON response: {text[:200]}..."
            )

        if "status" not in json:
            json["status"] = response.status_code
        details = models.ErrorResponse(**json)
    elif isinstance(response, httpx_sse.ServerSentEvent):
        if response.event != models.StreamEvent.ERROR.value:
            return
        details = models.ErrorStreamResponse(**response.json())
    else:
        raise ValueError(f"Invalid dify response type: {type(response)}")

    if details.status == HTTPStatus.NOT_FOUND:
        raise DifyResourceNotFound(details.status, details.code, details.message)
    elif details.status == HTTPStatus.INTERNAL_SERVER_ERROR:
        raise DifyInternalServerError(details.status, details.code, details.message)
    else:
        raise SPEC_CODE_ERRORS.get(details.code, DifyAPIError)(details.status, details.code, details.message)
