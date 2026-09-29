"""把 MinerU 的 ``*_content_list.json`` 转成 Block。

字段含义以 MinerU 3.4.4 ``make_blocks_to_content_list`` 为准：
标题是带 ``text_level`` 的 text；页眉/页脚/页码保留原类型；参考文献为 list；
公式的 text 已包含 ``$$`` 定界符；图片、图表、表格、代码各带说明与脚注列表。
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from scribeflow.domain import BBox, Block, Kind
from scribeflow.errors import OcrError

logger = logging.getLogger(__name__)

MARGINAL_TYPES = frozenset({"header", "footer", "page_number", "page_header", "page_footer"})
EQUATION_TYPES = frozenset({"equation", "interline_equation"})
IMAGE_TYPES = frozenset({"image", "chart", "figure"})


def find_content_list(result_dir: Path) -> Path:
    candidates = sorted(
        (path for path in result_dir.rglob("*_content_list.json")),
        key=lambda path: (len(path.parts), str(path)),
    )
    if not candidates:
        raise OcrError(f"MinerU 已结束，但没有生成 content_list：{result_dir}")
    return candidates[0]


def load_blocks(
    content_list: Path,
    *,
    id_prefix: str,
    page_offset: int,
    assets_dir: Path,
    asset_namespace: str,
) -> list[Block]:
    try:
        payload = json.loads(content_list.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OcrError(f"无法读取 MinerU 结果：{content_list}：{exc}") from exc
    if not isinstance(payload, list):
        raise OcrError(f"MinerU 结果格式异常（应为列表）：{content_list}")

    source_dir = content_list.parent
    blocks: list[Block] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        block = _to_block(item, f"{id_prefix}-{len(blocks) + 1:04d}", page_offset)
        if block is None:
            continue
        if block.image:
            block = block.with_changes(image=_import_asset(source_dir, block.image, assets_dir, asset_namespace))
        blocks.append(block)
    return blocks


def _to_block(item: dict[str, Any], block_id: str, page_offset: int) -> Block | None:
    source_type = str(item.get("type", ""))
    page = page_offset + _int(item.get("page_idx"))
    bbox = _bbox(item.get("bbox"))
    text = _text(item.get("text")).strip()
    common: dict[str, Any] = {"id": block_id, "page": page, "bbox": bbox, "source_type": source_type}

    level = item.get("text_level")
    if source_type == "text" and isinstance(level, int) and not isinstance(level, bool) and level > 0:
        return Block(kind=Kind.HEADING, text=text, level=min(level, 6), **common)
    if source_type == "text":
        return Block(kind=Kind.PARAGRAPH, text=text, **common) if text else None
    if source_type in MARGINAL_TYPES:
        return Block(kind=Kind.MARGINAL, text=text or _text(item).strip(), **common)
    if source_type == "list":
        items = tuple(part for part in (_text(entry).strip() for entry in _seq(item.get("list_items"))) if part)
        return Block(kind=Kind.LIST, items=items, **common) if items else None
    if source_type in EQUATION_TYPES:
        text = text or _text(item.get("latex")).strip()
        image = None if text else _str_or_none(item.get("img_path"))
        return Block(kind=Kind.EQUATION, text=text, image=image, **common) if text or image else None
    if source_type == "table":
        return Block(
            kind=Kind.TABLE,
            table_html=_str_or_none(item.get("table_body")),
            image=_str_or_none(item.get("img_path")),
            caption=_joined(item.get("table_caption")),
            footnote=_joined(item.get("table_footnote")),
            **common,
        )
    if source_type in IMAGE_TYPES:
        return Block(
            kind=Kind.IMAGE,
            image=_str_or_none(item.get("img_path")),
            caption=_joined(item.get(f"{source_type}_caption") or item.get("caption")),
            footnote=_joined(item.get(f"{source_type}_footnote")),
            **common,
        )
    if source_type == "code":
        body = _text(item.get("code_body")).strip()
        caption = _joined(item.get("code_caption"))
        return Block(kind=Kind.CODE, text=body, caption=caption, **common) if body else None
    return Block(kind=Kind.OTHER, text=text, **common) if text else None


def _import_asset(source_dir: Path, relative: str, assets_dir: Path, namespace: str) -> str | None:
    source = source_dir / relative
    if not source.is_file():
        logger.warning("MinerU 引用的图片不存在：%s", source)
        return None
    target_relative = f"{namespace}/{source.name}"
    target = assets_dir / target_relative
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return target_relative


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(item) for item in value)
    if isinstance(value, dict):
        for key in (
            "text",
            "content",
            "title_content",
            "paragraph_content",
            "page_header_content",
            "page_footer_content",
            "page_number_content",
        ):
            if key in value:
                return _text(value[key])
    return ""


def _joined(value: object) -> str:
    if isinstance(value, list):
        return " ".join(part for part in (_text(item).strip() for item in value) if part)
    return _text(value).strip()


def _seq(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _bbox(value: object) -> BBox | None:
    if isinstance(value, list) and len(value) == 4 and all(isinstance(v, int | float) for v in value):
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    return None
