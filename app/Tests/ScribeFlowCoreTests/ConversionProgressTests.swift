import Foundation
import Testing
@testable import ScribeFlowCore

struct ConversionProgressTests {
    @Test func progressFollowsEvents() {
        var progress = ConversionProgress()
        progress.begin(message: "正在启动")
        progress.apply(.started(Started(input: "a", output: "b", pageCount: 40, segmentCount: 3, resumed: true, version: 1)))
        #expect(progress.message == "继续上次未完成的任务")
        progress.apply(.segment(SegmentProgress(index: 1, count: 3, startPage: 1, endPage: 16, state: .skipped)))
        progress.apply(.segment(SegmentProgress(index: 2, count: 3, startPage: 17, endPage: 32, state: .running)))
        #expect(progress.message == "正在识别第 2/3 段（第 17–32 页）")
        #expect(abs((progress.fraction ?? 0) - 1.0 / 3.0) < 0.001)
        progress.apply(.segment(SegmentProgress(index: 2, count: 3, startPage: 17, endPage: 32, state: .done)))
        progress.apply(.stage(.render, message: "正在生成 Markdown"))
        #expect(progress.fraction == 0.97)
        let result = Completed(output: "o", document: "d", markdownFiles: 3, chapters: 2, log: "l", warnings: [])
        progress.apply(.completed(result))
        #expect(progress.phase == .succeeded(result))
        #expect(!progress.isActive)
        progress.processExited(status: 0)
        #expect(progress.phase == .succeeded(result))
    }

    @Test func unexpectedExitBecomesFailure() {
        var progress = ConversionProgress()
        progress.begin(message: "x")
        progress.processExited(status: 9)
        guard case let .failed(failure) = progress.phase else { Issue.record("expected failure"); return }
        #expect(failure.errorCode == .internal)
    }

    @Test func cancellingWithoutEventBecomesCancelled() {
        var progress = ConversionProgress()
        progress.begin(message: "x")
        progress.beginCancelling()
        #expect(progress.phase == .cancelling)
        progress.processExited(status: 15)
        guard case let .failed(failure) = progress.phase else { Issue.record("expected failure"); return }
        #expect(failure.errorCode == .cancelled)
    }
}
