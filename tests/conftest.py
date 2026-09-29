from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_logging() -> Iterator[None]:
    logger = logging.getLogger("scribeflow")
    handlers = list(logger.handlers)
    yield
    for handler in list(logger.handlers):
        if handler not in handlers:
            logger.removeHandler(handler)
