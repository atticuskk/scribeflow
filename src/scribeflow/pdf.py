"""PDF 文件操作：页数、哈希、按页拆分。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from scribeflow.errors import InvalidInput


def page_count(path: Path) -> int:
    try:
        count = len(PdfReader(path, strict=False).pages)
    except Exception as exc:  # pypdf 对损坏文件会抛出多种异常
        raise InvalidInput(f"无法读取 PDF：{path.name}（{exc}）") from exc
    if count < 1:
        raise InvalidInput(f"PDF 没有页面：{path.name}")
    return count


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_pages(source: Path, target: Path, start: int, end: int) -> None:
    """把 [start, end) 页写入 target；写入过程原子化，已存在则跳过。"""

    if target.is_file():
        return
    reader = PdfReader(source, strict=False)
    writer = PdfWriter()
    for page in reader.pages[start:end]:
        writer.add_page(page)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(target)
