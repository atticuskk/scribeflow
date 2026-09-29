"""按标题把文档切分成章节。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from scribeflow.domain import Block, Kind


@dataclass(frozen=True, slots=True)
class Chapter:
    index: int
    title: str
    blocks: tuple[Block, ...]

    @property
    def filename(self) -> str:
        return f"{self.index:03d}-{slugify(self.title)}.md"


def choose_chapter_level(blocks: Sequence[Block], requested: int | None = None) -> int | None:
    """选择切分层级：显式指定优先，否则取出现至少两次的最高层级。"""

    if requested is not None:
        return requested
    counts: dict[int, int] = {}
    for block in blocks:
        if block.level is not None:
            counts[block.level] = counts.get(block.level, 0) + 1
    for level in sorted(counts):
        if counts[level] >= 2:
            return level
    return min(counts) if counts else None


def split_chapters(blocks: Sequence[Block], level: int | None) -> list[Chapter]:
    """在指定层级的标题处切分。第一个章节标题之前若有正文，单独成为“前言”；
    若只有更高层级的标题（如书名），并入第一章。"""

    if level is None:
        return [Chapter(1, "全文", tuple(blocks))]
    preamble: list[Block] = []
    sections: list[tuple[str, list[Block]]] = []
    for block in blocks:
        if block.level == level:
            sections.append((block.text or "未命名章节", [block]))
        elif sections:
            sections[-1][1].append(block)
        else:
            preamble.append(block)
    if not sections:
        return [Chapter(1, "全文", tuple(blocks))]
    if any(block.kind is not Kind.HEADING for block in preamble):
        sections.insert(0, ("前言", preamble))
    elif preamble:
        title, first = sections[0]
        sections[0] = (title, [*preamble, *first])
    return [Chapter(index, title, tuple(members)) for index, (title, members) in enumerate(sections, start=1)]


def slugify(value: str, fallback: str = "chapter") -> str:
    value = re.sub(r"[^\w㐀-鿿-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-_")
    return value[:60] or fallback
