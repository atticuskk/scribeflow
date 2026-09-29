"""命令行入口：``scribeflow convert`` 与 ``scribeflow reprocess``。

GUI 通过 ``--events jsonl`` 调用同样的命令：事件写 stdout，日志写 stderr。
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path
from types import FrameType

from scribeflow import __version__
from scribeflow.cleaning.ai import AiSettings
from scribeflow.converter import CleaningSettings, ConversionResult, ConvertRequest, convert, reprocess
from scribeflow.errors import Cancelled, ErrorCode, ScribeflowError
from scribeflow.events import EventSink, Failed, JsonLinesSink, NullSink
from scribeflow.logs import configure_console
from scribeflow.ocr.engine import OcrSettings


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _add_cleaning_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("清洗与章节")
    group.add_argument(
        "--chapter-level", type=int, choices=range(1, 7), metavar="1-6", help="在第几级标题处切分章节；默认自动选择"
    )
    group.add_argument("--no-cross-page-merge", action="store_true", help="不合并被分页截断的中文句子")
    group.add_argument("--ai", action="store_true", help="启用在线 AI 清洗（默认关闭，会把内容块发送给服务）")
    group.add_argument("--ai-model", help="模型名；也可用 SCRIBEFLOW_AI_MODEL 或 OPENAI_MODEL")
    group.add_argument("--ai-base-url", help="OpenAI 兼容接口地址；也可用 SCRIBEFLOW_AI_BASE_URL 或 OPENAI_BASE_URL")
    parser.add_argument("--events", choices=["jsonl"], help="以 JSON Lines 向 stdout 输出进度事件（供 GUI 使用）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scribeflow", description="扫描版 PDF → 保真清洗 → 章节 Markdown")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("convert", help="转换 PDF（同一输出位置的未完成任务会自动续跑）")
    run.add_argument("input", type=Path, help="输入 PDF")
    run.add_argument("-o", "--output", type=Path, required=True, help="输出目录")
    run.add_argument("--overwrite", action="store_true", help="替换 ScribeFlow 之前生成的同名输出")
    run.add_argument("--fresh", action="store_true", help="放弃该输出位置的未完成任务，重新开始")
    run.add_argument("--segment-pages", type=int, default=16, help="每段 OCR 页数，默认 16")
    run.add_argument("--discard-ocr-output", action="store_true", help="不在输出目录中保留 MinerU 原始结果")
    ocr = run.add_argument_group("OCR")
    ocr.add_argument("--backend", default="pipeline", help="MinerU 后端，默认 pipeline")
    ocr.add_argument("--method", default="ocr", choices=["auto", "txt", "ocr"])
    ocr.add_argument("--lang", default="ch", help="OCR 语言，默认 ch")
    ocr.add_argument("--model-source", default="modelscope", choices=["modelscope", "huggingface", "local"])
    ocr.add_argument("--mineru", type=Path, help="mineru 可执行文件路径；默认使用当前 Python 环境中的 MinerU")
    ocr.add_argument("--no-shared-server", action="store_true", help="每段单独启动 MinerU（旧方式，较慢）")
    _add_cleaning_options(run)

    redo = commands.add_parser("reprocess", help="用已有 OCR 结果重新清洗和生成 Markdown，不再 OCR")
    redo.add_argument("output", type=Path, help="之前生成的输出目录")
    _add_cleaning_options(redo)
    return parser


def _cleaning(args: argparse.Namespace) -> CleaningSettings:
    ai = None
    if args.ai:
        model = args.ai_model or _env("SCRIBEFLOW_AI_MODEL", "OPENAI_MODEL")
        api_key = _env("SCRIBEFLOW_AI_API_KEY", "OPENAI_API_KEY")
        if not model or not api_key:
            raise ScribeflowError(
                "启用 AI 清洗需要模型名和 API 密钥（SCRIBEFLOW_AI_API_KEY 或 OPENAI_API_KEY）。",
                code=ErrorCode.AI_CONFIG,
            )
        base_url = args.ai_base_url or _env("SCRIBEFLOW_AI_BASE_URL", "OPENAI_BASE_URL")
        ai = AiSettings(model=model, api_key=api_key, base_url=base_url)
    return CleaningSettings(
        chapter_level=args.chapter_level,
        cross_page_merge=not args.no_cross_page_merge,
        ai=ai,
    )


def _raise_cancelled(signum: int, frame: FrameType | None) -> None:
    raise Cancelled()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_console()
    signal.signal(signal.SIGTERM, _raise_cancelled)
    sink: EventSink = JsonLinesSink() if args.events == "jsonl" else NullSink()
    try:
        cleaning = _cleaning(args)
    except ScribeflowError as exc:
        sink.emit(Failed(exc.code.value, exc.message, False, None))
        if args.events is None:
            print(f"错误：{exc}", file=sys.stderr)
        return 1
    try:
        result = _run(args, cleaning, sink)
    except ScribeflowError as exc:
        if args.events is None:
            print(f"错误：{exc}", file=sys.stderr)
        return 130 if exc.code is ErrorCode.CANCELLED else 1
    except KeyboardInterrupt:
        return 130
    if args.events is None:
        print(f"完成：{result.output_dir}")
        print(f"  完整文档：{result.document}")
        print(f"  章节：{result.chapters} 个")
        for warning in result.warnings:
            print(f"  注意：{warning}")
    return 0


def _run(args: argparse.Namespace, cleaning: CleaningSettings, sink: EventSink) -> ConversionResult:
    if args.command == "reprocess":
        return reprocess(args.output, cleaning, sink)
    request = ConvertRequest(
        input_pdf=args.input,
        output_dir=args.output,
        ocr=OcrSettings(
            backend=args.backend,
            method=args.method,
            language=args.lang,
            model_source=args.model_source,
            mineru=args.mineru,
            shared_server=not args.no_shared_server,
        ),
        cleaning=cleaning,
        segment_pages=args.segment_pages,
        overwrite=args.overwrite,
        fresh=args.fresh,
        keep_ocr_output=not args.discard_ocr_output,
    )
    return convert(request, sink)
