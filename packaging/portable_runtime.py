"""复制可迁移的 CPython 运行时，并收集依赖包自带的许可证文件。"""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

IGNORED_NAMES = {"__pycache__", ".DS_Store", "_virtualenv.pth", "_virtualenv.py", "direct_url.json"}
LICENSE_WORDS = ("license", "licence", "copying", "copyright", "notice")


def copy_ignore(directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in IGNORED_NAMES or name.endswith((".pyc", ".pyo")) or name.startswith(("_editable", "__editable__"))
    }


def verify_links(root: Path) -> None:
    """应用包必须能整体移动：符号链接只能是指向包内、真实存在的相对链接。"""

    resolved = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink() and (
            os.path.isabs(os.readlink(path)) or not path.exists() or not path.resolve().is_relative_to(resolved)
        ):
            raise RuntimeError(f"Non-portable or broken symlink: {path.relative_to(root)}")


def copy_python(source: Path, target: Path) -> None:
    if not (source / "bin/python3.12").is_file():
        raise RuntimeError("A standalone CPython 3.12 runtime is required")
    shutil.copytree(source, target, symlinks=True, ignore=copy_ignore)
    # bin/ 里的其他脚本带有指向构建机器的 shebang；应用只需要解释器本身。
    for path in (target / "bin").iterdir():
        if path.name not in {"python", "python3", "python3.12"}:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    verify_links(target)


def write_notices(resources: Path, site_packages: Path, notice: Path, supplemental: Path) -> None:
    destination = resources / "Licenses"
    destination.mkdir()
    shutil.copy2(notice, destination / "THIRD_PARTY_NOTICES.md")
    shutil.copy2(resources / "runtime/python/lib/python3.12/LICENSE.txt", destination / "Python-LICENSE.txt")
    if supplemental.is_dir():
        shutil.copytree(supplemental, destination / "Supplemental")
    index: list[dict[str, Any]] = []
    distributions = importlib.metadata.distributions(path=[str(site_packages)])
    for dist in sorted(distributions, key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        copied: list[str] = []
        for file in dist.files or ():
            if not any(word in str(file).lower() for word in LICENSE_WORDS):
                continue
            original = Path(str(dist.locate_file(file)))
            if not original.is_file() or not original.resolve().is_relative_to(site_packages.resolve()):
                continue
            target = destination / name / original.relative_to(site_packages)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            copied.append(str(target.relative_to(resources)))
        extra = destination / "Supplemental" / name
        if extra.is_dir():
            copied.extend(str(p.relative_to(resources)) for p in extra.rglob("*") if p.is_file())
        license_name = dist.metadata.get("License-Expression") or dist.metadata.get("License", "")
        index.append({"name": name, "version": dist.version, "license": license_name, "files": copied})
    (destination / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")


def source_info(root: Path) -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    return {
        "source_commit": git("rev-parse", "HEAD"),
        "source_dirty": bool(git("status", "--porcelain", "--untracked-files=normal")),
    }
