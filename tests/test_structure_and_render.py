from __future__ import annotations

from scribeflow.domain import Block, Kind
from scribeflow.render import render_markdown
from scribeflow.structure import choose_chapter_level, slugify, split_chapters


def h(block_id: str, text: str, level: int) -> Block:
    return Block(block_id, Kind.HEADING, 0, text=text, level=level)


def p(block_id: str, text: str) -> Block:
    return Block(block_id, Kind.PARAGRAPH, 0, text=text)


def test_chapter_level_prefers_highest_repeated_level() -> None:
    blocks = [h("t", "书名", 1), h("a", "第一章", 2), p("x", "内容"), h("b", "第二章", 2)]
    assert choose_chapter_level(blocks) == 2
    assert choose_chapter_level(blocks, 1) == 1
    assert choose_chapter_level([p("x", "无标题")]) is None


def test_title_before_first_chapter_joins_first_chapter() -> None:
    chapters = split_chapters([h("t", "书名", 1), h("a", "第一章", 2), p("x", "内容"), h("b", "第二章", 2)], 2)
    assert [(c.title, [b.id for b in c.blocks]) for c in chapters] == [("第一章", ["t", "a", "x"]), ("第二章", ["b"])]
    assert chapters[0].filename == "001-第一章.md"


def test_body_before_first_chapter_becomes_preface() -> None:
    chapters = split_chapters([p("x", "序"), h("a", "第一章", 1)], 1)
    assert [c.title for c in chapters] == ["前言", "第一章"]


def test_no_headings_gives_single_chapter() -> None:
    assert [c.title for c in split_chapters([p("x", "全文")], None)] == ["全文"]


def test_slugify() -> None:
    assert slugify("第一章：开始") == "第一章-开始"
    assert slugify("///") == "chapter"


def test_render_all_kinds() -> None:
    blocks = [
        h("h", "标题", 2),
        p("p", "正文"),
        Block("l", Kind.LIST, 0, items=("甲", "乙")),
        Block("e1", Kind.EQUATION, 0, text="$$\nx\n$$"),
        Block("e2", Kind.EQUATION, 0, text="y"),
        Block("e3", Kind.EQUATION, 0, image="s001/eq.jpg"),
        Block("t", Kind.TABLE, 0, table_html="<table/>", caption="表 1", footnote="注"),
        Block("i", Kind.IMAGE, 0, image="s001/a.jpg", caption="图 [1]"),
        Block("i2", Kind.IMAGE, 0),
        Block("c", Kind.CODE, 0, text="print(1)"),
        Block("o", Kind.OTHER, 0, text="脚注"),
    ]
    assert render_markdown(blocks, assets_prefix="../assets") == (
        "## 标题\n\n正文\n\n- 甲\n- 乙\n\n$$\nx\n$$\n\n$$\ny\n$$\n\n![公式](../assets/s001/eq.jpg)\n\n"
        "**表 1**\n\n<table/>\n\n> 注\n\n![图 \\[1\\]](../assets/s001/a.jpg)\n\n*图 [1]*\n\n"
        "```\nprint(1)\n```\n\n脚注\n"
    )
