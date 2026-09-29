#!/usr/bin/env python3
"""从一页扫描样本生成连续页数压力 PDF，不改变原始样本。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 PDF OCR 长文档压力样本")
    parser.add_argument("source", type=Path, help="源 PDF；使用第一页作为重复样本")
    parser.add_argument("output", type=Path, help="输出压力 PDF")
    parser.add_argument("--pages", type=int, default=300, help="生成的页数，默认 300")
    args = parser.parse_args()
    if args.pages < 1:
        parser.error("--pages 必须是正整数")
    reader = PdfReader(args.source, strict=False)
    if not reader.pages:
        raise SystemExit("源 PDF 没有页面")
    writer = PdfWriter()
    for _ in range(args.pages):
        writer.add_page(reader.pages[0])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as stream:
        writer.write(stream)
    print(f"已生成 {args.pages} 页压力 PDF：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
