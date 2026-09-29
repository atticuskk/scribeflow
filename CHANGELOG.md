# 变更记录

## 0.2.0

整体重构。与 0.1.x 不兼容：包名、命令、环境变量、输出目录结构、应用 Bundle ID 都已变化。

**后端**
- 包名 `pdf_to_md` → `scribeflow`；`pdf2md` 和 `gui_backend` 合并为 `scribeflow convert` / `scribeflow reprocess`。
- 新增 `reprocess`：复用已有 OCR 结果重新清洗和生成 Markdown。
- 整本书只启动一个 MinerU 服务并复用模型；服务崩溃时自动重启并重试该分段；正常结束时按 MinerU 的方式关闭服务，取消时连同 MinerU 进程一起结束。
- 续跑改为自动：同一输出位置的未完成任务再次转换即继续；`--fresh` 重新开始。
- 清洗统一为块级操作 + 校验 + 审计；审计中记录被拒绝的操作。
- 新规则：合并被分页截断的中文句子（可关闭）；英文续行可连续合并多行。
- 修复：公式被重复包裹 `$$`；图表、代码块、参考文献列表、图片/表格脚注丢失；空白页导致整次转换失败（现在只给出警告）。
- `--overwrite` 只会替换 ScribeFlow 生成的目录。
- AI 响应按内容缓存，失败后续跑或重新生成不重复请求。
- 环境变量改为 `SCRIBEFLOW_AI_MODEL` / `SCRIBEFLOW_AI_API_KEY` / `SCRIBEFLOW_AI_BASE_URL`（仍兼容 `OPENAI_*`）；不再读取 `.env`。
- MinerU 移到可选依赖 `scribeflow[ocr]`。

**桌面应用**
- 改为 SwiftPM 包，核心逻辑独立成 `ScribeFlowCore` 并有单元测试。
- 新增设置窗口、按错误类型给出恢复操作、一键重新生成、完成后的空白页警告。
- 输出位置默认为 PDF 所在文件夹。
- Bundle ID 改为 `io.github.scribeflow.app`，可执行文件改为 `ScribeFlow`；API 密钥需要在设置中重新填写一次。

**工程**
- pytest（含伪造 MinerU 的端到端测试）、ruff、mypy --strict、GitHub Actions（Python + macOS）；Swift 测试使用 swift-testing，无需完整 Xcode。
- 打包脚本按 `uv.lock` 安装运行时依赖，不再复制开发用 `.venv`；版本号只来自 `pyproject.toml`。
- 文档精简为 README、INSTALL、docs/architecture.md 和本文件。

## 0.1.x

初始版本：MinerU 分段 OCR、确定性清洗、可选 AI 清洗、SwiftUI 桌面应用。
