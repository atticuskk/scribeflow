#!/usr/bin/env python3
"""构建 ScribeFlow.app：SwiftUI 界面 + 独立 Python 3.12 运行时 + scribeflow[ocr]。

在仓库根目录运行（需要 macOS、完整 Xcode 和 uv）::

    uv run --frozen python packaging/build_app.py

产物写入 ``dist/ScribeFlow.app``；构建在暂存目录中完成，成功后才替换旧产物。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tomllib
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portable_runtime import copy_python, source_info, verify_links, write_notices

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
APP_NAME = "ScribeFlow.app"
EXECUTABLE = "ScribeFlow"
BUNDLE_ID = "io.github.scribeflow.app"


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, check=True, text=True, **kwargs)  # type: ignore[call-overload,no-any-return]


def project_version(pyproject: Path = ROOT / "pyproject.toml") -> str:
    return str(tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"])


def write_info_plist(template: Path, target: Path, *, version: str, build: str) -> dict[str, object]:
    info = plistlib.loads(template.read_bytes())
    info.update(
        {
            "CFBundleExecutable": EXECUTABLE,
            "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleShortVersionString": version,
            "CFBundleVersion": build,
        }
    )
    target.write_bytes(plistlib.dumps(info))
    return info


def check_environment(output_root: Path) -> None:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("只能在 Apple Silicon Mac 上构建应用。")
    applications = Path("/Applications")
    if output_root == applications or applications in output_root.parents:
        raise RuntimeError("构建输出不能位于 /Applications；请在 dist 中构建后手动安装。")
    developer_dir = os.environ.get("DEVELOPER_DIR") or run(["xcode-select", "-p"], capture_output=True).stdout.strip()
    if developer_dir.endswith("/CommandLineTools"):
        raise RuntimeError(
            "构建 SwiftUI 应用需要完整 Xcode（当前只有 CommandLineTools）。"
            "请安装 Xcode，或设置 DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer。"
        )
    if shutil.which("uv") is None:
        raise RuntimeError("需要 uv：https://docs.astral.sh/uv/")


def build_swift() -> Path:
    base = ["swift", "build", "-c", "release", "--arch", "arm64", "--package-path", str(ROOT / "app")]
    run([*base, "--product", EXECUTABLE])
    bin_dir = run([*base, "--show-bin-path"], capture_output=True).stdout.strip()
    return Path(bin_dir) / EXECUTABLE


def make_icon(source: Path, target: Path, work: Path) -> None:
    iconset = work / "AppIcon.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            run(
                [
                    "sips",
                    "-s",
                    "format",
                    "png",
                    "-z",
                    str(pixels),
                    str(pixels),
                    str(source),
                    "--out",
                    str(iconset / name),
                ],
                capture_output=True,
            )
    run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)])


def install_site_packages(python: Path, site_packages: Path, work: Path) -> None:
    """按 uv.lock 安装运行时依赖（含 MinerU），不包含开发工具。"""

    requirements = work / "requirements.txt"
    run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--extra",
            "ocr",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
        ],
        cwd=ROOT,
        capture_output=True,
    )
    common = ["uv", "pip", "install", "--python", str(python), "--target", str(site_packages), "--no-deps"]
    run([*common, "-r", str(requirements)])
    run([*common, str(ROOT)])
    for path in site_packages.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)


def smoke_test(python: Path, site_packages: Path) -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": str(site_packages), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONHOME", None)
    run([str(python), "-m", "scribeflow", "--version"], env=env)
    script = (
        "import importlib.metadata as m, json, sys;"
        "import mineru.cli.client, mineru.cli.fast_api;"
        "print(json.dumps({'python': sys.version.split()[0], 'mineru': m.version('mineru')}))"
    )
    versions: dict[str, str] = json.loads(run([str(python), "-c", script], env=env, capture_output=True).stdout)
    return versions


def build(output_root: Path, python_runtime: Path) -> Path:
    check_environment(output_root)
    version = project_version()
    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f".{APP_NAME}.staging-{uuid.uuid4().hex[:8]}"
    work = staging / "work"
    app = staging / APP_NAME
    contents = app / "Contents"
    resources = contents / "Resources"
    runtime = resources / "runtime"
    try:
        for directory in (work, contents / "MacOS", resources):
            directory.mkdir(parents=True)

        print("编译 SwiftUI 界面…", flush=True)
        shutil.copy2(build_swift(), contents / "MacOS" / EXECUTABLE)
        build_number = datetime.now().strftime("%Y%m%d%H%M")
        info = write_info_plist(PACKAGING / "Info.plist", contents / "Info.plist", version=version, build=build_number)
        make_icon(PACKAGING / "AppIcon-Source.png", resources / "AppIcon.icns", work)

        print("复制独立 Python 运行时…", flush=True)
        copy_python(python_runtime, runtime / "python")
        python = runtime / "python/bin/python3.12"

        print("安装 ScribeFlow 与 MinerU（约 1.3 GB）…", flush=True)
        install_site_packages(python, runtime / "site-packages", work)
        versions = smoke_test(python, runtime / "site-packages")

        write_notices(
            resources, runtime / "site-packages", ROOT / "THIRD_PARTY_NOTICES.md", PACKAGING / "ThirdPartyLicenses"
        )
        shutil.copy2(ROOT / "LICENSE", resources / "Licenses/ScribeFlow-LICENSE")
        build_info = {
            **source_info(ROOT),
            "version": version,
            "build": build_number,
            "bundle_id": BUNDLE_ID,
            "minimum_macos": info["LSMinimumSystemVersion"],
            "architecture": "arm64",
            **versions,
            "models_bundled": False,
            "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        (resources / "BuildInfo.json").write_text(
            json.dumps(build_info, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        verify_links(app)

        print("本地签名…", flush=True)
        run(["xattr", "-cr", str(app)])
        run(["codesign", "--force", "--deep", "--sign", "-", str(app)])
        run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])

        final = output_root / APP_NAME
        backup = output_root / f".{APP_NAME}.old-{uuid.uuid4().hex[:8]}"
        if final.exists():
            final.rename(backup)
        try:
            app.rename(final)
        except BaseException:
            if backup.exists():
                backup.rename(final)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        return final
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 ScribeFlow.app")
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="输出目录，默认 dist/")
    parser.add_argument(
        "--python-runtime",
        type=Path,
        default=Path(sys.base_prefix),
        help="独立 CPython 3.12 运行时目录（默认使用当前解释器的基础运行时，推荐 uv python install 3.12）",
    )
    args = parser.parse_args()
    try:
        result = build(args.output.resolve(), args.python_runtime.resolve())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    print(f"构建完成：{result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
