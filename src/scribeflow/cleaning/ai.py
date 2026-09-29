"""可选的 AI 清洗：把内容块发给 OpenAI 兼容接口，只接收块级操作。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit, urlunsplit

from scribeflow.cleaning.operations import Drop, Merge, Operation, Origin, SetLevel
from scribeflow.domain import Block
from scribeflow.errors import AiError

logger = logging.getLogger(__name__)

PROMPT_VERSION = 1
SYSTEM_PROMPT = """你是文档格式清洗器。必须保护原文，禁止改写、润色、摘要、翻译、纠错或生成替代文本。
你只能对给定块 ID 返回以下操作：
1. drop_ids：删除明确的页眉、页脚、独立页码、广告或推广块。
2. merge_groups：合并因分页/OCR而断开的相邻正文块；只能列连续块 ID。
3. heading_levels：把已有标题的 Markdown 层级调整到 1-6；不得把正文改成标题。
4. drop_reasons：为每个删除块给出简短原因。
宁可保留可疑正文，不要误删。返回 JSON 对象，不要返回 Markdown 或解释。"""

OUTPUT_SCHEMA = {
    "drop_ids": ["block_id"],
    "drop_reasons": {"block_id": "reason"},
    "merge_groups": [["adjacent_block_id_1", "adjacent_block_id_2"]],
    "heading_levels": {"heading_block_id": 2},
}


@dataclass(frozen=True, slots=True)
class AiSettings:
    model: str
    api_key: str
    base_url: str | None = None
    timeout_seconds: float = 120.0
    max_retries: int = 3
    chunk_chars: int = 12000
    chunk_blocks: int = 80

    def __repr__(self) -> str:  # 避免密钥出现在日志或异常信息里
        return f"AiSettings(model={self.model!r}, base_url={redact_url(self.base_url)!r})"


def redact_url(value: str | None) -> str | None:
    """去掉 URL 中的用户名、密码和查询参数。"""

    if not value:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return "[已隐藏的地址]"


class Completion(Protocol):
    def __call__(self, messages: list[dict[str, str]], *, json_mode: bool) -> str: ...


class JsonCache:
    """按请求内容哈希缓存 AI 响应，续跑或重新生成时不重复请求。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self._data: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)


def openai_completion(settings: AiSettings) -> Completion:
    from openai import BadRequestError, OpenAI, OpenAIError
    from openai.types.chat import ChatCompletionMessageParam

    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )
    json_supported = True

    def complete(messages: list[dict[str, str]], *, json_mode: bool) -> str:
        nonlocal json_supported
        typed = cast("list[ChatCompletionMessageParam]", messages)
        try:
            if json_mode and json_supported:
                try:
                    response = client.chat.completions.create(
                        model=settings.model,
                        messages=typed,
                        temperature=0,
                        response_format={"type": "json_object"},
                    )
                    return response.choices[0].message.content or ""
                except BadRequestError as exc:
                    json_supported = False
                    logger.warning("AI 服务不支持 JSON 模式，改用兼容模式：%s", exc)
            response = client.chat.completions.create(
                model=settings.model,
                messages=typed,
                temperature=0,
            )
            return response.choices[0].message.content or ""
        except OpenAIError as exc:
            raise AiError(f"AI 清洗请求失败：{exc}") from exc

    return complete


class AiPlanner:
    """把块分组发给模型，返回块级操作。它和确定性规则遵守同一个 Rule 协议。"""

    name = "ai"

    def __init__(
        self,
        settings: AiSettings,
        *,
        completion: Completion | None = None,
        cache: JsonCache | None = None,
    ) -> None:
        self.settings = settings
        self._completion = completion
        self._cache = cache

    def propose(self, blocks: Sequence[Block]) -> list[Operation]:
        chunks = list(self._chunks(blocks))
        operations: list[Operation] = []
        for index, chunk in enumerate(chunks, start=1):
            logger.info("AI 清洗第 %d/%d 组（%d 个块）", index, len(chunks), len(chunk))
            operations.extend(parse_operations(self._request(chunk)))
        return operations

    def _chunks(self, blocks: Sequence[Block]) -> Iterator[list[Block]]:
        chunk: list[Block] = []
        size = 0
        for block in blocks:
            addition = len(block.text) + len(block.table_html or "") + 100
            if chunk and (size + addition > self.settings.chunk_chars or len(chunk) >= self.settings.chunk_blocks):
                yield chunk
                chunk, size = [], 0
            chunk.append(block)
            size += addition
        if chunk:
            yield chunk

    def _request(self, chunk: Sequence[Block]) -> str:
        payload = json.dumps(
            {
                "blocks": [
                    {
                        "id": block.id,
                        "type": block.kind.value,
                        "source_type": block.source_type,
                        "page": block.page + 1,
                        "heading_level": block.level,
                        "text": block.text,
                    }
                    for block in chunk
                ],
                "output_schema": OUTPUT_SCHEMA,
            },
            ensure_ascii=False,
        )
        key = hashlib.sha256(f"{PROMPT_VERSION}\0{self.settings.model}\0{payload}".encode()).hexdigest()
        if self._cache is not None:
            cached = self._cache.get(key)
            if isinstance(cached, str):
                return cached
        if self._completion is None:
            self._completion = openai_completion(self.settings)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": payload}]
        content = self._completion(messages, json_mode=True)
        parse_operations(content)  # 无效响应不写入缓存
        if self._cache is not None:
            self._cache.set(key, content)
        return content


def parse_operations(content: str) -> list[Operation]:
    """把模型响应解析为操作；字段类型不对的条目直接忽略，未知字段不会被读取。"""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AiError(f"AI 返回的不是有效 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise AiError("AI 返回的 JSON 必须是对象")

    reasons = payload.get("drop_reasons")
    reasons = reasons if isinstance(reasons, dict) else {}
    operations: list[Operation] = []
    for block_id in _list(payload.get("drop_ids")):
        if isinstance(block_id, str):
            reason = str(reasons.get(block_id) or "页面噪声或广告")
            operations.append(Drop(block_id, f"AI 判断：{reason}", Origin.AI))
    levels = payload.get("heading_levels")
    for block_id, level in levels.items() if isinstance(levels, dict) else ():
        if isinstance(block_id, str) and isinstance(level, int) and not isinstance(level, bool):
            operations.append(SetLevel(block_id, level, "AI 调整标题层级", Origin.AI))
    for group in _list(payload.get("merge_groups")):
        if isinstance(group, list) and all(isinstance(item, str) for item in group):
            operations.append(Merge(tuple(group), "AI 判断为同一句或同一段的断裂", Origin.AI))
    return operations


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []
