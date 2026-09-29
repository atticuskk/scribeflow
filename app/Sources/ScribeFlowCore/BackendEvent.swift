import Foundation

/// 后端通过 JSON Lines 发出的事件。字段与 Python 端 `scribeflow.events` 一一对应，
/// 协议样例见 `Tests/ScribeFlowCoreTests/Resources/events.jsonl`。
public enum BackendEvent: Equatable, Sendable {
    case started(Started)
    case stage(PipelineStage, message: String)
    case segment(SegmentProgress)
    case diagnostics(section: String, values: [String: String])
    case completed(Completed)
    case failed(Failure)
}

public enum PipelineStage: String, Codable, Sendable {
    case prepare, ocr, clean, ai, render, publish
}

public enum SegmentState: String, Codable, Sendable {
    case running, done, skipped
}

public struct Started: Codable, Equatable, Sendable {
    public var input: String
    public var output: String
    public var pageCount: Int
    public var segmentCount: Int
    public var resumed: Bool
    public var version: Int

    enum CodingKeys: String, CodingKey {
        case input, output, resumed, version
        case pageCount = "page_count"
        case segmentCount = "segment_count"
    }
}

public struct SegmentProgress: Codable, Equatable, Sendable {
    public var index: Int
    public var count: Int
    public var startPage: Int
    public var endPage: Int
    public var state: SegmentState

    public init(index: Int, count: Int, startPage: Int, endPage: Int, state: SegmentState) {
        self.index = index
        self.count = count
        self.startPage = startPage
        self.endPage = endPage
        self.state = state
    }

    enum CodingKeys: String, CodingKey {
        case index, count, state
        case startPage = "start_page"
        case endPage = "end_page"
    }
}

public struct Completed: Codable, Equatable, Sendable {
    public var output: String
    public var document: String
    public var markdownFiles: Int
    public var chapters: Int
    public var log: String
    public var warnings: [String]

    public init(output: String, document: String, markdownFiles: Int, chapters: Int, log: String, warnings: [String]) {
        self.output = output
        self.document = document
        self.markdownFiles = markdownFiles
        self.chapters = chapters
        self.log = log
        self.warnings = warnings
    }

    enum CodingKeys: String, CodingKey {
        case output, document, chapters, log, warnings
        case markdownFiles = "markdown_files"
    }
}

public enum BackendErrorCode: String, Sendable {
    case invalidInput = "invalid_input"
    case outputExists = "output_exists"
    case workspaceConflict = "workspace_conflict"
    case ocrUnavailable = "ocr_unavailable"
    case ocrFailed = "ocr_failed"
    case ocrTimeout = "ocr_timeout"
    case ocrServer = "ocr_server"
    case aiConfig = "ai_config"
    case aiFailed = "ai_failed"
    case cancelled
    case `internal`
    case unknown
}

public struct Failure: Codable, Equatable, Sendable {
    public var code: String
    public var message: String
    public var resumable: Bool
    public var log: String?

    public init(code: String, message: String, resumable: Bool, log: String?) {
        self.code = code
        self.message = message
        self.resumable = resumable
        self.log = log
    }

    public var errorCode: BackendErrorCode {
        BackendErrorCode(rawValue: code) ?? .unknown
    }
}

public enum BackendEventError: Error, Equatable {
    case unknownEvent(String)
}

extension BackendEvent: Decodable {
    private enum Keys: String, CodingKey {
        case event, stage, message, section, values
    }

    public init(from decoder: Decoder) throws {
        let keys = try decoder.container(keyedBy: Keys.self)
        let name = try keys.decode(String.self, forKey: .event)
        switch name {
        case "started":
            self = .started(try Started(from: decoder))
        case "stage":
            self = .stage(
                try keys.decode(PipelineStage.self, forKey: .stage),
                message: try keys.decode(String.self, forKey: .message)
            )
        case "segment":
            self = .segment(try SegmentProgress(from: decoder))
        case "diagnostics":
            self = .diagnostics(
                section: try keys.decode(String.self, forKey: .section),
                values: try keys.decode([String: String].self, forKey: .values)
            )
        case "completed":
            self = .completed(try Completed(from: decoder))
        case "failed":
            self = .failed(try Failure(from: decoder))
        default:
            throw BackendEventError.unknownEvent(name)
        }
    }

    /// 解析一行 JSON；不是事件的行返回 nil。
    public static func decode(line: String) -> BackendEvent? {
        guard let data = line.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(BackendEvent.self, from: data)
    }
}
