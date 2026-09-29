"""面向用户的错误类型。每个错误带一个稳定的 code，供 GUI 分支处理。"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    OUTPUT_EXISTS = "output_exists"
    WORKSPACE_CONFLICT = "workspace_conflict"
    OCR_UNAVAILABLE = "ocr_unavailable"
    OCR_FAILED = "ocr_failed"
    OCR_TIMEOUT = "ocr_timeout"
    OCR_SERVER = "ocr_server"
    AI_CONFIG = "ai_config"
    AI_FAILED = "ai_failed"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class ScribeflowError(Exception):
    """可以直接展示给用户的错误。"""

    code: ErrorCode = ErrorCode.INTERNAL

    def __init__(self, message: str, *, code: ErrorCode | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code

    @property
    def message(self) -> str:
        return str(self)


class InvalidInput(ScribeflowError):
    code = ErrorCode.INVALID_INPUT


class OcrError(ScribeflowError):
    code = ErrorCode.OCR_FAILED


class AiError(ScribeflowError):
    code = ErrorCode.AI_FAILED


class Cancelled(ScribeflowError):
    code = ErrorCode.CANCELLED

    def __init__(self, message: str = "任务已取消。") -> None:
        super().__init__(message)
