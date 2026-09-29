"""通过真实子进程运行 CLI，并用伪造的 mineru / mineru-api 程序替代 MinerU。"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from fakes import BOOK_PAGES, book_pages, install_fake_mineru, make_pdf

ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="依赖 POSIX 进程组")


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.state = tmp_path / "state"
        self.state.mkdir()
        self.mineru = install_fake_mineru(tmp_path / "bin")
        self.pdf = make_pdf(tmp_path / "book.pdf", len(book_pages()))
        self.output = tmp_path / "out" / "book-Markdown"
        self.env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "FAKE_MINERU_STATE": str(self.state),
            "FAKE_MINERU_PAGES": str(BOOK_PAGES),
            "FAKE_MINERU_SEGMENT_PAGES": "2",
        }
        self.env.pop("MINERU_TASK_RESULT_TIMEOUT_SECONDS", None)

    def command(self, *extra: str) -> list[str]:
        return [
            sys.executable,
            "-m",
            "scribeflow",
            "convert",
            str(self.pdf),
            "-o",
            str(self.output),
            "--segment-pages",
            "2",
            "--mineru",
            str(self.mineru),
            "--events",
            "jsonl",
            *extra,
        ]

    def run(self, *extra: str, **env: str) -> tuple[int, list[dict[str, Any]], str]:
        completed = subprocess.run(
            self.command(*extra), env={**self.env, **env}, capture_output=True, text=True, timeout=60
        )
        return completed.returncode, parse(completed.stdout), completed.stderr

    def client_calls(self) -> list[dict[str, Any]]:
        path = self.state / "client-calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def server_pids(self) -> list[int]:
        path = self.state / "server-starts.txt"
        return [int(pid) for pid in path.read_text().split()] if path.exists() else []


def parse(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_convert_uses_one_shared_mineru_server(harness: Harness) -> None:
    code, events, stderr = harness.run()
    assert code == 0, stderr
    assert events[-1]["event"] == "completed"
    assert events[-1]["chapters"] == 4
    calls = harness.client_calls()
    assert [Path(call["pdf"]).name for call in calls] == ["s001.pdf", "s002.pdf", "s003.pdf"]
    assert len({call["api_url"] for call in calls}) == 1 and calls[0]["api_url"].startswith("http://127.0.0.1:")
    assert {call["timeout"] for call in calls} == {"3600"}
    assert {call["model_source"] for call in calls} == {"modelscope"}
    assert len(harness.server_pids()) == 1
    assert not alive(harness.server_pids()[0])
    graceful = harness.state / "server-graceful.txt"
    assert graceful.read_text().split() == [str(harness.server_pids()[0])]  # 通过关闭 stdin 正常退出
    assert "fake mineru client done" in stderr  # MinerU 输出进入日志（stderr）
    diagnostics = next(e for e in events if e["event"] == "diagnostics")
    assert diagnostics["values"]["服务"].startswith("http://127.0.0.1:")


def test_per_segment_mode_does_not_start_server(harness: Harness) -> None:
    code, _, stderr = harness.run("--no-shared-server")
    assert code == 0, stderr
    assert [call["api_url"] for call in harness.client_calls()] == [None, None, None]
    assert harness.server_pids() == []


def test_crashed_server_is_restarted_and_segment_retried(harness: Harness) -> None:
    code, _, stderr = harness.run(FAKE_MINERU_KILL_SERVER="2")
    assert code == 0, stderr
    assert len(harness.server_pids()) == 2
    assert [Path(call["pdf"]).name for call in harness.client_calls()] == [
        "s001.pdf",
        "s002.pdf",
        "s002.pdf",
        "s003.pdf",
    ]
    assert "重启后重试第 2 段" in stderr


def test_failure_then_resume(harness: Harness) -> None:
    code, events, _ = harness.run(FAKE_MINERU_FAIL="2")
    assert code == 1
    failed = events[-1]
    assert failed["event"] == "failed" and failed["code"] == "ocr_failed" and failed["resumable"]
    assert "simulated OCR crash" in failed["message"]
    assert Path(failed["log"]).is_file()

    code, events, stderr = harness.run()
    assert code == 0, stderr
    started = next(e for e in events if e["event"] == "started")
    assert started["resumed"] is True
    assert [Path(call["pdf"]).name for call in harness.client_calls()] == [
        "s001.pdf",
        "s002.pdf",
        "s002.pdf",
        "s003.pdf",
    ]


def test_sigterm_cancels_and_leaves_no_processes(harness: Harness) -> None:
    process = subprocess.Popen(
        harness.command(),
        env={**harness.env, "FAKE_MINERU_SLEEP": "60"},
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    pid_file = harness.state / "client.pid"
    deadline = time.monotonic() + 30
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert pid_file.exists(), "fake mineru client never started"
    client_pid = int(pid_file.read_text())
    process.send_signal(signal.SIGTERM)
    stdout, _ = process.communicate(timeout=30)
    assert process.returncode == 130
    failed = parse(stdout)[-1]
    assert failed["event"] == "failed" and failed["code"] == "cancelled"
    time.sleep(0.2)
    assert not alive(client_pid)
    assert not any(alive(pid) for pid in harness.server_pids())
    assert not (harness.state / "server-graceful.txt").exists()  # 取消时立即结束，不等待正常退出


def test_ai_without_configuration_fails_fast(harness: Harness) -> None:
    env = {"SCRIBEFLOW_AI_API_KEY": "", "OPENAI_API_KEY": "", "SCRIBEFLOW_AI_MODEL": "", "OPENAI_MODEL": ""}
    code, events, _ = harness.run("--ai", **env)
    assert code == 1
    assert events == [
        {"event": "failed", "code": "ai_config", "message": events[0]["message"], "resumable": False, "log": None}
    ]
    assert harness.client_calls() == []


def test_reprocess_command(harness: Harness) -> None:
    assert harness.run()[0] == 0
    completed = subprocess.run(
        [sys.executable, "-m", "scribeflow", "reprocess", str(harness.output), "--chapter-level", "2"],
        env=harness.env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "章节：2 个" in completed.stdout
