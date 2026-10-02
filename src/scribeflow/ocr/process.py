"""启动子进程并保证能连同其子进程一起终止。"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass

PROGRESS_RE = re.compile(r"^(?P<label>.*?):?\s*(?P<percent>\d{1,3})%\|")


class ProgressFilter:
    """MinerU 的 tqdm 进度条约每 0.1 秒用 ``\\r`` 重绘一次，读取时每次重绘都是单独一行，
    全部写进日志会让日志文件膨胀、界面频繁刷新。每个进度条只保留第一行、完成行，
    以及中间每隔 ``interval`` 秒一行；其他输出原样保留。"""

    def __init__(self, interval: float = 10.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._interval = interval
        self._clock = clock
        self._last: dict[str, tuple[float, str]] = {}

    def keep(self, line: str) -> bool:
        match = PROGRESS_RE.match(line)
        if match is None:
            return True
        label = match["label"].strip()
        now = self._clock()
        last = self._last.get(label)
        if last is not None:
            if line == last[1]:  # tqdm 结束时会重复输出最后一行
                return False
            if match["percent"] != "100" and now - last[0] < self._interval:
                return False
        self._last[label] = (now, line)
        return True


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    tail: tuple[str, ...]


def popen_group(command: Sequence[str], *, env: dict[str, str], stdin_pipe: bool = False) -> subprocess.Popen[str]:
    return subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        start_new_session=True,  # 独立进程组，便于整组终止
    )


def terminate_group(process: subprocess.Popen[str], *, grace_seconds: float = 3.0) -> None:
    """立即结束整个进程组：先 SIGTERM，宽限期后 SIGKILL。用于取消、出错和服务崩溃后的清理。

    即使组长进程已经退出（例如服务被外部杀死），组内其他成员（如 resource_tracker）
    仍可能存活，所以始终以进程组为单位检查和发送信号。
    """

    pgid = process.pid
    for sig, wait in ((signal.SIGTERM, grace_seconds), (signal.SIGKILL, 3.0)):
        process.poll()  # 回收已退出的组长，避免僵尸进程被当作存活成员
        if not _group_alive(pgid):
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, sig)
        if _wait_group(process, wait):
            return


def _wait_group(process: subprocess.Popen[str], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        process.poll()
        if not _group_alive(process.pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def close_gracefully(process: subprocess.Popen[str], *, timeout: float = 30.0, drain: float = 5.0) -> None:
    """关闭 stdin 请进程自行退出（MinerU 服务的官方关闭方式），
    让它和它的子进程（如 multiprocessing 的 resource_tracker）有机会清理资源；超时再强制结束。"""

    if process.stdin is not None:
        with contextlib.suppress(OSError):
            process.stdin.close()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_group(process)
        return
    if not _wait_group(process, drain):
        terminate_group(process, grace_seconds=0.5)


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
    progress = ProgressFilter()
    process = popen_group(command, env=env)
    try:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if not line:
                continue
            if on_line is not None:
                on_line(line)
            if progress.keep(line):
                tail.append(line)
                logger.info("%s | %s", prefix, line)
        return ProcessResult(process.wait(), tuple(tail))
    finally:
        if process.poll() is None:  # 被取消或出错：立即结束
            terminate_group(process)
        elif not _wait_group(process, 5.0):  # 正常退出：给同组子进程时间自行收尾
            terminate_group(process, grace_seconds=0.5)


def pump_output(process: subprocess.Popen[str], logger: logging.Logger, prefix: str) -> threading.Thread:
    """后台线程持续读取长期运行进程的输出，避免管道写满阻塞。"""

    def pump() -> None:
        assert process.stdout is not None
        progress = ProgressFilter()
        for raw in process.stdout:
            line = raw.rstrip()
            if line and progress.keep(line):
                logger.info("%s | %s", prefix, line)

    thread = threading.Thread(target=pump, name=f"{prefix}-output", daemon=True)
    thread.start()
    return thread
