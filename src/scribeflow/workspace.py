"""任务工作区：OCR 分段的 checkpoint、日志和中间产物。

工作区位于输出目录旁边，名字固定为 ``.<输出目录名>.scribeflow-work``，
所以同一个输出目标再次运行时会自动找到并续跑。成功发布后工作区被删除。
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scribeflow.domain import Block
from scribeflow.errors import ErrorCode, ScribeflowError

SCHEMA_VERSION = 1


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(slots=True)
class SegmentRecord:
    index: int
    start: int  # 源 PDF 中的起始页（从 0 开始，含）
    end: int  # 结束页（不含）
    done: bool = False
    blocks: int = 0
    seconds: float | None = None

    @property
    def page_count(self) -> int:
        return self.end - self.start


@dataclass(slots=True)
class JobState:
    input_path: str
    input_sha256: str
    page_count: int
    segment_pages: int
    ocr: dict[str, str]
    segments: list[SegmentRecord]
    schema: int = SCHEMA_VERSION
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    last_error: str | None = None

    @property
    def completed_segments(self) -> int:
        return sum(1 for segment in self.segments if segment.done)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> JobState:
        segments = [SegmentRecord(**segment) for segment in data.pop("segments")]
        return cls(segments=segments, **data)


def plan_segments(page_count: int, segment_pages: int) -> list[SegmentRecord]:
    if segment_pages < 1:
        raise ScribeflowError("每段页数必须是正整数。", code=ErrorCode.INVALID_INPUT)
    return [
        SegmentRecord(index=index, start=start, end=min(start + segment_pages, page_count))
        for index, start in enumerate(range(0, page_count, segment_pages), start=1)
    ]


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def for_output(cls, output: Path) -> Workspace:
        return cls(output.parent / f".{output.name}.scribeflow-work")

    @property
    def job_file(self) -> Path:
        return self.root / "job.json"

    @property
    def log_file(self) -> Path:
        return self.root / "run.log"

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def ai_cache_file(self) -> Path:
        return self.root / "ai-cache.json"

    def segment_pdf(self, segment: SegmentRecord) -> Path:
        return self.root / "segments" / f"s{segment.index:03d}.pdf"

    def segment_ocr_dir(self, segment: SegmentRecord) -> Path:
        return self.root / "ocr" / f"s{segment.index:03d}"

    def segment_blocks_file(self, segment: SegmentRecord) -> Path:
        return self.root / "blocks" / f"s{segment.index:03d}.jsonl"

    @property
    def ocr_dir(self) -> Path:
        return self.root / "ocr"

    def exists(self) -> bool:
        return self.job_file.is_file()

    def load(self) -> JobState:
        try:
            data = json.loads(self.job_file.read_text(encoding="utf-8"))
            if data.get("schema") != SCHEMA_VERSION:
                raise ValueError(f"不支持的工作区版本 {data.get('schema')}")
            return JobState.from_json(data)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ScribeflowError(
                f"未完成任务的记录已损坏：{self.job_file}（{exc}）。可选择重新开始。",
                code=ErrorCode.WORKSPACE_CONFLICT,
            ) from exc

    def save(self, job: JobState) -> None:
        job.updated_at = now()
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.job_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(job.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.job_file)

    def open(self, fresh_job: JobState, *, fresh: bool) -> tuple[JobState, bool]:
        """返回 (任务状态, 是否续跑)。已有工作区与本次输入不一致时报错，除非 fresh。"""

        if self.root.exists() and fresh:
            self.discard()
        if self.exists():
            job = self.load()
            mismatch = _describe_mismatch(job, fresh_job)
            if mismatch:
                raise ScribeflowError(
                    f"输出位置已有一个未完成的任务，但{mismatch}。可选择放弃旧任务重新开始。",
                    code=ErrorCode.WORKSPACE_CONFLICT,
                )
            job.last_error = None
            return job, job.completed_segments > 0
        self.root.mkdir(parents=True, exist_ok=True)
        self.save(fresh_job)
        return fresh_job, False

    def write_segment_blocks(self, segment: SegmentRecord, blocks: list[Block]) -> None:
        path = self.segment_blocks_file(segment)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        write_blocks(temporary, blocks)
        temporary.replace(path)

    def read_all_blocks(self, job: JobState) -> list[Block]:
        return [block for segment in job.segments for block in read_blocks(self.segment_blocks_file(segment))]

    def discard(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _describe_mismatch(existing: JobState, wanted: JobState) -> str:
    if existing.input_sha256 != wanted.input_sha256:
        return "它来自另一个 PDF 文件"
    if existing.segment_pages != wanted.segment_pages:
        return f"它使用每段 {existing.segment_pages} 页，而本次是 {wanted.segment_pages} 页"
    if existing.ocr != wanted.ocr:
        return "它使用了不同的 OCR 参数"
    return ""


def write_blocks(path: Path, blocks: list[Block]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for block in blocks:
            stream.write(json.dumps(block.to_json(), ensure_ascii=False) + "\n")


def read_blocks(path: Path) -> list[Block]:
    return list(_iter_blocks(path))


def _iter_blocks(path: Path) -> Iterator[Block]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield Block.from_json(json.loads(line))
