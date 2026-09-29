import Foundation
import Testing
@testable import ScribeFlowCore

struct BackendEventTests {
    /// 与 Python 端 tests/test_events.py 共用同一份协议样例。
    @Test func decodesSharedProtocolSamples() throws {
        let url = try #require(Bundle.module.url(forResource: "events", withExtension: "jsonl", subdirectory: "Resources"))
        let lines = try String(contentsOf: url, encoding: .utf8).split(separator: "\n").map(String.init)
        let events = lines.compactMap(BackendEvent.decode(line:))
        try #require(events.count == lines.count)

        #expect(events[0] == .stage(.prepare, message: "正在检查 PDF"))
        guard case let .started(started) = events[1] else { Issue.record("expected started"); return }
        #expect(started.pageCount == 480)
        #expect(started.segmentCount == 30)
        #expect(started.resumed)
        #expect(events[2] == .segment(SegmentProgress(index: 1, count: 30, startPage: 1, endPage: 16, state: .skipped)))
        #expect(events[3] == .diagnostics(section: "ocr", values: ["引擎": "MinerU", "服务": "http://127.0.0.1:50123"]))
        guard case let .completed(result) = events[6] else { Issue.record("expected completed"); return }
        #expect(result.markdownFiles == 13)
        #expect(result.chapters == 12)
        #expect(result.warnings.count == 1)
        guard case let .failed(failure) = events[7] else { Issue.record("expected failed"); return }
        #expect(failure.errorCode == .ocrServer)
        #expect(failure.resumable)
        guard case let .failed(invalid) = events[8] else { Issue.record("expected failed"); return }
        #expect(invalid.log == nil)
        #expect(invalid.errorCode == .invalidInput)
    }

    @Test func nonEventLinesAreIgnored() {
        #expect(BackendEvent.decode(line: "MinerU | loading model") == nil)
        #expect(BackendEvent.decode(line: #"{"event": "future_event"}"#) == nil)
        #expect(
            BackendEvent.decode(line: #"{"event": "failed", "code": "brand_new", "message": "m", "resumable": false}"#)
                == .failed(Failure(code: "brand_new", message: "m", resumable: false, log: nil))
        )
    }
}
