import Foundation
import Testing
@testable import ScribeFlowCore

struct LineBufferTests {
    @Test func reassemblesSplitMultibyteLines() {
        var buffer = LineBuffer()
        var lines: [String] = []
        for byte in Array("第一行\n第二行\n尾".utf8) {
            lines += buffer.append(Data([byte]))
        }
        #expect(lines == ["第一行", "第二行"])
        #expect(buffer.finish() == ["尾"])
        #expect(buffer.finish().isEmpty)
    }
}
