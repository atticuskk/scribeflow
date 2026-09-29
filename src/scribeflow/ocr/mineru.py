"""MinerU 适配器。

默认先启动一个常驻的 ``mineru-api`` 服务，再让每个分段的 ``mineru`` 客户端通过
``--api-url`` 连接它，这样整本书只加载一次模型。服务意外退出时会自动重启并重试该分段一次。
``shared_server=False`` 时退回旧方式：每个分段由 ``mineru`` 自行启动临时服务。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Self

from scribeflow.domain import Block
from scribeflow.errors import ErrorCode, OcrError
from scribeflow.ocr.engine import OcrSettings, SegmentJob
from scribeflow.ocr.mineru_format import find_content_list, load_blocks
from scribeflow.ocr.process import popen_group, pump_output, run_streaming, terminate_group

logger = logging.getLogger(__name__)

CLIENT_MODULE = "mineru.cli.client"
SERVER_MODULE = "mineru.cli.fast_api"
TIMEOUT_ENV = "MINERU_TASK_RESULT_TIMEOUT_SECONDS"


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def resolve_commands(explicit: Path | None) -> tuple[list[str], list[str]]:
    """返回 (客户端命令, 服务端命令)。优先显式路径，其次当前解释器可导入的模块，最后 PATH。"""

    if explicit is not None:
        if not (explicit.is_file() and os.access(explicit, os.X_OK)):
            raise OcrError(f"指定的 MinerU 程序不可执行：{explicit}", code=ErrorCode.OCR_UNAVAILABLE)
        server = explicit.with_name("mineru-api")
        return [str(explicit)], [str(server)] if server.is_file() else [sys.executable, "-m", SERVER_MODULE]
    if _module_available(CLIENT_MODULE):
        return [sys.executable, "-m", CLIENT_MODULE], [sys.executable, "-m", SERVER_MODULE]
    client_path, server_path = shutil.which("mineru"), shutil.which("mineru-api")
    if client_path and server_path:
        return [client_path], [server_path]
    raise OcrError(
        "找不到 MinerU。请安装 scribeflow[ocr]，或用 --mineru 指定 mineru 程序路径。", code=ErrorCode.OCR_UNAVAILABLE
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class MinerUServer:
    """一个常驻的 mineru-api 进程。"""

    def __init__(self, command: list[str], env: dict[str, str], *, startup_timeout: float = 600.0) -> None:
        self._command = command
        self._env = env
        self._startup_timeout = startup_timeout
        self._process: subprocess.Popen[str] | None = None
        self._output_root: tempfile.TemporaryDirectory[str] | None = None
        self.url = ""

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        self.stop()
        port = _free_port()
        self.url = f"http://127.0.0.1:{port}"
        self._output_root = tempfile.TemporaryDirectory(prefix="scribeflow-mineru-api-")
        env = {
            **self._env,
            "MINERU_API_OUTPUT_ROOT": self._output_root.name,
            "MINERU_API_DISABLE_ACCESS_LOG": "1",
        }
        logger.info("启动 MinerU 服务：%s", self.url)
        self._process = popen_group([*self._command, "--host", "127.0.0.1", "--port", str(port)], env=env)
        pump_output(self._process, logging.getLogger("scribeflow.mineru"), "MinerU 服务")
        self._wait_until_healthy()

    def _wait_until_healthy(self) -> None:
        deadline = time.monotonic() + self._startup_timeout
        last_error = ""
        while time.monotonic() < deadline:
            if not self.running:
                raise OcrError("MinerU 服务启动失败，详情见日志。", code=ErrorCode.OCR_SERVER)
            try:
                with urllib.request.urlopen(f"{self.url}/health", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if payload.get("status") == "healthy":
                        logger.info("MinerU 服务就绪（版本 %s）", payload.get("version", "未知"))
                        return
            except (OSError, urllib.error.URLError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(1.0)
        raise OcrError(f"等待 MinerU 服务就绪超时：{last_error}", code=ErrorCode.OCR_SERVER)

    def stop(self) -> None:
        if self._process is not None:
            terminate_group(self._process)
            self._process = None
        if self._output_root is not None:
            self._output_root.cleanup()
            self._output_root = None


class MinerUEngine:
    def __init__(self, settings: OcrSettings) -> None:
        self.settings = settings
        self._client: list[str] = []
        self._server: MinerUServer | None = None
        self._env: dict[str, str] = {}

    def __enter__(self) -> Self:
        self._client, server_command = resolve_commands(self.settings.mineru)
        self._env = {**os.environ, "MINERU_MODEL_SOURCE": self.settings.model_source}
        if self.settings.shared_server:
            self._server = MinerUServer(server_command, self._env)
            try:
                self._server.start()
            except BaseException:
                self._server.stop()
                raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._server is not None:
            self._server.stop()

    def diagnostics(self) -> dict[str, str]:
        return {
            "引擎": "MinerU",
            "客户端命令": " ".join(self._client),
            "服务": self._server.url if self._server else "每段临时启动",
            "backend": self.settings.backend,
            "method": self.settings.method,
            "language": self.settings.language,
            "模型源": self.settings.model_source,
            "模型缓存": _model_cache_hint(self.settings.model_source),
            "Python": sys.executable,
        }

    def recognize(self, job: SegmentJob) -> list[Block]:
        try:
            self._run_client(job)
        except OcrError as exc:
            if self._server is None or (self._server.running and exc.code is not ErrorCode.OCR_SERVER):
                raise
            logger.warning("MinerU 服务异常（%s），重启后重试第 %d 段", exc, job.index)
            self._server.start()
            self._run_client(job)
        content_list = find_content_list(job.output_dir)
        return load_blocks(
            content_list,
            id_prefix=f"s{job.index:03d}",
            page_offset=job.first_page,
            assets_dir=job.assets_dir,
            asset_namespace=f"s{job.index:03d}",
        )

    def _run_client(self, job: SegmentJob) -> None:
        if job.output_dir.exists():
            shutil.rmtree(job.output_dir)
        job.output_dir.mkdir(parents=True)
        command = [
            *self._client,
            "-p",
            str(job.pdf),
            "-o",
            str(job.output_dir),
            "-b",
            self.settings.backend,
            "-m",
            self.settings.method,
            "-l",
            self.settings.language,
        ]
        if self._server is not None:
            command += ["--api-url", self._server.url]
        env = dict(self._env)
        if TIMEOUT_ENV not in os.environ:
            timeout = self.settings.task_timeout_seconds or max(3600, 300 * job.page_count)
            env[TIMEOUT_ENV] = str(timeout)

        flags = {"timeout": False, "server": False}

        def classify(line: str) -> None:
            if "Timed out waiting for result of task" in line:
                flags["timeout"] = True
            if "Failed to query task status" in line or "Local mineru-api exited" in line:
                flags["server"] = True

        result = run_streaming(
            command, env=env, logger=logging.getLogger("scribeflow.mineru"), prefix="MinerU", on_line=classify
        )
        if result.returncode == 0:
            return
        if flags["timeout"]:
            raise OcrError(f"第 {job.index} 段 OCR 超时（{env.get(TIMEOUT_ENV)} 秒）。", code=ErrorCode.OCR_TIMEOUT)
        if flags["server"] or (self._server is not None and not self._server.running):
            raise OcrError("MinerU 服务不可用，通常与内存不足有关。", code=ErrorCode.OCR_SERVER)
        detail = result.tail[-1] if result.tail else "无输出"
        raise OcrError(f"第 {job.index} 段 OCR 失败（退出码 {result.returncode}）：{detail}")


def _model_cache_hint(model_source: str) -> str:
    home = Path.home()
    candidates = {
        "modelscope": [home / ".cache/modelscope/hub", home / ".cache/modelscope"],
        "huggingface": [home / ".cache/huggingface/hub"],
    }.get(model_source, [])
    for path in candidates:
        if path.exists():
            return str(path)
    return "未找到（首次运行会下载）" if candidates else "由 MinerU 配置决定"
