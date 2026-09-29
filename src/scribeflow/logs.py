"""日志配置：所有模块写入 ``scribeflow`` 命名空间，运行期间额外写入任务日志文件。"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
ROOT = logging.getLogger("scribeflow")


def configure_console() -> None:
    ROOT.setLevel(logging.INFO)
    if not any(getattr(handler, "_scribeflow_console", False) for handler in ROOT.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(FORMAT))
        handler._scribeflow_console = True  # type: ignore[attr-defined]
        ROOT.addHandler(handler)


@contextmanager
def log_to_file(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    if ROOT.level == logging.NOTSET or ROOT.level > logging.INFO:
        ROOT.setLevel(logging.INFO)
    ROOT.addHandler(handler)
    try:
        yield
    finally:
        ROOT.removeHandler(handler)
        handler.close()
