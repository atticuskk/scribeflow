"""ScribeFlow：扫描版 PDF 转章节 Markdown。"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("scribeflow")
except PackageNotFoundError:  # 以源码目录直接运行时
    __version__ = "0.0.0+source"
