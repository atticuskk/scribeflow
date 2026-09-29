"""进度事件与 JSON Lines 协议（GUI 与后端之间的唯一接口）。

每行一个 JSON 对象，``event`` 字段区分类型。协议示例见
``app/Tests/ScribeFlowCoreTests/Resources/events.jsonl``，Python 与 Swift 两侧的测试都以它为准。
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Protocol, TextIO

PROTOCOL_VERSION = 1


class Stage(StrEnum):
    PREPARE = "prepare"
    OCR = "ocr"
    CLEAN = "clean"
    AI = "ai"
    RENDER = "render"
    PUBLISH = "publish"


class SegmentState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Started:
    name: ClassVar[str] = "started"
    input: str
    output: str
    page_count: int
    segment_count: int
    resumed: bool
    version: int = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class StageChanged:
    name: ClassVar[str] = "stage"
    stage: Stage
    message: str


@dataclass(frozen=True, slots=True)
class SegmentProgress:
    name: ClassVar[str] = "segment"
    index: int
    count: int
    start_page: int
    end_page: int
    state: SegmentState


@dataclass(frozen=True, slots=True)
class Diagnostics:
    name: ClassVar[str] = "diagnostics"
    section: str
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class Completed:
    name: ClassVar[str] = "completed"
    output: str
    document: str
    markdown_files: int
    chapters: int
    log: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Failed:
    name: ClassVar[str] = "failed"
    code: str
    message: str
    resumable: bool
    log: str | None = None


Event = Started | StageChanged | SegmentProgress | Diagnostics | Completed | Failed


def to_json(event: Event) -> dict[str, Any]:
    return {"event": event.name, **asdict(event)}


class EventSink(Protocol):
    def emit(self, event: Event) -> None: ...


class NullSink:
    def emit(self, event: Event) -> None:
        pass


class JsonLinesSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def emit(self, event: Event) -> None:
        self._stream.write(json.dumps(to_json(event), ensure_ascii=False) + "\n")
        self._stream.flush()


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)
