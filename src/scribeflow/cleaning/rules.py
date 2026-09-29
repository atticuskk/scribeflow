"""确定性清洗规则。每条规则只“提议”操作，由 apply_operations 统一执行。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise
from typing import Protocol

from scribeflow.cleaning.operations import Drop, Merge, Operation
from scribeflow.domain import Block, Kind


class Rule(Protocol):
    name: str

    def propose(self, blocks: Sequence[Block]) -> list[Operation]: ...


SENTENCE_END_RE = re.compile(r"[。！？.!?；;：:）)\]】”’\"'…]$")


class DropMarginals:
    """删除 MinerU 标记为页眉、页脚、页码的块。"""

    name = "marginals"

    def propose(self, blocks: Sequence[Block]) -> list[Operation]:
        return [
            Drop(block.id, f"MinerU 标记为 {block.source_type or 'marginal'}")
            for block in blocks
            if block.kind is Kind.MARGINAL
        ]


class DropPageNumbers:
    """删除内容只有页码的正文块，如“第 3 页”“- 3 -”“3/120”。"""

    name = "page_numbers"
    pattern = re.compile(
        r"^\s*(?:第\s*\d{1,4}\s*页|Page\s+\d{1,4}|[-—–]\s*\d{1,4}\s*[-—–]|\d{1,4}\s*/\s*\d{1,4})\s*$",
        re.IGNORECASE,
    )

    def propose(self, blocks: Sequence[Block]) -> list[Operation]:
        return [
            Drop(block.id, "规则识别为独立页码")
            for block in blocks
            if block.kind is Kind.PARAGRAPH and self.pattern.fullmatch(block.text)
        ]


class DropAdvertisements:
    """删除以明确广告词开头或独立出现的短块。"""

    name = "advertisements"
    max_length = 160
    pattern = re.compile(
        r"(?:^|\s)(?:广告|ADVERTISEMENT|推广|赞助内容|商业合作|扫码关注|点击购买)(?:\s|[:：]|$)",
        re.IGNORECASE,
    )

    def propose(self, blocks: Sequence[Block]) -> list[Operation]:
        return [
            Drop(block.id, "规则识别为广告或推广文字")
            for block in blocks
            if block.kind is Kind.PARAGRAPH and len(block.text) <= self.max_length and self.pattern.search(block.text)
        ]


def _continues(previous: Block, following: Block, starts: re.Pattern[str]) -> bool:
    return (
        previous.kind is Kind.PARAGRAPH
        and following.kind is Kind.PARAGRAPH
        and bool(previous.text)
        and bool(following.text)
        and not SENTENCE_END_RE.search(previous.text)
        and starts.match(following.text) is not None
    )


class MergeEnglishContinuations:
    """合并英文小写续行和连字符断词，连续多行会合并为一组。"""

    name = "english_continuations"
    lowercase_start = re.compile(r"^[a-z]")

    def propose(self, blocks: Sequence[Block]) -> list[Operation]:
        groups: list[list[str]] = []
        for previous, following in pairwise(blocks):
            if not _continues(previous, following, self.lowercase_start):
                continue
            if groups and groups[-1][-1] == previous.id:
                groups[-1].append(following.id)
            else:
                groups.append([previous.id, following.id])
        return [Merge(tuple(group), "英文小写续行或连字符断词") for group in groups]


class MergeCrossPageSentences:
    """合并被分页截断的中文句子。

    条件同时满足才合并：前一块是某页最后一个块、后一块是下一页第一个块，
    两者都是正文；前一块不以句末标点结束且以汉字或逗号类标点结尾，
    后一块以汉字开头；有坐标时前一块位于页面下部、后一块位于页面上部。
    """

    name = "cross_page_sentences"
    previous_end = re.compile(r"[㐀-鿿豈-﫿，、]$")
    following_start = re.compile(r"^[㐀-鿿豈-﫿]")
    lower_half = 500.0

    def propose(self, blocks: Sequence[Block]) -> list[Operation]:
        operations: list[Operation] = []
        for previous, following in pairwise(blocks):
            if following.page != previous.page + 1:
                continue
            if not _continues(previous, following, self.following_start):
                continue
            if not self.previous_end.search(previous.text):
                continue
            if previous.bbox and previous.bbox[3] < self.lower_half:
                continue
            if following.bbox and following.bbox[1] > self.lower_half:
                continue
            operations.append(Merge((previous.id, following.id), "分页截断的中文句子"))
        return operations


def default_rules(*, cross_page_merge: bool = True) -> list[Rule]:
    rules: list[Rule] = [DropMarginals(), DropPageNumbers(), DropAdvertisements(), MergeEnglishContinuations()]
    if cross_page_merge:
        rules.append(MergeCrossPageSentences())
    return rules
