import Foundation

/// 把任意切分的字节流还原为完整的 UTF-8 行。
public struct LineBuffer: Sendable {
    private var pending = Data()

    public init() {}

    public mutating func append(_ data: Data) -> [String] {
        pending.append(data)
        var lines: [String] = []
        while let newline = pending.firstIndex(of: 0x0A) {
            let line = pending[pending.startIndex..<newline]
            pending.removeSubrange(pending.startIndex...newline)
            lines.append(String(decoding: line, as: UTF8.self))
        }
        return lines
    }

    public mutating func finish() -> [String] {
        defer { pending.removeAll() }
        return pending.isEmpty ? [] : [String(decoding: pending, as: UTF8.self)]
    }
}
