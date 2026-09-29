from __future__ import annotations

from scribeflow.cleaning.operations import Audit
from scribeflow.cleaning.pipeline import run_rules
from scribeflow.cleaning.rules import (
    DropAdvertisements,
    DropPageNumbers,
    MergeCrossPageSentences,
    MergeEnglishContinuations,
    default_rules,
)
from scribeflow.domain import Block, Kind


def para(block_id: str, text: str, page: int = 0, bbox: tuple[float, float, float, float] | None = None) -> Block:
    return Block(block_id, Kind.PARAGRAPH, page, text=text, bbox=bbox)


def test_marginals_page_numbers_and_ads_are_dropped() -> None:
    blocks = [
        Block("m", Kind.MARGINAL, 0, text="书名页眉", source_type="header"),
        para("n", "- 12 -"),
        para("ad", "广告：扫码关注"),
        para("body", "正文中提到推广普通话，不是广告。"),
    ]
    audit = Audit()
    result = run_rules(blocks, default_rules(), audit)
    assert [b.id for b in result] == ["body"]
    assert [e.reason for e in audit.applied] == [
        "MinerU 标记为 header",
        "规则识别为独立页码",
        "规则识别为广告或推广文字",
    ]


def test_page_number_patterns() -> None:
    rule = DropPageNumbers()
    texts = ["第 3 页", "Page 12", "— 7 —", "3/120", "第三章", "2024 年"]
    dropped = {op.block_id for op in rule.propose([para(str(i), t) for i, t in enumerate(texts)])}  # type: ignore[union-attr]
    assert dropped == {"0", "1", "2", "3"}


def test_long_text_with_ad_word_is_kept() -> None:
    assert DropAdvertisements().propose([para("a", "广告 " + "正文" * 100)]) == []


def test_english_continuations_chain() -> None:
    blocks = [
        para("a", "The principle re-"),
        para("b", "quires parties to act"),
        para("c", "honestly."),
        para("d", "next"),
    ]
    audit = Audit()
    result = run_rules(blocks, [MergeEnglishContinuations()], audit)
    assert [b.text for b in result] == ["The principle requires parties to act honestly.", "next"]


def test_cross_page_sentence_merge() -> None:
    blocks = [
        para("a", "按照自己的意思设立、变更、终止民事", page=0, bbox=(60, 700, 540, 780)),
        para("b", "法律关系。", page=1, bbox=(60, 60, 540, 80)),
    ]
    audit = Audit()
    result = run_rules(blocks, [MergeCrossPageSentences()], audit)
    assert [b.text for b in result] == ["按照自己的意思设立、变更、终止民事法律关系。"]
    assert audit.applied[0].pages == (0, 1)


def test_cross_page_merge_requires_page_boundary_and_open_sentence() -> None:
    rule = MergeCrossPageSentences()
    same_page = [para("a", "没有结束", 0), para("b", "继续", 0)]
    closed = [para("a", "已经结束。", 0), para("b", "新段落", 1)]
    top_of_page = [para("a", "位于页面上方", 0, (60, 100, 540, 150)), para("b", "继续", 1)]
    assert rule.propose(same_page) == []
    assert rule.propose(closed) == []
    assert rule.propose(top_of_page) == []


def test_cross_page_merge_can_be_disabled() -> None:
    assert not any(isinstance(rule, MergeCrossPageSentences) for rule in default_rules(cross_page_merge=False))
