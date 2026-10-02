import SwiftUI

struct LogSection: View {
    @Environment(AppModel.self) private var model
    @State private var expanded = false

    var body: some View {
        if !model.log.lines.isEmpty {
            DisclosureGroup("运行日志（最近 \(model.log.lines.count) 行）", isExpanded: $expanded) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 1) {
                            ForEach(model.log.lines) { line in
                                Text(line.text)
                                    .font(.system(.caption, design: .monospaced))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                        .textSelection(.enabled)
                        .padding(8)
                    }
                    .frame(height: 220)
                    .background(Color.secondary.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    // 跟随最后一行的 id 而不是行数：日志满 3000 行后行数不再变化，仍要滚到底部
                    .onChange(of: model.log.lines.last?.id) { _, id in
                        if let id { proxy.scrollTo(id, anchor: .bottom) }
                    }
                }
            }
        }
    }
}

struct DiagnosticsSection: View {
    @Environment(AppModel.self) private var model
    @AppStorage(Preferences.developerMode) private var developerMode = false

    var body: some View {
        if developerMode, !model.progress.diagnostics.isEmpty {
            DisclosureGroup("开发者诊断") {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(model.progress.diagnostics.keys.sorted(), id: \.self) { section in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(section.uppercased()).font(.caption.bold()).foregroundStyle(.secondary)
                            let values = model.progress.diagnostics[section] ?? [:]
                            ForEach(values.keys.sorted(), id: \.self) { key in
                                HStack(alignment: .top) {
                                    Text(key).foregroundStyle(.secondary).frame(width: 110, alignment: .leading)
                                    Text(values[key] ?? "").font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                                }
                            }
                        }
                    }
                }
                .padding(.top, 6)
            }
        }
    }
}
