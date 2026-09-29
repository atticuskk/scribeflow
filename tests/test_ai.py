from __future__ import annotations

from pathlib import Path

import pytest

from scribeflow.cleaning.ai import AiPlanner, AiSettings, JsonCache, parse_operations, redact_url
from scribeflow.cleaning.operations import Drop, Merge, Origin, SetLevel
from scribeflow.domain import Block, Kind
from scribeflow.errors import AiError

SETTINGS = AiSettings(model="test-model", api_key="sk-secret", chunk_blocks=2)


def blocks(count: int) -> list[Block]:
    return [Block(f"b{i}", Kind.PARAGRAPH, 0, text=f"文字{i}") for i in range(count)]


def test_parse_operations_reads_only_known_fields() -> None:
    content = """```json
    {"drop_ids": ["b1", 3], "drop_reasons": {"b1": "广告"}, "merge_groups": [["b2", "b3"], ["b4", 5]],
     "heading_levels": {"b0": 2, "b9": true}, "replacement_text": {"b2": "改写"}}
    ```"""
    assert parse_operations(content) == [
        Drop("b1", "AI 判断：广告", Origin.AI),
        SetLevel("b0", 2, "AI 调整标题层级", Origin.AI),
        Merge(("b2", "b3"), "AI 判断为同一句或同一段的断裂", Origin.AI),
    ]


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_invalid_responses_raise(content: str) -> None:
    with pytest.raises(AiError):
        parse_operations(content)


def test_planner_chunks_requests_and_uses_cache(tmp_path: Path) -> None:
    calls: list[str] = []

    def completion(messages: list[dict[str, str]], *, json_mode: bool) -> str:
        calls.append(messages[1]["content"])
        return '{"drop_ids": ["b0"]}'

    cache = JsonCache(tmp_path / "cache.json")
    planner = AiPlanner(SETTINGS, completion=completion, cache=cache)
    assert [op.block_id for op in planner.propose(blocks(3)) if isinstance(op, Drop)] == ["b0", "b0"]
    assert len(calls) == 2  # 3 个块、每组最多 2 个

    again = AiPlanner(SETTINGS, completion=completion, cache=JsonCache(tmp_path / "cache.json"))
    again.propose(blocks(3))
    assert len(calls) == 2  # 全部命中缓存


def test_invalid_response_is_not_cached(tmp_path: Path) -> None:
    cache = JsonCache(tmp_path / "cache.json")
    planner = AiPlanner(SETTINGS, completion=lambda messages, *, json_mode: "oops", cache=cache)
    with pytest.raises(AiError):
        planner.propose(blocks(1))
    assert not (tmp_path / "cache.json").exists()


def test_secrets_are_not_exposed() -> None:
    assert "sk-secret" not in repr(SETTINGS)
    assert redact_url("https://user:pw@example.com:8443/v1?key=abc") == "https://example.com:8443/v1"
