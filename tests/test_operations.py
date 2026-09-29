from __future__ import annotations

import pytest

from scribeflow.cleaning.operations import Audit, Drop, Merge, Origin, SetLevel, apply_operations, join_texts
from scribeflow.domain import Block, Kind


def para(block_id: str, text: str, page: int = 0) -> Block:
    return Block(block_id, Kind.PARAGRAPH, page, text=text)


def heading(block_id: str, text: str, level: int = 1) -> Block:
    return Block(block_id, Kind.HEADING, 0, text=text, level=level)


def test_valid_operations_are_applied_and_audited() -> None:
    blocks = [heading("h", "第一章"), para("a", "这是断开的前半句"), para("b", "后半句。"), para("c", "赞助内容")]
    audit = Audit()
    result = apply_operations(
        blocks,
        [Drop("c", "广告", Origin.AI), Merge(("a", "b"), "断句", Origin.AI), SetLevel("h", 2, "层级", Origin.AI)],
        audit,
    )
    assert [(b.id, b.text, b.level) for b in result] == [("h", "第一章", 2), ("a", "这是断开的前半句后半句。", None)]
    assert [entry.action for entry in audit.applied] == ["drop", "set_level", "merge"]
    assert audit.applied[2].original == ("这是断开的前半句", "后半句。")
    assert audit.rejected == []


@pytest.mark.parametrize(
    ("operation", "why"),
    [
        (Drop("missing", "x"), "块不存在"),
        (Merge(("h", "a"), "x"), "只能合并正文段落"),
        (Merge(("a", "c"), "x"), "只能合并相邻的块"),
        (Merge(("a",), "x"), "合并至少需要两个不同的块"),
        (SetLevel("a", 2, "x"), "只能调整已有标题"),
        (SetLevel("h", 9, "x"), "层级必须在 1–6 之间"),
    ],
)
def test_invalid_operations_are_rejected(operation: Drop | Merge | SetLevel, why: str) -> None:
    blocks = [heading("h", "标题"), para("a", "甲"), para("b", "乙"), para("c", "丙")]
    audit = Audit()
    result = apply_operations(blocks, [operation], audit)
    assert result == blocks
    assert [rejection.why for rejection in audit.rejected] == [why]


def test_merge_adjacency_is_checked_after_drops() -> None:
    blocks = [para("a", "前半"), para("noise", "广告"), para("b", "后半")]
    audit = Audit()
    result = apply_operations(blocks, [Drop("noise", "广告"), Merge(("a", "b"), "断句")], audit)
    assert [b.text for b in result] == ["前半后半"]


def test_overlapping_merges_keep_the_first() -> None:
    blocks = [para("a", "one"), para("b", "two"), para("c", "three")]
    audit = Audit()
    result = apply_operations(blocks, [Merge(("a", "b"), "x"), Merge(("b", "c"), "x")], audit)
    assert [b.text for b in result] == ["one two", "three"]
    assert audit.rejected[0].why == "与本批次其他合并重叠"


def test_dropped_heading_cannot_change_level() -> None:
    audit = Audit()
    apply_operations([heading("h", "页眉")], [Drop("h", "x"), SetLevel("h", 2, "x")], audit)
    assert audit.rejected[0].why == "块不存在或已删除"


@pytest.mark.parametrize(
    ("first", "second", "joined"),
    [
        ("inter-", "national", "international"),
        ("中文句子", "继续", "中文句子继续"),
        ("逗号，", "继续", "逗号，继续"),
        ("end of", "line", "end of line"),
    ],
)
def test_join_texts(first: str, second: str, joined: str) -> None:
    assert join_texts(first, second) == joined
