import XCTest
@testable import ScribeFlowCore

final class LineBufferTests: XCTestCase {
    func testReassemblesSplitMultibyteLines() {
        let bytes = Array("第一行\n第二行\n尾".utf8)
        var buffer = LineBuffer()
        var lines: [String] = []
        for byte in bytes {
            lines += buffer.append(Data([byte]))
        }
        XCTAssertEqual(lines, ["第一行", "第二行"])
        XCTAssertEqual(buffer.finish(), ["尾"])
        XCTAssertEqual(buffer.finish(), [])
    }
}
