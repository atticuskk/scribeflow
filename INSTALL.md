# 安装与构建

## 系统要求

- Apple Silicon（M 系列）Mac，macOS 15.0 或更高（打包的依赖要求 15.0）。
- 首次转换需要联网下载 OCR 模型（默认从 ModelScope），模型缓存在当前用户目录；建议预留至少 10 GB 空间。
- 可选的 AI 清洗需要一个 OpenAI 兼容服务。

## 安装预构建应用

1. 从仓库的 Releases 下载应用 ZIP 和 `SHA256SUMS.txt`。
2. 在下载目录运行 `shasum -a 256 -c SHA256SUMS.txt`，确认显示 `OK`。
3. 解压，把 `ScribeFlow.app` 拖到“应用程序”。
4. 应用使用本地 ad-hoc 签名，没有经过 Apple 公证。首次打开若被拦截，到“系统设置 → 隐私与安全性”选择“仍要打开”。不要关闭系统安全检查。

不要修改应用包内的文件，否则签名会失效。应用改名或放在含空格、中文的路径下不影响运行。

### 从 0.1.x 升级

0.2.0 的 Bundle ID 已变化，会作为一个新应用出现：

- 在“设置 → AI 清洗”中重新填写 API 密钥（旧密钥仍在钥匙串的 `com.local.PDFToMarkdown` 条目中，可手动删除）。
- 旧版生成的输出目录可以用“替换已有结果”覆盖，但不能用“重新生成”（旧版没有保存 OCR 块）。
- 旧版未完成任务的 `.failed-*` / `.staging-*` 目录不会被续跑，可以手动删除。

## 从源码构建

推荐安装完整 Xcode；只有 Command Line Tools 时脚本会给出警告并尝试编译，失败再安装 Xcode。另外需要 [uv](https://docs.astral.sh/uv/getting-started/installation/)：

```bash
git clone https://github.com/atticuskk/scribeflow.git
cd scribeflow
uv python install 3.12
uv sync --frozen
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer uv run --frozen python packaging/build_app.py
```

构建脚本会：

1. 用 SwiftPM 编译界面；
2. 复制 uv 提供的独立 CPython 3.12 运行时（可用 `--python-runtime` 指定）；
3. 按 `uv.lock` 安装 `scribeflow[ocr]` 及其依赖（不含开发工具），并用内置 Python 做一次启动检查；
4. 收集依赖许可证，写入 `BuildInfo.json`（源码提交、版本、MinerU 版本）；
5. ad-hoc 签名，最后把 `dist/ScribeFlow.app` 整体替换。

构建不会触碰 `/Applications`，也不允许把输出目录设在那里。

## 只用命令行

```bash
uv sync --frozen --extra ocr
uv run scribeflow convert 输入.pdf -o 输出目录
```
