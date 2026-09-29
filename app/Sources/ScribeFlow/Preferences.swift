import Foundation
import ScribeFlowCore

/// 用户偏好的键和默认值。界面通过 @AppStorage 读写，启动转换时由 `conversionOptions()` 汇总。
enum Preferences {
    static let segmentPages = "segmentPages"
    static let language = "ocrLanguage"
    static let modelSource = "modelSource"
    static let keepOCROutput = "keepOCROutput"
    static let crossPageMerge = "crossPageMerge"
    static let chapterLevel = "chapterLevel"  // 0 表示自动
    static let useAI = "useAI"
    static let aiModel = "aiModel"
    static let aiBaseURL = "aiBaseURL"
    static let openWhenDone = "openWhenDone"
    static let developerMode = "developerMode"

    struct Language: Identifiable {
        let id: String
        let name: String
    }

    /// MinerU pipeline 后端支持的常用 OCR 语言。
    static let languages = [
        Language(id: "ch", name: "简体中文 / 英文"),
        Language(id: "chinese_cht", name: "繁体中文"),
        Language(id: "en", name: "英文"),
        Language(id: "japan", name: "日文"),
        Language(id: "korean", name: "韩文"),
        Language(id: "latin", name: "拉丁语系"),
    ]

    static func registerDefaults(_ defaults: UserDefaults = .standard) {
        defaults.register(defaults: [
            segmentPages: 16,
            language: "ch",
            modelSource: "modelscope",
            keepOCROutput: true,
            crossPageMerge: true,
            chapterLevel: 0,
            useAI: false,
            aiModel: "",
            aiBaseURL: "",
            openWhenDone: true,
            developerMode: false,
        ])
    }

    enum OptionsError: LocalizedError {
        case aiNotConfigured

        var errorDescription: String? {
            "已开启 AI 清洗，但还没有填写模型名称或 API 密钥。请在“设置 → AI 清洗”中完成配置。"
        }
    }

    static func conversionOptions(_ defaults: UserDefaults = .standard) throws -> ConversionOptions {
        var options = ConversionOptions()
        options.segmentPages = max(1, defaults.integer(forKey: segmentPages))
        options.language = defaults.string(forKey: language) ?? "ch"
        options.modelSource = defaults.string(forKey: modelSource) ?? "modelscope"
        options.keepOCROutput = defaults.bool(forKey: keepOCROutput)
        options.crossPageMerge = defaults.bool(forKey: crossPageMerge)
        let level = defaults.integer(forKey: chapterLevel)
        options.chapterLevel = (1...6).contains(level) ? level : nil
        if defaults.bool(forKey: useAI) {
            let model = (defaults.string(forKey: aiModel) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let key = KeychainStore.loadAPIKey()
            guard !model.isEmpty, !key.isEmpty else { throw OptionsError.aiNotConfigured }
            options.ai = AIOptions(model: model, baseURL: defaults.string(forKey: aiBaseURL) ?? "", apiKey: key)
        }
        return options
    }
}
