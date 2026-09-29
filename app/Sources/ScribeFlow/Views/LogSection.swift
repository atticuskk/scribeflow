import SwiftUI

struct LogSection: View {
    @Environment(AppModel.self) private var model
    @State private var expanded = false

    var body: some View {
        if !model.logLines.isEmpty {
            DisclosureGroup("运行日志（\(model.logLines.count) 行）", isExpanded: $expanded) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 1) {
                            ForEach(Array(model.logLines.enumerated()), id: \.offset) { index, line in
                                Text(line)
                                    .font(.system(.caption, design: .monospaced))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .id(index)
                            }
                        }
                        .textSelection(.enabled)
                        .padding(8)
                    }
                    .frame(height: 220)
                    .background(Color.secondary.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .onChange(of: model.logLines.count) { _, count in
                        proxy.scrollTo(count - 1, anchor: .bottom)
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
