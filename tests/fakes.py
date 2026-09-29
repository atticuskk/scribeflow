"""测试用的 MinerU 替身：按真实 content_list 格式写出结果。"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from types import TracebackType
from typing import Self

from pypdf import PdfWriter

from scribeflow.domain import Block
from scribeflow.ocr.engine import OcrSettings, SegmentJob
from scribeflow.ocr.mineru_format import find_content_list, load_blocks

FIXTURES = Path(__file__).parent / "fixtures"
BOOK_PAGES = FIXTURES / "book_pages.json"


def book_pages() -> list[list[dict[str, object]]]:
    return json.loads(BOOK_PAGES.read_text(encoding="utf-8"))


def make_pdf(path: Path, pages: int) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def write_mineru_output(
    pages: list[list[dict[str, object]]], first_page: int, page_count: int, output_dir: Path, stem: str
) -> None:
    """按 MinerU 的目录结构写出 content_list 和图片；伪造的 mineru 脚本也复用这段源码。"""
    import json
    from pathlib import Path

    result = Path(output_dir) / stem / "ocr"
    (result / "images").mkdir(parents=True, exist_ok=True)
    items = []
    for local, page in enumerate(pages[first_page : first_page + page_count]):
        for item in page:
            item = dict(item, page_idx=local)
            image = item.get("img_path")
            if isinstance(image, str) and image:
                (result / image).write_bytes(("image:" + image).encode())
            items.append(item)
    (result / f"{stem}_content_list.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


WRITER_SOURCE = "from __future__ import annotations\n" + inspect.getsource(write_mineru_output)


class FakeEngine:
    """进程内的 OCR 替身。``fail_once`` 中的分段第一次识别时抛出异常。"""

    def __init__(self, settings: OcrSettings, *, fail_once: set[int] | None = None) -> None:
        self.settings = settings
        self.fail_once = set(fail_once or ())
        self.calls: list[int] = []
        self.entered = 0

    def __call__(self, settings: OcrSettings) -> Self:
        self.settings = settings
        return self

    def __enter__(self) -> Self:
        self.entered += 1
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        pass

    def diagnostics(self) -> dict[str, str]:
        return {"引擎": "fake"}

    def recognize(self, job: SegmentJob) -> list[Block]:
        self.calls.append(job.index)
        if job.index in self.fail_once:
            self.fail_once.discard(job.index)
            raise RuntimeError(f"simulated failure in segment {job.index}")
        stem = job.pdf.stem
        write_mineru_output(book_pages(), job.first_page, job.page_count, job.output_dir, stem)
        return load_blocks(
            find_content_list(job.output_dir),
            id_prefix=stem,
            page_offset=job.first_page,
            assets_dir=job.assets_dir,
            asset_namespace=stem,
        )


FAKE_CLIENT = (
    WRITER_SOURCE
    + r"""
import argparse, json, os, sys, time, urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("-p"); parser.add_argument("-o"); parser.add_argument("-b"); parser.add_argument("-m")
parser.add_argument("-l"); parser.add_argument("--api-url")
args = parser.parse_args()
state = Path(os.environ["FAKE_MINERU_STATE"])
with (state / "client-calls.jsonl").open("a") as log:
    log.write(json.dumps({"pdf": args.p, "api_url": args.api_url, "pid": os.getpid(),
                          "timeout": os.environ.get("MINERU_TASK_RESULT_TIMEOUT_SECONDS"),
                          "model_source": os.environ.get("MINERU_MODEL_SOURCE")}) + "\n")
print("fake mineru client starting", flush=True)
if args.api_url:
    try:
        urllib.request.urlopen(args.api_url + "/health", timeout=5).read()
    except Exception as exc:
        print(f"Failed to query task status for {args.p}: {exc}", flush=True)
        sys.exit(3)
stem = Path(args.p).stem
index = int(stem[1:])
kill_marker = state / f"killed-{index}"
if os.environ.get("FAKE_MINERU_KILL_SERVER") == str(index) and not kill_marker.exists():
    import signal
    kill_marker.write_text("x")
    server_pid = int((state / "server-starts.txt").read_text().split()[-1])
    os.killpg(server_pid, signal.SIGKILL)
    print(f"Failed to query task status for {args.p}: 502 Bad Gateway", flush=True)
    sys.exit(3)
sleep = float(os.environ.get("FAKE_MINERU_SLEEP", "0"))
if sleep:
    (state / "client.pid").write_text(str(os.getpid()))
    time.sleep(sleep)
fail_marker = state / f"failed-{index}"
if os.environ.get("FAKE_MINERU_FAIL") == str(index) and not fail_marker.exists():
    fail_marker.write_text("x")
    print("simulated OCR crash", flush=True)
    sys.exit(2)
pages = json.loads(Path(os.environ["FAKE_MINERU_PAGES"]).read_text(encoding="utf-8"))
size = int(os.environ["FAKE_MINERU_SEGMENT_PAGES"])
first = (index - 1) * size
write_mineru_output(pages, first, min(size, len(pages) - first), args.o, stem)
print("fake mineru client done", flush=True)
"""
)

FAKE_SERVER = r"""
import argparse, json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--host"); parser.add_argument("--port", type=int)
args = parser.parse_args()
state = Path(os.environ["FAKE_MINERU_STATE"])
with (state / "server-starts.txt").open("a") as log:
    log.write(f"{os.getpid()}\n")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "healthy", "version": "fake"}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

print("fake mineru-api listening", flush=True)
HTTPServer((args.host, args.port), Handler).serve_forever()
"""


def install_fake_mineru(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, source in (("mineru", FAKE_CLIENT), ("mineru-api", FAKE_SERVER)):
        script = directory / name
        script.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
        script.chmod(0o755)
    return directory / "mineru"
