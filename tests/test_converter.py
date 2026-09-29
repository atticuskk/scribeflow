from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fakes import FIXTURES, FakeEngine, book_pages, make_pdf
from scribeflow.converter import META, CleaningSettings, ConvertRequest, convert, reprocess
from scribeflow.errors import ErrorCode, ScribeflowError
from scribeflow.events import Completed, Failed, RecordingSink, SegmentProgress, SegmentState, Started
from scribeflow.workspace import Workspace

GOLDEN = FIXTURES / "expected"


@pytest.fixture
def book(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "民法 讲义.pdf", len(book_pages()))


def request(book: Path, **changes: object) -> ConvertRequest:
    defaults: dict[str, object] = {"input_pdf": book, "output_dir": book.with_name("民法-Markdown"), "segment_pages": 2}
    return ConvertRequest(**{**defaults, **changes})  # type: ignore[arg-type]


def snapshot(output: Path) -> dict[str, str]:
    files = [output / "document.md", *sorted((output / "chapters").iterdir())]
    return {str(path.relative_to(output)): path.read_text(encoding="utf-8") for path in files}


def test_convert_matches_golden_output(book: Path) -> None:
    engine = FakeEngine
    sink = RecordingSink()
    result = convert(request(book), sink, engine_factory=lambda settings: engine(settings))
    output = result.output_dir

    actual = snapshot(output)
    if os.environ.get("UPDATE_GOLDEN"):
        for name, text in actual.items():
            (GOLDEN / name).parent.mkdir(parents=True, exist_ok=True)
            (GOLDEN / name).write_text(text, encoding="utf-8")
    expected = {str(p.relative_to(GOLDEN)): p.read_text(encoding="utf-8") for p in sorted(GOLDEN.rglob("*.md"))}
    assert actual == expected

    assert sorted(p.name for p in (output / "assets" / "s002").iterdir()) == ["principle.jpg", "table.jpg"]
    manifest = json.loads((output / META / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["page_count"] == 6
    assert manifest["stats"]["dropped"] == 7
    assert manifest["warnings"] == result.warnings == ["有 1 页没有识别到任何内容（第 5 页），请确认是否为空白页。"]
    audit = json.loads((output / META / "audit.json").read_text(encoding="utf-8"))
    assert {entry["action"] for entry in audit["applied"]} == {"drop", "merge"}
    assert (output / META / "blocks.jsonl").is_file()
    assert result.log.is_file() and "ScribeFlow" in result.log.read_text(encoding="utf-8")
    assert (output / META / "ocr" / "s001").is_dir()
    assert not Workspace.for_output(output).root.exists()

    assert isinstance(sink.events[-1], Completed)
    started = next(e for e in sink.events if isinstance(e, Started))
    assert (started.page_count, started.segment_count, started.resumed) == (6, 3, False)


def test_failed_segment_is_resumed_without_redoing_completed_work(book: Path) -> None:
    engine = FakeEngine(settings=None, fail_once={2})  # type: ignore[arg-type]
    sink = RecordingSink()
    with pytest.raises(ScribeflowError):
        convert(request(book), sink, engine_factory=engine)
    failed = sink.events[-1]
    assert isinstance(failed, Failed) and failed.resumable and failed.code == "internal"
    workspace = Workspace.for_output(book.with_name("民法-Markdown"))
    assert json.loads(workspace.job_file.read_text(encoding="utf-8"))["last_error"]

    sink = RecordingSink()
    convert(request(book), sink, engine_factory=engine)
    assert engine.calls == [1, 2, 2, 3]
    states = [(e.index, e.state) for e in sink.events if isinstance(e, SegmentProgress)]
    assert states[0] == (1, SegmentState.SKIPPED)
    assert next(e for e in sink.events if isinstance(e, Started)).resumed


def test_fully_recognized_workspace_skips_ocr_engine(book: Path) -> None:
    engine = FakeEngine(settings=None)  # type: ignore[arg-type]
    output = book.with_name("民法-Markdown")
    output.mkdir()  # 输出已存在且不是 ScribeFlow 目录 → 发布失败，但 OCR 已完成
    (output / "notes.txt").write_text("用户文件")
    with pytest.raises(ScribeflowError) as error:
        convert(request(book, overwrite=True), engine_factory=engine)
    assert error.value.code is ErrorCode.OUTPUT_EXISTS
    assert (output / "notes.txt").exists()
    assert engine.entered == 0


def test_workspace_from_other_pdf_is_a_conflict(book: Path, tmp_path: Path) -> None:
    engine = FakeEngine(settings=None, fail_once={1})  # type: ignore[arg-type]
    with pytest.raises(ScribeflowError):
        convert(request(book), engine_factory=engine)
    other = make_pdf(tmp_path / "other.pdf", 7)
    with pytest.raises(ScribeflowError) as error:
        convert(request(other, output_dir=book.with_name("民法-Markdown")), engine_factory=engine)
    assert error.value.code is ErrorCode.WORKSPACE_CONFLICT
    convert(request(other, output_dir=book.with_name("民法-Markdown"), fresh=True), engine_factory=engine)


def test_existing_output_requires_overwrite(book: Path) -> None:
    convert(request(book), engine_factory=FakeEngine(settings=None))  # type: ignore[arg-type]
    with pytest.raises(ScribeflowError) as error:
        convert(request(book), engine_factory=FakeEngine(settings=None))  # type: ignore[arg-type]
    assert error.value.code is ErrorCode.OUTPUT_EXISTS
    convert(request(book, overwrite=True), engine_factory=FakeEngine(settings=None))  # type: ignore[arg-type]


def test_invalid_input_reports_failure_event(tmp_path: Path) -> None:
    sink = RecordingSink()
    with pytest.raises(ScribeflowError):
        convert(request(tmp_path / "missing.pdf"), sink, engine_factory=FakeEngine(settings=None))  # type: ignore[arg-type]
    assert isinstance(sink.events[-1], Failed)
    assert sink.events[-1].code == "invalid_input" and not sink.events[-1].resumable


def test_reprocess_changes_chapters_without_ocr(book: Path) -> None:
    result = convert(request(book), engine_factory=FakeEngine(settings=None))  # type: ignore[arg-type]
    before = snapshot(result.output_dir)
    redone = reprocess(result.output_dir, CleaningSettings(chapter_level=2, cross_page_merge=False))
    after = snapshot(redone.output_dir)
    assert after["document.md"] != before["document.md"]
    assert "终止民事\n\n法律关系。" in after["document.md"]
    assert [name for name in after if name.startswith("chapters/")] == [
        "chapters/001-前言.md",
        "chapters/002-第一节-基本原则.md",
    ]
    assert (redone.output_dir / "assets" / "s002" / "principle.jpg").is_file()
    logs = sorted(p.name for p in (redone.output_dir / META / "logs").iterdir())
    assert [name.split("-")[-1] for name in logs] == ["convert.log", "reprocess.log"]
    manifest = json.loads((redone.output_dir / META / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cleaning"]["chapter_level"] == 2


def test_reprocess_rejects_foreign_directory(tmp_path: Path) -> None:
    with pytest.raises(ScribeflowError) as error:
        reprocess(tmp_path, CleaningSettings())
    assert error.value.code is ErrorCode.INVALID_INPUT
