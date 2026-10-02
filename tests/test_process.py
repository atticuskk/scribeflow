from __future__ import annotations

from scribeflow.ocr.process import ProgressFilter


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def bar(label: str, done: int, total: int) -> str:
    return f"{label}: {100 * done // total:3d}%|{'█' * (10 * done // total):10}| {done}/{total} [00:01<00:02, 9.9it/s]"


def test_keeps_first_periodic_and_final_progress_lines() -> None:
    clock = Clock()
    progress = ProgressFilter(interval=10, clock=clock)
    kept = []
    for done in range(101):
        clock.now = done * 0.2  # 20 秒内重绘 100 次
        line = bar("OCR-rec Predict", done, 100)
        if progress.keep(line):
            kept.append(line)
    assert progress.keep(bar("OCR-rec Predict", 100, 100)) is False  # 结束时重复的最后一行
    assert [line.split("|")[0] for line in kept] == [
        "OCR-rec Predict:   0%",
        "OCR-rec Predict:  50%",
        "OCR-rec Predict: 100%",
    ]


def test_progress_bars_are_tracked_separately() -> None:
    progress = ProgressFilter(interval=10, clock=Clock())
    assert progress.keep(bar("Layout Predict", 0, 4))
    assert progress.keep(bar("OCR-det ch", 0, 4))
    assert not progress.keep(bar("Layout Predict", 1, 4))
    assert progress.keep(bar("Layout Predict", 4, 4))


def test_other_output_is_never_dropped() -> None:
    progress = ProgressFilter(clock=Clock())
    for line in ["Failed to query task status", "Failed to query task status", "处理 50% 的页面"]:
        assert progress.keep(line)
