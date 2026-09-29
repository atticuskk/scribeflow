import SwiftUI

struct SettingsView: View {
    var body: some View {
        TabView {
            OCRSettings().tabItem { Label("OCR", systemImage: "text.viewfinder") }
            AISettings().tabItem { Label("AI 清洗", systemImage: "sparkles") }
            GeneralSettings().tabItem { Label("通用", systemImage: "gearshape") }
        }
        .frame(width: 480)
        .padding(20)
    }
}

private struct OCRSettings: View {
    @AppStorage(Preferences.language) private var language = "ch"
    @AppStorage(Preferences.modelSource) private var modelSource = "modelscope"
    @AppStorage(Preferences.segmentPages) private var segmentPages = 16
    @AppStorage(Preferences.keepOCROutput) private var keepOCROutput = true

    var body: some View {
        Form {
            Picker("识别语言", selection: $language) {
                ForEach(Preferences.languages) { Text($0.name).tag($0.id) }
            }
            Picker("模型下载源", selection: $modelSource) {
                Text("ModelScope（国内推荐）").tag("modelscope")
                Text("Hugging Face").tag("huggingface")
                Text("本地模型").tag("local")
            }
            Stepper("每段 \(segmentPages) 页", value: $segmentPages, in: 4...64, step: 4)
            Text("分段越小，内存占用越低、失败后重做的页数越少；分段越大，整体速度略快。")
                .font(.caption).foregroundStyle(.secondary)
            Toggle("在输出中保留 MinerU 原始结果", isOn: $keepOCROutput)
        }
    }
}

private struct AISettings: View {
    @AppStorage(Preferences.aiModel) private var model = ""
    @AppStorage(Preferences.aiBaseURL) private var baseURL = ""
    @State private var apiKey = ""
    @State private var status: String?

    var body: some View {
        Form {
            TextField("模型名称", text: $model, prompt: Text("例如 gpt-4.1-mini"))
            TextField("接口地址", text: $baseURL, prompt: Text("使用 OpenAI 默认接口时留空"))
            SecureField("API 密钥", text: $apiKey)
            HStack {
                Button("保存密钥到钥匙串") { save() }
                if let status { Text(status).font(.caption).foregroundStyle(.secondary) }
            }
            Text("AI 只会返回“删除 / 合并 / 调整标题层级”三类块级操作，程序会逐条校验并记录审计，正文不会被改写。")
                .font(.caption).foregroundStyle(.secondary)
        }
        .onAppear { apiKey = KeychainStore.loadAPIKey() }
    }

    private func save() {
        do {
            try KeychainStore.saveAPIKey(apiKey)
            status = apiKey.isEmpty ? "已删除" : "已保存"
        } catch {
            status = error.localizedDescription
        }
    }
}

private struct GeneralSettings: View {
    @AppStorage(Preferences.openWhenDone) private var openWhenDone = true
    @AppStorage(Preferences.developerMode) private var developerMode = false

    var body: some View {
        Form {
            Toggle("完成后打开输出文件夹", isOn: $openWhenDone)
            Toggle("开发者模式（显示 OCR / AI 诊断信息）", isOn: $developerMode)
            if let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String {
                LabeledContent("版本", value: version)
            }
        }
    }
}
