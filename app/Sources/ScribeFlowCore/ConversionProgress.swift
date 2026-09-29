import Foundation

/// 由后端事件驱动的转换状态。纯值类型，便于测试。
public struct ConversionProgress: Equatable, Sendable {
    public enum Phase: Equatable, Sendable {
        case idle
        case running
        case cancelling
        case succeeded(Completed)
        case failed(Failure)
    }

    public var phase: Phase = .idle
    public var stage: PipelineStage?
    public var message = ""
    public var pageCount = 0
    public var segmentCount = 0
    public var finishedSegments = 0
    public var resumed = false
    public var diagnostics: [String: [String: String]] = [:]

    public init() {}

    public var isActive: Bool {
        phase == .running || phase == .cancelling
    }

    /// OCR 占绝大部分耗时，所以进度按已完成分段计算；OCR 之后的阶段视为接近完成。
    public var fraction: Double? {
        guard segmentCount > 0 else { return nil }
        let ocr = Double(finishedSegments) / Double(segmentCount)
        switch stage {
        case .clean?, .ai?, .render?, .publish?: return 0.97
        default: return min(ocr, 0.95)
        }
    }

    public mutating func begin(message: String) {
        self = ConversionProgress()
        phase = .running
        self.message = message
    }

    public mutating func beginCancelling() {
        if phase == .running {
            phase = .cancelling
            message = "正在停止…"
        }
    }

    public mutating func apply(_ event: BackendEvent) {
        switch event {
        case let .started(started):
            pageCount = started.pageCount
            segmentCount = started.segmentCount
            resumed = started.resumed
            if started.resumed { message = "继续上次未完成的任务" }
        case let .stage(stage, text):
            self.stage = stage
            message = text
        case let .segment(segment):
            stage = .ocr
            segmentCount = segment.count
            switch segment.state {
            case .running:
                message = "正在识别第 \(segment.index)/\(segment.count) 段（第 \(segment.startPage)–\(segment.endPage) 页）"
            case .done, .skipped:
                finishedSegments = min(finishedSegments + 1, segment.count)
            }
        case let .diagnostics(section, values):
            diagnostics[section] = values
        case let .completed(result):
            phase = .succeeded(result)
            message = "已完成"
        case let .failed(failure):
            phase = .failed(failure)
            message = failure.errorCode == .cancelled ? "已停止" : "转换失败"
        }
    }

    /// 进程退出但没有收到结束事件时，补一个失败状态。
    public mutating func processExited(status: Int32) {
        guard isActive else { return }
        if phase == .cancelling {
            apply(.failed(Failure(code: "cancelled", message: "任务已取消。", resumable: true, log: nil)))
        } else {
            apply(.failed(Failure(
                code: "internal",
                message: "后端异常退出（代码 \(status)）。请查看日志。",
                resumable: false,
                log: nil
            )))
        }
    }
}
