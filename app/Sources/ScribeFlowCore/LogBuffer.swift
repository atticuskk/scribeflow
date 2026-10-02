import Foundation

public struct LogLine: Identifiable, Equatable, Sendable {
    public let id: Int
    public let text: String
}

/// 界面上的运行日志：只保留最近 `capacity` 行。
/// 每行的 id 递增且不复用，裁掉旧行时其余行的 id 不变，列表不必整体重新渲染。
public struct LogBuffer: Equatable, Sendable {
    public private(set) var lines: [LogLine] = []
    public let capacity: Int
    private var nextID = 0

    public init(capacity: Int = 3000) {
        self.capacity = max(1, capacity)
    }

    public mutating func append(contentsOf texts: [String]) {
        let kept = texts.suffix(capacity)
        nextID += texts.count - kept.count
        for text in kept {
            lines.append(LogLine(id: nextID, text: text))
            nextID += 1
        }
        if lines.count > capacity {
            lines.removeFirst(lines.count - capacity)
        }
    }

    public mutating func removeAll() {
        lines.removeAll()
    }
}
