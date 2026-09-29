"""文档的统一表示：OCR 引擎产出 Block，清洗、结构分析和渲染只消费 Block。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Self


class Kind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    EQUATION = "equation"
    CODE = "code"
    MARGINAL = "marginal"  # 页眉、页脚、页码：保留在块序列中，由清洗规则删除并审计
    OTHER = "other"


BBox = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Block:
    """OCR 输出的一个内容块。

    ``page`` 是源 PDF 中从 0 开始的页码；``bbox`` 使用 MinerU 的 0–1000 归一化坐标；
    ``image`` 是相对输出目录 ``assets/`` 的路径。
    """

    id: str
    kind: Kind
    page: int
    text: str = ""
    level: int | None = None
    bbox: BBox | None = None
    image: str | None = None
    table_html: str | None = None
    caption: str = ""
    footnote: str = ""
    items: tuple[str, ...] = field(default_factory=tuple)
    source_type: str = ""

    def __post_init__(self) -> None:
        if (self.kind is Kind.HEADING) != (self.level is not None):
            raise ValueError(f"块 {self.id}：只有标题块才有层级")
        if self.level is not None and not 1 <= self.level <= 6:
            raise ValueError(f"块 {self.id}：标题层级必须在 1–6 之间")

    def with_changes(self, **changes: Any) -> Self:
        return replace(self, **changes)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "kind": self.kind.value, "page": self.page}
        optional = {
            "text": self.text,
            "level": self.level,
            "bbox": list(self.bbox) if self.bbox else None,
            "image": self.image,
            "table_html": self.table_html,
            "caption": self.caption,
            "footnote": self.footnote,
            "items": list(self.items),
            "source_type": self.source_type,
        }
        data.update({key: value for key, value in optional.items() if value})
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        bbox = data.get("bbox")
        return cls(
            id=str(data["id"]),
            kind=Kind(data["kind"]),
            page=int(data["page"]),
            text=str(data.get("text", "")),
            level=data.get("level"),
            bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])) if bbox else None,
            image=data.get("image"),
            table_html=data.get("table_html"),
            caption=str(data.get("caption", "")),
            footnote=str(data.get("footnote", "")),
            items=tuple(data.get("items", ())),
            source_type=str(data.get("source_type", "")),
        )
