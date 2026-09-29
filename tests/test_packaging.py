from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

from build_app import project_version, write_info_plist  # noqa: E402
from portable_runtime import copy_ignore, verify_links  # noqa: E402


def test_relative_links_survive_relocation(tmp_path: Path) -> None:
    root = tmp_path / "迁移 空格" / "Bundle"
    root.mkdir(parents=True)
    (root / "python3.12").write_text("test")
    (root / "python").symlink_to("python3.12")
    moved = root.with_name("移动 App")
    root.rename(moved)
    verify_links(moved)
    assert (moved / "python").read_text() == "test"


@pytest.mark.parametrize("target", ["/usr/bin/python3", "../external-python", "missing-python"])
def test_absolute_external_and_broken_links_rejected(tmp_path: Path, target: str) -> None:
    (tmp_path / "python").symlink_to(target)
    with pytest.raises(RuntimeError):
        verify_links(tmp_path)


def test_private_install_metadata_and_editable_paths_excluded() -> None:
    names = ["direct_url.json", "_editable_impl_x.pth", "__editable__.x.pth", "__pycache__", "a.pyc", "LICENSE", "m.py"]
    assert set(names) - copy_ignore("/unused", names) == {"LICENSE", "m.py"}


def test_info_plist_gets_version_from_pyproject(tmp_path: Path) -> None:
    info = write_info_plist(
        ROOT / "packaging/Info.plist", tmp_path / "Info.plist", version=project_version(), build="7"
    )
    written = plistlib.loads((tmp_path / "Info.plist").read_bytes())
    assert written == info
    assert written["CFBundleShortVersionString"] == project_version()
    assert (written["CFBundleExecutable"], written["CFBundleVersion"]) == ("ScribeFlow", "7")
