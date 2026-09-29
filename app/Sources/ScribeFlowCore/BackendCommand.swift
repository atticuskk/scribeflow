import Foundation

public struct AIOptions: Equatable, Sendable {
    public var model: String
    public var baseURL: String
    public var apiKey: String

    public init(model: String, baseURL: String = "", apiKey: String) {
        self.model = model
        self.baseURL = baseURL
        self.apiKey = apiKey
    }
}

/// 一次转换的用户选项。
public struct ConversionOptions: Equatable, Sendable {
    public var overwrite = false
    public var fresh = false
    public var segmentPages = 16
    public var chapterLevel: Int?
    public var crossPageMerge = true
    public var keepOCROutput = true
    public var language = "ch"
    public var modelSource = "modelscope"
    public var ai: AIOptions?

    public init() {}
}

/// 要交给 Python 后端执行的命令。
public enum BackendCommand: Equatable, Sendable {
    case convert(input: URL, output: URL, options: ConversionOptions)
    case reprocess(output: URL, options: ConversionOptions)

    public var arguments: [String] {
        var arguments = ["-m", "scribeflow"]
        let options: ConversionOptions
        switch self {
        case let .convert(input, output, convertOptions):
            options = convertOptions
            arguments += [
                "convert", input.path, "--output", output.path,
                "--segment-pages", String(options.segmentPages),
                "--lang", options.language,
                "--model-source", options.modelSource,
            ]
            if options.overwrite { arguments.append("--overwrite") }
            if options.fresh { arguments.append("--fresh") }
            if !options.keepOCROutput { arguments.append("--discard-ocr-output") }
        case let .reprocess(output, reprocessOptions):
            options = reprocessOptions
            arguments += ["reprocess", output.path]
        }
        if let level = options.chapterLevel { arguments += ["--chapter-level", String(level)] }
        if !options.crossPageMerge { arguments.append("--no-cross-page-merge") }
        if let ai = options.ai {
            arguments += ["--ai", "--ai-model", ai.model]
            let baseURL = ai.baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
            if !baseURL.isEmpty { arguments += ["--ai-base-url", baseURL] }
        }
        return arguments + ["--events", "jsonl"]
    }

    /// 通过环境变量而不是命令行参数传递密钥，避免出现在进程列表里。
    public var environment: [String: String] {
        switch self {
        case let .convert(_, _, options), let .reprocess(_, options):
            guard let ai = options.ai else { return [:] }
            return ["SCRIBEFLOW_AI_API_KEY": ai.apiKey]
        }
    }
}
