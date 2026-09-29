import ScribeFlowCore
import SwiftUI

struct ContentView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                SourceSection()
                OptionsSection()
                ActionBar()
                StatusSection()
                DiagnosticsSection()
                LogSection()
            }
            .padding(24)
        }
        .alert(
            "无法开始",
            isPresented: Binding(get: { model.alertMessage != nil }, set: { if !$0 { model.alertMessage = nil } }),
            actions: { Button("好") { model.alertMessage = nil } },
            message: { Text(model.alertMessage ?? "") }
        )
    }

    private var header: some View {
        HStack(spacing: 14) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 32))
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 2) {
                Text("ScribeFlow").font(.title2.bold())
                Text("扫描版 PDF → 保真清洗 → 章节 Markdown").foregroundStyle(.secondary)
            }
        }
    }
}

/// 拖入 PDF、选择输出位置。
struct SourceSection: View {
    @Environment(AppModel.self) private var model
    @State private var isTargeted = false

    var body: some View {
        VStack(spacing: 12) {
            dropZone
            GroupBox {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(model.outputParent?.path ?? "尚未选择输出位置").lineLimit(1).truncationMode(.middle)
                        if let output = model.proposedOutput {
                            Text("将生成文件夹：\(output.lastPathComponent)").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Button("更改…") { model.chooseOutputParent() }
                        .disabled(model.progress.isActive)
                }
                .padding(4)
            } label: {
                Label("输出位置", systemImage: "folder")
            }
        }
    }

    private var dropZone: some View {
        VStack(spacing: 10) {
            Image(systemName: model.inputPDF == nil ? "arrow.down.doc" : "doc.richtext")
                .font(.system(size: 36))
                .foregroundStyle(isTargeted ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))
            if let pdf = model.inputPDF {
                Text(pdf.lastPathComponent).font(.headline).lineLimit(1).truncationMode(.middle)
                Text(pdf.deletingLastPathComponent().path)
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
            } else {
                Text("把扫描版 PDF 拖到这里").font(.headline)
            }
            Button(model.inputPDF == nil ? "选择 PDF…" : "更换 PDF…") { model.choosePDF() }
                .disabled(model.progress.isActive)
        }
        .frame(maxWidth: .infinity, minHeight: 150)
        .background(RoundedRectangle(cornerRadius: 12).fill(isTargeted ? Color.accentColor.opacity(0.1) : Color.secondary.opacity(0.06)))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(isTargeted ? Color.accentColor : Color.secondary.opacity(0.35), style: StrokeStyle(lineWidth: 1.5, dash: [7]))
        )
        .dropDestination(for: URL.self) { urls, _ in
            guard !model.progress.isActive, let pdf = urls.first(where: { $0.pathExtension.lowercased() == "pdf" }) else {
                return false
            }
            model.selectInput(pdf)
            return true
        } isTargeted: { isTargeted = $0 }
    }
}

/// 每次转换都可能调整的选项；其余参数在“设置”中。
struct OptionsSection: View {
    @Environment(AppModel.self) private var model
    @AppStorage(Preferences.chapterLevel) private var chapterLevel = 0
    @AppStorage(Preferences.crossPageMerge) private var crossPageMerge = true
    @AppStorage(Preferences.useAI) private var useAI = false

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                ChapterLevelPicker(level: $chapterLevel)
                Toggle("合并被分页截断的中文句子", isOn: $crossPageMerge)
                HStack {
                    Toggle("使用 AI 清洗格式（不会改写正文）", isOn: $useAI)
                    Spacer()
                    SettingsLink { Text("AI 设置…") }
                }
                if useAI {
                    Text("开启后，内容块会发送到你在设置中配置的 AI 服务。")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(4)
            .disabled(model.progress.isActive)
        } label: {
            Label("转换选项", systemImage: "slider.horizontal.3")
        }
    }
}

struct ChapterLevelPicker: View {
    @Binding var level: Int

    var body: some View {
        Picker("章节切分", selection: $level) {
            Text("自动").tag(0)
            ForEach(1...6, id: \.self) { Text("第 \($0) 级标题").tag($0) }
        }
        .fixedSize()
    }
}

struct ActionBar: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        HStack {
            if model.progress.isActive {
                Button("停止", role: .destructive) { model.cancel() }
                    .disabled(model.progress.phase == .cancelling)
            }
            Spacer()
            Button {
                model.startConversion()
            } label: {
                Label("开始转换", systemImage: "play.fill").frame(minWidth: 110)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
            .disabled(!model.canStart)
        }
    }
}
