# ScribeFlow 本机项目交接

交接日期：2026-10-03（Asia/Shanghai），同日与 GitHub 同步后更新。接管目录：`/Users/luliss/Documents/scribeflow`。

## 1. 当前状态与本次工作

- 版本：ScribeFlow 0.2.0；Python 包、CLI、应用名和 Bundle ID 均未改名。
- 分支：`main`，跟踪 `origin/main`。
- HEAD：`0a5457a`（Merge pull request #1），与 `origin/main` 一致。功能分支 `claude/gracious-wright-tz4g7i`（`1c9d9ac`）已合并，本地保留并跟踪 `origin/claude/gracious-wright-tz4g7i`。
- remote：只保留 `origin` = `https://github.com/atticuskk/scribeflow.git`。原 `jasperfarmer6-maker/scribeflow` 已被 GitHub 永久重定向到该仓库，与原 `atticus` remote 是同一仓库，已合并为一个。

### 与 GitHub 同步（2026-10-03）

- 同步前本地停在 `03cae80`，比远端少 2 个提交、无本地独有提交，按快进方式更新：
  - `1c9d9ac` fix(ocr)：MinerU 服务主进程被杀后，仍清理整个进程组（resource_tracker、spawn worker 等），避免残留子进程。
  - `0a5457a` 将 PR #1 合并进 `main`。
- 本地 `main` 原停在 `441c425`（0.1.x 时代），已一并快进到 `0a5457a`。
- 删除了只剩 `__pycache__` 的旧目录 `macos/`、`src/pdf_to_md/`（均为 0.1.x 残留、被 git 忽略）。

### 迁移（交接前完成）

- 原实际项目目录 `/Users/luliss/Documents/Codex/scribeflow` 已整体迁移到接管目录。即时比对 95,444 个文件、目录及链接，普通文件 SHA-256、链接目标和清单完全一致。
- 迁移后按 `uv.lock` 使用 `uv sync --frozen --extra ocr` 重建 `.venv`（Python 3.12.14，MinerU 3.4.4），修复入口脚本和 editable 安装的旧路径。验证后删除旧环境备份。
- Swift 使用 `swift package clean` 清理旧路径缓存后重新编译测试。源码、Git 历史、samples、output、dist 均保留。
- 原聊天目录 `/Users/luliss/Documents/ChatGPT/PDF转md` 是空目录，并非代码所在地；本次在确认仍为空后移除。旧聊天/工具若仍绑定旧目录，应重新打开本项目，不应据旧目录缺失推断源码丢失。

## 2. 产品与已实现功能

面向扫描版 PDF 的本地 OCR 工具，将内容清洗并拆分为章节 Markdown。支持 SwiftUI 桌面应用和命令行。

- MinerU pipeline OCR，默认中文、ModelScope 模型源、每 16 页一段顺序识别。
- 整本书复用一个 MinerU 服务和模型；支持分段检查点、续跑、服务崩溃重试和取消。
- 确定性清洗、可选 AI 块级清洗、操作校验和审计、标题层级及章节拆分。
- `reprocess` 复用已保存 OCR 块重新生成，不重新 OCR。
- 输出 `document.md`、`chapters/`、`assets/` 和 `.scribeflow/` 元数据；发布采用暂存目录和替换恢复机制。
- AI 默认关闭；密钥使用钥匙串或环境变量，交接不包含密钥。

以上依据现有源码与项目文档；本轮测试覆盖情况见后文，不代表真实大文件 OCR 已再次验收。0.2.0 与 0.1.x 的包名、命令和输出结构不兼容，详见 CHANGELOG.md。

## 3. 架构与阅读顺序

先读本文件，再读 README.md、docs/architecture.md、CHANGELOG.md、INSTALL.md。

- `app/Sources/ScribeFlow`：SwiftUI 界面和 AppModel；`ScribeFlowCore`：后端进程、JSONL 事件、进度状态和运行时定位。
- `src/scribeflow/cli.py` → `converter.py`：转换与重新生成入口、阶段编排、发布。
- `ocr/`：MinerU 服务、客户端及内容块适配；`workspace.py`：分段状态与续跑。
- `domain.py` 中 Block 是统一表示；`cleaning/` 只允许 Drop、Merge、SetLevel，经统一校验后执行，禁止改写正文。
- `structure.py`、`render.py`：章节结构和 Markdown 输出。
- `tests/`、`app/Tests/`：Python 与 Swift 测试；两侧共享事件协议样例。
- `packaging/build_app.py`：独立 Python 运行时、锁定依赖、许可证、签名与构建信息。

当前入口为 `src/scribeflow`；0.1.x 的 `src/pdf_to_md`、`macos/` 已从仓库和本机移除。

## 4. 新路径下的常用命令

```bash
cd /Users/luliss/Documents/scribeflow
uv sync --frozen --extra ocr
.venv/bin/python -m scribeflow --version
.venv/bin/python -m scribeflow convert /绝对路径/输入.pdf -o /绝对路径/输出目录
.venv/bin/python -m scribeflow reprocess /绝对路径/输出目录 --chapter-level 2
```

验证（直接调用虚拟环境工具，避免普通 uv run 同步时移除未指定的 OCR extra）：

```bash
cd /Users/luliss/Documents/scribeflow
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
cd app
swift test
```

开发启动桌面界面：

```bash
cd /Users/luliss/Documents/scribeflow/app
SCRIBEFLOW_PYTHON=/Users/luliss/Documents/scribeflow/.venv/bin/python swift run ScribeFlow
```

构建与现有应用：

```bash
cd /Users/luliss/Documents/scribeflow
uv run --frozen --extra ocr python packaging/build_app.py
open /Users/luliss/Documents/scribeflow/dist/ScribeFlow.app
```

完整 Xcode 推荐但非绝对前置条件，构建脚本可尝试 Command Line Tools。不要直接改已签名应用包。首次真实 OCR 可能下载模型，用户目录中的模型缓存没有随项目移动或删除。

## 5. 实际验收

### 交接时（HEAD `03cae80`，迁移后）

| 检查 | 结果 |
|---|---|
| 完整迁移即时清单与内容校验 | 95,444 项一致 |
| CLI 版本和帮助 | 正常，scribeflow 0.2.0 |
| pytest | 58 passed，15.51 秒 |
| ruff check | All checks passed |
| ruff format --check | 47 files already formatted |
| mypy | 22 个源文件无问题 |
| Swift 清理后编译及测试 | 编译成功，13 tests passed |
| 现有 dist 应用签名 | codesign --verify --deep --strict 通过 |
| 现有应用启动冒烟 | 直接启动可执行文件后存活 8 秒，无 stdout/stderr 错误，然后关闭本次验证进程 |

### 同步后（HEAD `0a5457a`）

| 检查 | 结果 |
|---|---|
| pytest | 58 passed，15.67 秒 |
| ruff check | All checks passed |
| ruff format --check | 48 files already formatted |
| mypy | 22 个源文件无问题 |
| Swift 测试 | 13 tests passed |

同步后未重新做 dist 签名校验和启动冒烟（dist 未变）。启动冒烟只验证进程未提前退出，未人工验证窗口交互或执行真实 OCR。Python 端到端测试使用伪造 MinerU，不能替代真实模型压力测试。

现有 dist 应用 BuildInfo：0.2.0、build 202609300552、源码提交 `03cae80`、arm64、最低 macOS 15.0、内置 Python 3.12.14、MinerU 3.4.4；模型未打包。**dist 应用早于 `1c9d9ac`，不含进程组清理修复，也不含之后的优化（见 CHANGELOG“未发布”）**；需要时运行 `packaging/build_app.py` 重建。

## 6. 待办：卡顿和高内存（用户决定暂缓）

用户已反馈 PDF 转 Markdown 工具卡顿且内存占用高。尚未取得复现 PDF、页数、文件大小、最卡阶段及峰值内存数据，尚未定位原因或实施性能优化。已有分段和模型复用不能证明问题已解决。

**2026-10-03 用户决定暂不排查**：真实 OCR 复现会占用大量本机内存、影响其他任务。在用户明确要求前，不要运行真实 MinerU 转换、压力测试或其他高内存排查。

`1c9d9ac` 修复了 MinerU 主进程被杀后子进程残留的问题，可能与"内存占用高"有关，但未经真实运行验证，不能视为已解决；且现有 dist 应用不含此修复。

恢复排查时的建议：
1. 确认实际使用的是此版本/此应用（dist 需先用当前源码重建），取得可复现文件和操作步骤。
2. 分别记录 GUI、Python 主进程、MinerU 服务及子进程的耗时和峰值内存；比较准备、OCR、清洗、渲染阶段。
3. 检查分段页数、模型常驻成本、图像缓冲及缓存、全部 Block 合并、事件/日志更新频率；这些仅为调查方向。
4. 测试完成、取消和失败后的进程释放与断点续跑，不以强制关闭服务掩盖泄漏。
5. 在同一输入和配置下比较优化前后性能，并保持 Markdown、审计和正文保真约束。

## 7. 给接管模型的指令

请以 `/Users/luliss/Documents/scribeflow` 为工作目录，先阅读 HANDOFF.md 和架构文档，检查 Git 状态。迁移已经完成，不要再次改名或搬迁；保留本交接文档。性能排查已由用户暂缓，未经要求不要运行高内存任务。不要把历史文档中的功能描述等同于真实 OCR 验收，不要将未运行的检查记为通过。本文件已纳入版本控制，状态变化时请同步更新。
