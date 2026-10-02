"""Python 事件序列化必须与 Swift 测试共用的协议样例逐字段一致。"""

from __future__ import annotations

import io
import json
from pathlib import Path

from scribeflow.events import (
    Completed,
    Diagnostics,
    Event,
    Failed,
    JsonLinesSink,
    SegmentProgress,
    SegmentState,
    Stage,
    StageChanged,
    Started,
    to_json,
)

PROTOCOL_SAMPLES = Path(__file__).parents[1] / "app/Tests/ScribeFlowCoreTests/Resources/events.jsonl"

EVENTS: list[Event] = [
    StageChanged(Stage.PREPARE, "正在检查 PDF"),
    Started("/书/民法.pdf", "/书/民法-Markdown", 480, 30, True),
    SegmentProgress(1, 30, 1, 16, SegmentState.SKIPPED),
    Diagnostics("ocr", {"引擎": "MinerU", "服务": "http://127.0.0.1:50123"}),
    SegmentProgress(2, 30, 17, 32, SegmentState.RUNNING),
    SegmentProgress(2, 30, 17, 32, SegmentState.DONE),
    Completed(
        "/书/民法-Markdown",
        "/书/民法-Markdown/document.md",
        13,
        12,
        "/书/民法-Markdown/.scribeflow/logs/20260929-101500-convert.log",
        ["有 1 页没有识别到任何内容（第 5 页），请确认是否为空白页。"],
    ),
    Failed("ocr_server", "MinerU 服务不可用，通常与内存不足有关。", True, "/书/.民法-Markdown.scribeflow-work/run.log"),
    Failed("invalid_input", "找不到输入文件：/x.pdf", False, None),
]


def test_events_match_shared_protocol_samples() -> None:
    samples = [json.loads(line) for line in PROTOCOL_SAMPLES.read_text(encoding="utf-8").splitlines()]
    assert [to_json(event) for event in EVENTS] == samples


def test_json_lines_sink_writes_one_line_per_event() -> None:
    stream = io.StringIO()
    sink = JsonLinesSink(stream)
    for event in EVENTS:
        sink.emit(event)
    lines = stream.getvalue().splitlines()
    assert len(lines) == len(EVENTS)
    assert "民法" in lines[1]  # 不转义中文


class BrokenPipe(io.StringIO):
    def write(self, text: str) -> int:
        raise BrokenPipeError


def test_json_lines_sink_ignores_closed_reader() -> None:
    sink = JsonLinesSink(BrokenPipe())
    for event in EVENTS:  # GUI 已退出时丢弃事件，不打断取消和清理
        sink.emit(event)
