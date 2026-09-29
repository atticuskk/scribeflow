"""启动子进程并保证能连同其子进程一起终止。"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    tail: tuple[str, ...]


def popen_group(command: Sequence[str], *, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        start_new_session=True,  # 独立进程组，便于整组终止
    )


def terminate_group(process: subprocess.Popen[str], *, grace_seconds: float = 10.0) -> None:
    if process.poll() is not None:
        return
    for sig, wait in ((signal.SIGTERM, grace_seconds), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def run_streaming(
    command: Sequence[str],
    *,
    env: dict[str, str],
    logger: logging.Logger,
    prefix: str,
    on_line: Callable[[str], None] | None = None,
) -> ProcessResult:
    """运行命令，逐行写日志；无论正常结束还是被取消，都不留下子进程。"""

    tail: deque[str] = deque(maxlen=20)
    process = popen_group(command, env=env)
    try:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if not line:
                continue
            tail.append(line)
            logger.info("%s | %s", prefix, line)
            if on_line is not None:
                on_line(line)
        return ProcessResult(process.wait(), tuple(tail))
    finally:
        terminate_group(process)


def pump_output(process: subprocess.Popen[str], logger: logging.Logger, prefix: str) -> threading.Thread:
    """后台线程持续读取长期运行进程的输出，避免管道写满阻塞。"""

    def pump() -> None:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if line:
                logger.info("%s | %s", prefix, line)

    thread = threading.Thread(target=pump, name=f"{prefix}-output", daemon=True)
    thread.start()
    return thread
