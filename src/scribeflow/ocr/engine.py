"""OCR 引擎接口。换引擎只需实现这个协议并产出 Block。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

from scribeflow.domain import Block


@dataclass(frozen=True, slots=True)
class OcrSettings:
    backend: str = "pipeline"
    method: str = "ocr"
    language: str = "ch"
    model_source: str = "modelscope"
    mineru: Path | None = None
    shared_server: bool = True
    task_timeout_seconds: int | None = None

    def fingerprint(self) -> dict[str, str]:
        """影响识别结果的参数；续跑时必须与已完成分段一致。"""

        return {"backend": self.backend, "method": self.method, "language": self.language}


@dataclass(frozen=True, slots=True)
class SegmentJob:
    """一次识别请求：``pdf`` 只包含源文档 [first_page, first_page + page_count) 这些页。"""

    index: int
    pdf: Path
    first_page: int
    page_count: int
    output_dir: Path
    assets_dir: Path


class OcrEngine(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def recognize(self, job: SegmentJob) -> list[Block]:
        """识别一个分段，把图片复制到 ``job.assets_dir``，返回带全局页码的块。"""
        ...

    def diagnostics(self) -> dict[str, str]: ...
