from __future__ import annotations

import json
from pathlib import Path

from scribeflow.domain import Kind
from scribeflow.ocr.mineru_format import find_content_list, load_blocks


def write(tmp_path: Path, items: list[dict[str, object]]) -> Path:
    result = tmp_path / "raw" / "s001" / "ocr"
    (result / "images").mkdir(parents=True)
    for name in ("a.jpg", "chart.jpg", "eq.jpg"):
        (result / "images" / name).write_bytes(b"x")
    path = result / "s001_content_list.json"
    path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return path


def test_all_mineru_types_are_mapped(tmp_path: Path) -> None:
    items = [
        {"type": "header", "text": "页眉", "page_idx": 0, "bbox": [1, 2, 3, 4]},
        {"type": "text", "text": "标题", "text_level": 2, "page_idx": 0},
        {"type": "text", "text": "  正文  ", "page_idx": 0},
        {"type": "text", "text": "", "page_idx": 0},
        {"type": "list", "sub_type": "ref_text", "list_items": ["[1] 甲", "[2] 乙"], "page_idx": 1},
        {"type": "equation", "text": "$$\nE=mc^2\n$$", "img_path": "images/eq.jpg", "page_idx": 1},
        {"type": "equation", "img_path": "images/eq.jpg", "page_idx": 1},
        {"type": "chart", "img_path": "images/chart.jpg", "chart_caption": ["图表"], "page_idx": 1},
        {
            "type": "image",
            "img_path": "images/a.jpg",
            "image_caption": ["图 1"],
            "image_footnote": ["注"],
            "page_idx": 1,
        },
        {"type": "image", "img_path": "images/missing.jpg", "page_idx": 1},
        {"type": "table", "table_body": "<table></table>", "table_caption": ["表 1"], "page_idx": 1},
        {"type": "code", "sub_type": "code", "code_body": "print(1)", "code_caption": ["代码"], "page_idx": 1},
        {"type": "page_footnote", "text": "脚注", "page_idx": 1},
        {"type": "text", "text": "标题", "text_level": 9, "page_idx": 1},
    ]
    assets = tmp_path / "assets"
    blocks = load_blocks(
        write(tmp_path, items), id_prefix="s001", page_offset=16, assets_dir=assets, asset_namespace="s001"
    )
    summary = [(b.id, b.kind, b.page) for b in blocks]
    assert summary[0] == ("s001-0001", Kind.MARGINAL, 16)
    assert [b.kind for b in blocks] == [
        Kind.MARGINAL,
        Kind.HEADING,
        Kind.PARAGRAPH,
        Kind.LIST,
        Kind.EQUATION,
        Kind.EQUATION,
        Kind.IMAGE,
        Kind.IMAGE,
        Kind.IMAGE,
        Kind.TABLE,
        Kind.CODE,
        Kind.OTHER,
        Kind.HEADING,
    ]
    assert blocks[0].bbox == (1.0, 2.0, 3.0, 4.0)
    assert blocks[2].text == "正文"
    assert blocks[3].items == ("[1] 甲", "[2] 乙")
    assert blocks[4].text.startswith("$$") and blocks[4].image is None
    assert blocks[5].image == "s001/eq.jpg"
    assert blocks[6].caption == "图表"
    assert (blocks[7].caption, blocks[7].footnote, blocks[7].image) == ("图 1", "注", "s001/a.jpg")
    assert blocks[8].image is None
    assert blocks[12].level == 6
    assert (assets / "s001" / "a.jpg").is_file()


def test_find_content_list_prefers_shallowest(tmp_path: Path) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "x_content_list.json").write_text("[]")
    (tmp_path / "a" / "b" / "y_content_list.json").write_text("[]")
    assert find_content_list(tmp_path).name == "x_content_list.json"
