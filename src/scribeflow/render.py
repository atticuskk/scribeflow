"""把块序列渲染为 Markdown。"""

from __future__ import annotations

from collections.abc import Iterable

from scribeflow.domain import Block, Kind


def render_markdown(blocks: Iterable[Block], *, assets_prefix: str) -> str:
    parts = [part for part in (_render(block, assets_prefix) for block in blocks) if part]
    return "\n\n".join(parts).strip() + "\n"


def _render(block: Block, prefix: str) -> str:
    match block.kind:
        case Kind.HEADING:
            return f"{'#' * (block.level or 1)} {block.text}" if block.text else ""
        case Kind.LIST:
            return "\n".join(f"- {item}" for item in block.items)
        case Kind.EQUATION:
            if block.text:
                return block.text if block.text.startswith("$$") else f"$$\n{block.text}\n$$"
            return _image(block, prefix, "公式")
        case Kind.TABLE:
            body = block.table_html or _image(block, prefix, "表格")
            return _join(f"**{block.caption}**" if block.caption else "", body, _note(block.footnote)) if body else ""
        case Kind.IMAGE:
            image = _image(block, prefix, block.caption or "图片")
            caption = f"*{block.caption}*" if block.caption else ""
            return _join(image, caption, _note(block.footnote)) if image else ""
        case Kind.CODE:
            if not block.text:
                return ""
            return _join(f"**{block.caption}**" if block.caption else "", f"```\n{block.text}\n```")
        case _:
            return block.text


def _image(block: Block, prefix: str, alt: str) -> str:
    if not block.image:
        return ""
    alt = alt.replace("[", "\\[").replace("]", "\\]")
    return f"![{alt}]({prefix}/{block.image})"


def _note(text: str) -> str:
    return f"> {text}" if text else ""


def _join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
