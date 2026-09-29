import XCTest
@testable import ScribeFlowCore

final class BackendEventTests: XCTestCase {
    /// 与 Python 端 tests/test_events.py 共用同一份协议样例。
    func testDecodesSharedProtocolSamples() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "events", withExtension: "jsonl", subdirectory: "Resources"))
        let lines = try String(contentsOf: url, encoding: .utf8).split(separator: "\n").map(String.init)
        let events = lines.compactMap(BackendEvent.decode(line:))
        XCTAssertEqual(events.count, lines.count)

        XCTAssertEqual(events[0], .stage(.prepare, message: "正在检查 PDF"))
        guard case let .started(started) = events[1] else { return XCTFail("expected started") }
        XCTAssertEqual(started.pageCount, 480)
        XCTAssertEqual(started.segmentCount, 30)
        XCTAssertTrue(started.resumed)
        XCTAssertEqual(events[2], .segment(SegmentProgress(index: 1, count: 30, startPage: 1, endPage: 16, state: .skipped)))
        XCTAssertEqual(events[3], .diagnostics(section: "ocr", values: ["引擎": "MinerU", "服务": "http://127.0.0.1:50123"]))
        guard case let .completed(result) = events[6] else { return XCTFail("expected completed") }
        XCTAssertEqual(result.markdownFiles, 13)
        XCTAssertEqual(result.chapters, 12)
        XCTAssertEqual(result.warnings.count, 1)
        guard case let .failed(failure) = events[7] else { return XCTFail("expected failed") }
        XCTAssertEqual(failure.errorCode, .ocrServer)
        XCTAssertTrue(failure.resumable)
        guard case let .failed(invalid) = events[8] else { return XCTFail("expected failed") }
        XCTAssertNil(invalid.log)
        XCTAssertEqual(invalid.errorCode, .invalidInput)
    }

    func testNonEventLinesAreIgnored() {
        XCTAssertNil(BackendEvent.decode(line: "MinerU | loading model"))
        XCTAssertNil(BackendEvent.decode(line: #"{"event": "future_event"}"#))
        XCTAssertEqual(
            BackendEvent.decode(line: #"{"event": "failed", "code": "brand_new", "message": "m", "resumable": false}"#),
            .failed(Failure(code: "brand_new", message: "m", resumable: false, log: nil))
        )
    }
}
