"""按顺序运行清洗规则：每条规则看到的是前一条规则执行后的块序列。"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from scribeflow.cleaning.operations import Audit, apply_operations
from scribeflow.cleaning.rules import Rule
from scribeflow.domain import Block

logger = logging.getLogger(__name__)


def run_rules(blocks: Sequence[Block], rules: Sequence[Rule], audit: Audit) -> list[Block]:
    current = list(blocks)
    for rule in rules:
        before = len(audit.applied)
        current = apply_operations(current, rule.propose(current), audit)
        applied = len(audit.applied) - before
        if applied:
            logger.info("清洗规则 %s：执行 %d 项操作", rule.name, applied)
    return current
