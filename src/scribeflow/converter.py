"""转换流程编排。

``convert``：PDF → 分段 OCR（可续跑）→ 统一块 → 清洗 → 渲染 → 原子发布。
``reprocess``：直接复用已发布结果中的 OCR 块，重新清洗和渲染，不再调用 OCR。

发布后的输出目录::

    document.md            完整文档
    chapters/              按章节拆分
    assets/                图片
    .scribeflow/           manifest.json、audit.json、blocks.jsonl、logs/、ocr/（可选）
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scribeflow import __version__, pdf
from scribeflow.cleaning.ai import AiPlanner, AiSettings, JsonCache, redact_url
from scribeflow.cleaning.operations import Audit
from scribeflow.cleaning.pipeline import run_rules
from scribeflow.cleaning.rules import default_rules
from scribeflow.domain import Block
from scribeflow.errors import Cancelled, ErrorCode, InvalidInput, OcrError, ScribeflowError
from scribeflow.events import (
    Completed,
    Diagnostics,
    EventSink,
    Failed,
    NullSink,
    SegmentProgress,
    SegmentState,
    Stage,
    StageChanged,
    Started,
)
from scribeflow.logs import log_to_file
from scribeflow.ocr.engine import OcrEngine, OcrSettings, SegmentJob
from scribeflow.render import render_markdown
from scribeflow.structure import Chapter, choose_chapter_level, split_chapters
from scribeflow.workspace import JobState, Workspace, now, plan_segments, read_blocks, write_blocks

logger = logging.getLogger(__name__)

META = ".scribeflow"
MANIFEST_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class CleaningSettings:
    chapter_level: int | None = None
    cross_page_merge: bool = True
    ai: AiSettings | None = None


@dataclass(frozen=True, slots=True)
class ConvertRequest:
    input_pdf: Path
    output_dir: Path
    ocr: OcrSettings = field(default_factory=OcrSettings)
    cleaning: CleaningSettings = field(default_factory=CleaningSettings)
    segment_pages: int = 16
    overwrite: bool = False
    fresh: bool = False
    keep_ocr_output: bool = True


@dataclass(frozen=True, slots=True)
class ConversionResult:
    output_dir: Path
    document: Path
    chapters: int
    markdown_files: int
    log: Path
    warnings: list[str]


EngineFactory = Callable[[OcrSettings], OcrEngine]


def _default_engine(settings: OcrSettings) -> OcrEngine:
    from scribeflow.ocr.mineru import MinerUEngine

    return MinerUEngine(settings)


def convert(
    request: ConvertRequest,
    sink: EventSink | None = None,
    *,
    engine_factory: EngineFactory = _default_engine,
) -> ConversionResult:
    sink = sink or NullSink()
    output = request.output_dir.expanduser().resolve()
    workspace = Workspace.for_output(output)
    job: JobState | None = None
    try:
        sink.emit(StageChanged(Stage.PREPARE, "正在检查 PDF"))
        source = _validate_input(request.input_pdf)
        _check_output_target(output, request.overwrite)
        page_count = pdf.page_count(source)
        wanted = JobState(
            input_path=str(source),
            input_sha256=pdf.sha256(source),
            page_count=page_count,
            segment_pages=request.segment_pages,
            ocr=request.ocr.fingerprint(),
            segments=plan_segments(page_count, request.segment_pages),
        )
        job, resumed = workspace.open(wanted, fresh=request.fresh)
        with log_to_file(workspace.log_file):
            try:
                logger.info(
                    "ScribeFlow %s：%s → %s（%d 页，每段 %d 页，%s）",
                    __version__,
                    source,
                    output,
                    page_count,
                    request.segment_pages,
                    "续跑" if resumed else "新任务",
                )
                sink.emit(Started(str(source), str(output), page_count, len(job.segments), resumed))
                _run_ocr(source, workspace, job, request.ocr, sink, engine_factory)
                blocks = workspace.read_all_blocks(job)
                context = {
                    "source": {"path": str(source), "sha256": job.input_sha256, "page_count": page_count},
                    "ocr": {
                        "engine": "mineru",
                        **request.ocr.fingerprint(),
                        "model_source": request.ocr.model_source,
                        "segment_pages": request.segment_pages,
                    },
                }
                staging = _new_staging(output)
                try:
                    _link_tree(workspace.assets_dir, staging / "assets")
                    if request.keep_ocr_output:
                        _link_tree(workspace.ocr_dir, staging / META / "ocr")
                    if workspace.ai_cache_file.exists():
                        _link_file(workspace.ai_cache_file, staging / META / "ai-cache.json")
                    result = _build_and_publish(
                        staging,
                        output,
                        blocks,
                        request.cleaning,
                        context,
                        sink,
                        overwrite=request.overwrite,
                        log_source=workspace.log_file,
                        log_kind="convert",
                        ai_cache=workspace.ai_cache_file,
                    )
                finally:
                    shutil.rmtree(staging, ignore_errors=True)
            except BaseException as exc:
                _log_failure(exc)
                raise
        workspace.discard()
        sink.emit(_completed(result))
        return result
    except BaseException as exc:
        error = _as_error(exc)
        if job is not None and workspace.exists():
            job.last_error = error.message
            workspace.save(job)
        resumable = job is not None and workspace.exists() and job.completed_segments > 0
        log = str(workspace.log_file) if workspace.log_file.exists() else None
        sink.emit(Failed(error.code.value, error.message, resumable, log))
        if error is exc:
            raise
        raise error from exc


def reprocess(
    output_dir: Path,
    cleaning: CleaningSettings,
    sink: EventSink | None = None,
) -> ConversionResult:
    """用已发布结果里的 OCR 块重新清洗和渲染。"""

    sink = sink or NullSink()
    output = output_dir.expanduser().resolve()
    try:
        manifest_path = output / META / "manifest.json"
        blocks_path = output / META / "blocks.jsonl"
        if not (manifest_path.is_file() and blocks_path.is_file()):
            raise InvalidInput(f"不是 ScribeFlow 生成的输出目录，或缺少 OCR 块记录：{output}")
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        blocks = read_blocks(blocks_path)
        sink.emit(Started(str(previous["source"]["path"]), str(output), int(previous["source"]["page_count"]), 0, True))
        staging = _new_staging(output)
        try:
            _link_tree(output / "assets", staging / "assets")
            for name in ("ocr", "logs", "ai-cache.json"):
                source = output / META / name
                if source.is_dir():
                    _link_tree(source, staging / META / name)
                elif source.is_file():
                    _link_file(source, staging / META / name)
            context = {"source": previous["source"], "ocr": previous["ocr"]}
            log_path = staging / META / "logs" / f"{_stamp()}-reprocess.log"
            with log_to_file(log_path):
                logger.info("ScribeFlow %s：重新生成 %s", __version__, output)
                try:
                    result = _build_and_publish(
                        staging,
                        output,
                        blocks,
                        cleaning,
                        context,
                        sink,
                        overwrite=True,
                        log_source=None,
                        log_kind="reprocess",
                        ai_cache=staging / META / "ai-cache.json",
                        log_path=log_path,
                    )
                except BaseException as exc:
                    _log_failure(exc)
                    raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        sink.emit(_completed(result))
        return result
    except BaseException as exc:
        error = _as_error(exc)
        sink.emit(Failed(error.code.value, error.message, False, None))
        if error is exc:
            raise
        raise error from exc


def _run_ocr(
    source: Path,
    workspace: Workspace,
    job: JobState,
    settings: OcrSettings,
    sink: EventSink,
    engine_factory: EngineFactory,
) -> None:
    count = len(job.segments)
    for segment in job.segments:
        if segment.done:
            sink.emit(SegmentProgress(segment.index, count, segment.start + 1, segment.end, SegmentState.SKIPPED))
    pending = [segment for segment in job.segments if not segment.done]
    if not pending:
        return
    sink.emit(StageChanged(Stage.OCR, "正在启动 OCR 引擎"))
    with engine_factory(settings) as engine:
        sink.emit(Diagnostics("ocr", engine.diagnostics()))
        for segment in pending:
            sink.emit(SegmentProgress(segment.index, count, segment.start + 1, segment.end, SegmentState.RUNNING))
            logger.info("第 %d/%d 段：第 %d–%d 页", segment.index, count, segment.start + 1, segment.end)
            started = time.monotonic()
            segment_pdf = workspace.segment_pdf(segment)
            pdf.write_pages(source, segment_pdf, segment.start, segment.end)
            blocks = engine.recognize(
                SegmentJob(
                    index=segment.index,
                    pdf=segment_pdf,
                    first_page=segment.start,
                    page_count=segment.page_count,
                    output_dir=workspace.segment_ocr_dir(segment),
                    assets_dir=workspace.assets_dir,
                )
            )
            outside = sorted({b.page + 1 for b in blocks if not segment.start <= b.page < segment.end})
            if outside:
                raise OcrError(f"第 {segment.index} 段返回了超出范围的页码：{outside[:8]}")
            workspace.write_segment_blocks(segment, blocks)
            segment.done, segment.blocks = True, len(blocks)
            segment.seconds = round(time.monotonic() - started, 1)
            workspace.save(job)
            segment_pdf.unlink(missing_ok=True)
            sink.emit(SegmentProgress(segment.index, count, segment.start + 1, segment.end, SegmentState.DONE))


def _build_and_publish(
    staging: Path,
    output: Path,
    raw_blocks: list[Block],
    cleaning: CleaningSettings,
    context: dict[str, Any],
    sink: EventSink,
    *,
    overwrite: bool,
    log_source: Path | None,
    log_kind: str,
    ai_cache: Path,
    log_path: Path | None = None,
) -> ConversionResult:
    meta = staging / META
    meta.mkdir(parents=True, exist_ok=True)
    audit = Audit()

    sink.emit(StageChanged(Stage.CLEAN, "正在清洗页眉、页码和断行"))
    blocks = run_rules(raw_blocks, default_rules(cross_page_merge=cleaning.cross_page_merge), audit)
    logger.info("清洗：%d 个块 → %d 个块", len(raw_blocks), len(blocks))
    if cleaning.ai is not None:
        sink.emit(StageChanged(Stage.AI, "正在使用 AI 清洗格式"))
        sink.emit(
            Diagnostics(
                "ai",
                {
                    "模型": cleaning.ai.model,
                    "接口": redact_url(cleaning.ai.base_url) or "OpenAI 默认接口",
                    "temperature": "0",
                },
            )
        )
        planner = AiPlanner(cleaning.ai, cache=JsonCache(ai_cache))
        blocks = run_rules(blocks, [planner], audit)
        if ai_cache.exists() and ai_cache.parent != meta:
            _link_file(ai_cache, meta / "ai-cache.json", replace=True)

    sink.emit(StageChanged(Stage.RENDER, "正在生成 Markdown"))
    (staging / "document.md").write_text(render_markdown(blocks, assets_prefix="assets"), encoding="utf-8")
    level = choose_chapter_level(blocks, cleaning.chapter_level)
    chapters = split_chapters(blocks, level)
    chapters_dir = staging / "chapters"
    chapters_dir.mkdir()
    for chapter in chapters:
        (chapters_dir / chapter.filename).write_text(
            render_markdown(chapter.blocks, assets_prefix="../assets"), encoding="utf-8"
        )

    warnings = _empty_page_warning(raw_blocks, int(context["source"]["page_count"]))
    write_blocks(meta / "blocks.jsonl", raw_blocks)
    (meta / "audit.json").write_text(json.dumps(audit.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = _manifest(context, cleaning, level, chapters, raw_blocks, blocks, audit, warnings)
    (meta / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    sink.emit(StageChanged(Stage.PUBLISH, "正在发布结果"))
    logger.info("生成 %d 个章节，发布到 %s", len(chapters), output)
    if log_source is not None:
        log_path = meta / "logs" / f"{_stamp()}-{log_kind}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log_source, log_path)
    _publish(staging, output, overwrite=overwrite)
    final_log = output / log_path.relative_to(staging) if log_path else output / META / "logs"
    return ConversionResult(
        output_dir=output,
        document=output / "document.md",
        chapters=len(chapters),
        markdown_files=1 + len(chapters),
        log=final_log,
        warnings=warnings,
    )


def _manifest(
    context: dict[str, Any],
    cleaning: CleaningSettings,
    level: int | None,
    chapters: list[Chapter],
    raw_blocks: list[Block],
    blocks: list[Block],
    audit: Audit,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "generator": f"scribeflow {__version__}",
        "created_at": now(),
        **context,
        "cleaning": {
            "cross_page_merge": cleaning.cross_page_merge,
            "chapter_level": level,
            "chapter_level_requested": cleaning.chapter_level,
            "ai": {"model": cleaning.ai.model, "base_url": redact_url(cleaning.ai.base_url)} if cleaning.ai else None,
        },
        "document": "document.md",
        "chapters": [{"index": c.index, "title": c.title, "file": f"chapters/{c.filename}"} for c in chapters],
        "stats": {
            "ocr_blocks": len(raw_blocks),
            "output_blocks": len(blocks),
            "dropped": audit.count("drop"),
            "merged": audit.count("merge"),
            "levels_changed": audit.count("set_level"),
            "rejected": len(audit.rejected),
        },
        "warnings": warnings,
    }


def _empty_page_warning(blocks: list[Block], page_count: int) -> list[str]:
    seen = {block.page for block in blocks}
    empty = [page + 1 for page in range(page_count) if page not in seen]
    if not empty:
        return []
    shown = "、".join(str(page) for page in empty[:20]) + ("……" if len(empty) > 20 else "")
    return [f"有 {len(empty)} 页没有识别到任何内容（第 {shown} 页），请确认是否为空白页。"]


def _validate_input(path: Path) -> Path:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise InvalidInput(f"找不到输入文件：{source}")
    if source.suffix.lower() != ".pdf":
        raise InvalidInput(f"输入文件不是 PDF：{source.name}")
    return source


def _is_generated_output(path: Path) -> bool:
    return (path / META / "manifest.json").is_file() or (
        (path / "manifest.json").is_file() and (path / "document.md").is_file()  # 0.1.x 旧版输出
    )


def _check_output_target(output: Path, overwrite: bool) -> None:
    if not output.exists():
        return
    if not overwrite:
        raise ScribeflowError(f"输出目录已存在：{output}", code=ErrorCode.OUTPUT_EXISTS)
    if not output.is_dir() or not _is_generated_output(output):
        raise ScribeflowError(f"拒绝覆盖不是由 ScribeFlow 生成的目录：{output}", code=ErrorCode.OUTPUT_EXISTS)


def _publish(staging: Path, output: Path, *, overwrite: bool) -> None:
    if not output.exists():
        staging.rename(output)
        return
    _check_output_target(output, overwrite)
    backup = output.with_name(f".{output.name}.scribeflow-old-{uuid.uuid4().hex[:8]}")
    output.rename(backup)
    try:
        staging.rename(output)
    except BaseException:
        backup.rename(output)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _new_staging(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(f".{output.name}.scribeflow-publish-{uuid.uuid4().hex[:8]}")
    staging.mkdir()
    return staging


def _link_file(source: Path, target: Path, *, replace: bool = False) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if replace:
        target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _link_tree(source: Path, target: Path) -> None:
    """用硬链接复制目录（同一磁盘上几乎不占空间），不支持时退回普通复制。"""

    if not source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        return

    def link(src: str, dst: str) -> object:
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
        return dst

    shutil.copytree(source, target, copy_function=link, dirs_exist_ok=True)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _completed(result: ConversionResult) -> Completed:
    return Completed(
        output=str(result.output_dir),
        document=str(result.document),
        markdown_files=result.markdown_files,
        chapters=result.chapters,
        log=str(result.log),
        warnings=result.warnings,
    )


def _as_error(exc: BaseException) -> ScribeflowError:
    if isinstance(exc, ScribeflowError):
        return exc
    if isinstance(exc, KeyboardInterrupt):
        return Cancelled()
    return ScribeflowError(f"未预期的错误：{exc}")


def _log_failure(exc: BaseException) -> None:
    if isinstance(exc, ScribeflowError | KeyboardInterrupt):
        logger.error("任务失败：%s", exc or "已取消")
    else:
        logger.exception("未预期的错误")
