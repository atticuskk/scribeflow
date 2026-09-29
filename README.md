# ScribeFlow

把**扫描版 PDF** 转成**按章节拆分的 Markdown**。OCR 在本机用 [MinerU](https://github.com/opendatalab/MinerU) 完成，随后的清洗只做“删除 / 合并 / 调整标题层级”三类块级操作，**不改写正文**，每一处改动都有审计记录。

- macOS 桌面应用（Apple Silicon）：拖入 PDF → 开始转换 → 得到章节 Markdown
- 命令行：`scribeflow convert` / `scribeflow reprocess`
- 适合四五百页的厚书：分段 OCR、断点续跑、整本书只加载一次模型

## 功能

| | |
|---|---|
| OCR | MinerU `pipeline` 后端，默认中文、ModelScope 模型源；每 16 页一段顺序识别 |
| 续跑 | 每段完成即保存；失败或停止后再次转换同一个输出位置会自动跳过已完成分段 |
| 清洗规则 | 删除页眉页脚页码、独立页码、短广告；合并英文断词、被分页截断的中文句子 |
| AI 清洗（可选，默认关闭） | OpenAI 兼容接口；只能提议块级操作，程序逐条校验后执行 |
| 重新生成 | 换章节层级、开关规则或 AI 后，复用已有 OCR 结果几秒内重新生成 |
| 输出 | 完整文档、章节文件、图片，以及 manifest / 审计 / OCR 块 / 日志 |

## 使用桌面应用

1. 把 PDF 拖进窗口（输出位置默认是 PDF 所在文件夹，可更改）。
2. 选择章节切分方式，点击“开始转换”。
3. 完成后可直接打开文件夹或完整文档；想换一种章节切分，调整后点“按当前选项重新生成”。

失败时窗口会给出对应操作：继续转换、替换已有结果、放弃旧进度重新开始。OCR 语言、每段页数、模型源、AI 服务和开发者诊断在“设置”（⌘,）里。

安装预构建应用或从源码构建，见 [INSTALL.md](INSTALL.md)。

## 命令行

```bash
uv sync --extra ocr                      # 安装 ScribeFlow 与 MinerU
uv run scribeflow convert 书.pdf -o 书-Markdown
uv run scribeflow reprocess 书-Markdown --chapter-level 2
```

常用参数：

| 参数 | 作用 |
|---|---|
| `--segment-pages N` | 每段页数，默认 16 |
| `--overwrite` | 替换 ScribeFlow 之前生成的同名输出（不会替换其他目录） |
| `--fresh` | 放弃该输出位置的未完成任务，重新开始 |
| `--chapter-level 1-6` | 在第几级标题处切分章节，默认自动 |
| `--no-cross-page-merge` | 不合并分页截断的中文句子 |
| `--ai --ai-model M [--ai-base-url URL]` | 启用 AI 清洗；密钥来自 `SCRIBEFLOW_AI_API_KEY` 或 `OPENAI_API_KEY` |
| `--lang` / `--model-source` / `--method` / `--backend` | 传给 MinerU |
| `--no-shared-server` | 每段单独启动 MinerU（旧方式，较慢） |
| `--events jsonl` | 向 stdout 输出 JSON Lines 进度事件（桌面应用使用） |

`MINERU_TASK_RESULT_TIMEOUT_SECONDS`、`MINERU_PROCESSING_WINDOW_SIZE` 等 MinerU 环境变量会原样传递。

## 输出结构

```text
书-Markdown/
├── document.md            完整文档
├── chapters/              001-第一章-总则.md …
├── assets/                图片（按 OCR 分段分目录）
└── .scribeflow/
    ├── manifest.json      输入、参数、章节、统计、警告
    ├── audit.json         每一项删除/合并/层级调整，以及被拒绝的操作
    ├── blocks.jsonl       OCR 得到的全部内容块（重新生成的依据）
    ├── logs/              每次转换、重新生成的日志
    └── ocr/               MinerU 原始结果（可在设置中关闭）
```

转换过程中，进度保存在输出位置旁边的 `.<输出名>.scribeflow-work/`，成功发布后自动删除。

## 保真与隐私

- 正文只来自 OCR 内容块；规则和 AI 都没有“替换文本”的能力。
- AI 默认关闭。开启后，内容块会发送到你配置的服务，请只处理你有权发送的内容。
- API 密钥在应用中保存于钥匙串，在命令行中只从环境变量读取；不会写入日志、事件或 manifest。
- 本工具不授予你处理任何第三方 PDF 的权利。基于 MinerU 对外提供服务时，请遵守 MinerU 许可证的标注要求。

## 开发

架构、事件协议和测试方式见 [docs/architecture.md](docs/architecture.md)，变更记录见 [CHANGELOG.md](CHANGELOG.md)。

```bash
uv sync                    # 开发环境（不含 MinerU）
uv run pytest              # 包括用伪造 MinerU 的端到端测试
uv run ruff check . && uv run mypy
cd app && swift test       # macOS 应用核心逻辑
```

## 许可

MIT，见 [LICENSE](LICENSE)。依赖许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
