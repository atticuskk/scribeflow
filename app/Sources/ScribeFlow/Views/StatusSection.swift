import ScribeFlowCore
import SwiftUI

struct StatusSection: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        switch model.progress.phase {
        case .idle:
            EmptyView()
        case .running, .cancelling:
            RunningView(progress: model.progress)
        case let .succeeded(result):
            SuccessView(result: result)
        case let .failed(failure):
            FailureView(failure: failure)
        }
    }
}

private struct RunningView: View {
    let progress: ConversionProgress

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                if let fraction = progress.fraction {
                    ProgressView(value: fraction)
                } else {
                    ProgressView().progressViewStyle(.linear)
                }
                Text(progress.message).font(.headline)
                HStack(spacing: 12) {
                    if progress.pageCount > 0 {
                        Text("共 \(progress.pageCount) 页 · \(progress.finishedSegments)/\(progress.segmentCount) 段已完成")
                    }
                    if progress.resumed {
                        Label("续跑", systemImage: "arrow.clockwise").foregroundStyle(.blue)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .padding(4)
        } label: {
            Label("正在处理", systemImage: "gearshape.2")
        }
    }
}

private struct SuccessView: View {
    @Environment(AppModel.self) private var model
    @AppStorage(Preferences.chapterLevel) private var chapterLevel = 0
    let result: Completed

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                Label("已生成 \(result.markdownFiles) 个 Markdown 文件（\(result.chapters) 个章节）", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.headline)
                ForEach(result.warnings, id: \.self) { warning in
                    Label(warning, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                }
                HStack {
                    Button("打开文件夹") { model.open(path: result.output) }
                    Button("打开完整文档") { model.open(path: result.document) }
                    Button("查看日志") { model.open(path: result.log) }
                }
                Divider()
                HStack {
                    ChapterLevelPicker(level: $chapterLevel)
                    Spacer()
                    Button("按当前选项重新生成") { model.reprocess() }
                        .help("复用已完成的 OCR 结果，只重新清洗和切分章节，几秒即可完成")
                }
            }
            .padding(4)
        } label: {
            Label("完成", systemImage: "flag.checkered")
        }
    }
}

private struct FailureView: View {
    @Environment(AppModel.self) private var model
    let failure: Failure

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                Label(failure.message, systemImage: failure.errorCode == .cancelled ? "stop.circle" : "xmark.octagon.fill")
                    .foregroundStyle(failure.errorCode == .cancelled ? Color.secondary : Color.red)
                    .textSelection(.enabled)
                if let hint {
                    Text(hint).font(.caption).foregroundStyle(.secondary)
                }
                HStack {
                    recoveryButtons
                    Spacer()
                    if let log = failure.log {
                        Button("查看日志") { model.open(path: log) }
                    }
                }
            }
            .padding(4)
        } label: {
            Label(failure.errorCode == .cancelled ? "已停止" : "转换失败", systemImage: "exclamationmark.bubble")
        }
    }

    private var hint: String? {
        switch failure.errorCode {
        case .ocrServer: return "OCR 服务通常因内存不足退出。可以关闭其他占用内存的应用后继续，已完成的分段不会重做。"
        case .ocrTimeout: return "单段处理时间过长。可以在设置中减小每段页数后重新开始。"
        case .ocrUnavailable: return "应用内置的 MinerU 无法启动，请重新安装 ScribeFlow。"
        case .aiConfig, .aiFailed: return "OCR 结果已保留。检查 AI 设置后继续，或关闭 AI 清洗。"
        default: return failure.resumable ? "已完成的分段已保存，继续时会跳过。" : nil
        }
    }

    @ViewBuilder
    private var recoveryButtons: some View {
        switch failure.errorCode {
        case .outputExists:
            Button("替换已有结果") { model.retry { $0.overwrite = true } }
        case .workspaceConflict:
            Button("放弃旧进度，重新开始") { model.retry { $0.fresh = true } }
        default:
            if failure.resumable {
                Button("继续转换") { model.retry() }.buttonStyle(.borderedProminent)
            }
        }
    }
}
