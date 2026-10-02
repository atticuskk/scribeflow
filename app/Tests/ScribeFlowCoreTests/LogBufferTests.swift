import Testing
@testable import ScribeFlowCore

struct LogBufferTests {
    @Test func keepsNewestLinesWithStableIDs() {
        var log = LogBuffer(capacity: 3)
        log.append(contentsOf: ["a", "b"])
        let firstB = log.lines[1]
        log.append(contentsOf: ["c", "d"])
        #expect(log.lines.map(\.text) == ["b", "c", "d"])
        #expect(log.lines.first == firstB)  // 裁掉旧行不改变其余行的 id
        #expect(log.lines.map(\.id) == [1, 2, 3])
    }

    @Test func oversizedBatchKeepsTailAndAdvancesIDs() {
        var log = LogBuffer(capacity: 2)
        log.append(contentsOf: ["a", "b", "c", "d", "e"])
        #expect(log.lines.map(\.text) == ["d", "e"])
        #expect(log.lines.map(\.id) == [3, 4])
    }

    @Test func idsAreNotReusedAfterClearing() {
        var log = LogBuffer(capacity: 5)
        log.append(contentsOf: ["a"])
        log.removeAll()
        log.append(contentsOf: ["b"])
        #expect(log.lines == [LogLine(id: 1, text: "b")])
    }
}
