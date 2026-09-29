"""块级清洗操作。

规则和 AI 都只能提出三种操作：删除块、合并相邻正文块、调整已有标题的层级。
所有操作经 ``apply_operations`` 统一校验后执行，并自动写入审计；
没有任何操作能提供替换正文，这是“保真”的结构性保证。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from scribeflow.domain import Block, Kind


class Origin(StrEnum):
    RULE = "rule"
    AI = "ai"


@dataclass(frozen=True, slots=True)
class Drop:
    block_id: str
    reason: str
    origin: Origin = Origin.RULE


@dataclass(frozen=True, slots=True)
class Merge:
    block_ids: tuple[str, ...]
    reason: str
    origin: Origin = Origin.RULE


@dataclass(frozen=True, slots=True)
class SetLevel:
    block_id: str
    level: int
    reason: str
    origin: Origin = Origin.RULE


Operation = Drop | Merge | SetLevel


@dataclass(frozen=True, slots=True)
class AuditEntry:
    action: str
    block_ids: tuple[str, ...]
    reason: str
    origin: Origin
    pages: tuple[int, ...]
    original: tuple[str, ...]
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "action": self.action,
            "block_ids": list(self.block_ids),
            "reason": self.reason,
            "origin": self.origin.value,
            "pages": [page + 1 for page in self.pages],
            "original": list(self.original),
        }
        if self.detail:
            data["detail"] = self.detail
        return data


@dataclass(frozen=True, slots=True)
class Rejection:
    operation: Operation
    why: str

    def to_json(self) -> dict[str, Any]:
        op = self.operation
        ids = list(op.block_ids) if isinstance(op, Merge) else [op.block_id]
        return {
            "action": _action_name(op),
            "block_ids": ids,
            "origin": op.origin.value,
            "reason": op.reason,
            "rejected_because": self.why,
        }


@dataclass(slots=True)
class Audit:
    applied: list[AuditEntry] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for entry in self.applied if entry.action == action)

    def to_json(self) -> dict[str, Any]:
        return {
            "applied": [entry.to_json() for entry in self.applied],
            "rejected": [rejection.to_json() for rejection in self.rejected],
        }


def _action_name(op: Operation) -> str:
    if isinstance(op, Drop):
        return "drop"
    if isinstance(op, Merge):
        return "merge"
    return "set_level"


_CJK = r"㐀-鿿豈-﫿"
_CJK_END_RE = re.compile(rf"[{_CJK}　-〿＀-￯]$")
_CJK_START_RE = re.compile(rf"^[{_CJK}　-〿＀-￯]")


def join_texts(first: str, second: str) -> str:
    """拼接两段因换行/分页断开的文字，只调整连接处的空白和英文连字符。"""

    if first.endswith("-") and re.match(r"^[A-Za-z]", second):
        return first[:-1] + second
    if _CJK_END_RE.search(first) and _CJK_START_RE.search(second):
        return first + second
    return first.rstrip() + " " + second.lstrip()


def apply_operations(
    blocks: Sequence[Block],
    operations: Iterable[Operation],
    audit: Audit,
) -> list[Block]:
    """校验并执行一批操作。执行顺序固定为：删除 → 层级 → 合并。"""

    ops = list(operations)
    by_id = {block.id: block for block in blocks}

    dropped: set[str] = set()
    for op in ops:
        if not isinstance(op, Drop):
            continue
        if op.block_id not in by_id:
            audit.rejected.append(Rejection(op, "块不存在"))
        elif op.block_id in dropped:
            continue
        else:
            dropped.add(op.block_id)
            block = by_id[op.block_id]
            audit.applied.append(AuditEntry("drop", (block.id,), op.reason, op.origin, (block.page,), (block.text,)))

    levels: dict[str, int] = {}
    for op in ops:
        if not isinstance(op, SetLevel):
            continue
        heading = by_id.get(op.block_id)
        if heading is None or op.block_id in dropped:
            audit.rejected.append(Rejection(op, "块不存在或已删除"))
        elif heading.kind is not Kind.HEADING:
            audit.rejected.append(Rejection(op, "只能调整已有标题"))
        elif not 1 <= op.level <= 6:
            audit.rejected.append(Rejection(op, "层级必须在 1–6 之间"))
        elif op.level != heading.level and op.block_id not in levels:
            levels[op.block_id] = op.level
            audit.applied.append(
                AuditEntry(
                    "set_level",
                    (heading.id,),
                    op.reason,
                    op.origin,
                    (heading.page,),
                    (heading.text,),
                    detail=f"{heading.level} -> {op.level}",
                )
            )

    remaining = [block for block in blocks if block.id not in dropped]
    position = {block.id: index for index, block in enumerate(remaining)}
    groups: dict[str, tuple[str, ...]] = {}
    grouped: set[str] = set()
    for op in ops:
        if not isinstance(op, Merge):
            continue
        why = _merge_problem(op, position, by_id, grouped)
        if why:
            audit.rejected.append(Rejection(op, why))
            continue
        groups[op.block_ids[0]] = op.block_ids
        grouped.update(op.block_ids)
        members = [by_id[block_id] for block_id in op.block_ids]
        audit.applied.append(
            AuditEntry(
                "merge",
                op.block_ids,
                op.reason,
                op.origin,
                tuple(block.page for block in members),
                tuple(block.text for block in members),
            )
        )

    result: list[Block] = []
    for block in remaining:
        if block.id in grouped and block.id not in groups:
            continue
        current = block
        if block.id in levels:
            current = current.with_changes(level=levels[block.id])
        if block.id in groups:
            text = current.text
            for member_id in groups[block.id][1:]:
                text = join_texts(text, by_id[member_id].text)
            current = current.with_changes(text=text)
        result.append(current)
    return result


def _merge_problem(
    op: Merge,
    position: dict[str, int],
    by_id: dict[str, Block],
    grouped: set[str],
) -> str:
    ids = op.block_ids
    if len(ids) < 2 or len(set(ids)) != len(ids):
        return "合并至少需要两个不同的块"
    if any(block_id not in position for block_id in ids):
        return "块不存在或已删除"
    indexes = [position[block_id] for block_id in ids]
    if indexes != list(range(indexes[0], indexes[0] + len(ids))):
        return "只能合并相邻的块"
    if any(by_id[block_id].kind is not Kind.PARAGRAPH for block_id in ids):
        return "只能合并正文段落"
    if grouped.intersection(ids):
        return "与本批次其他合并重叠"
    return ""
