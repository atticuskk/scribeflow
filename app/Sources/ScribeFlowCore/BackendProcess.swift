import Foundation

/// 后端进程的输出：stdout 上的事件，stderr 上的日志，以及退出状态。
public enum BackendOutput: Equatable, Sendable {
    case event(BackendEvent)
    case log(String)
    case exited(Int32)
}

/// 运行一次 Python 后端并以 AsyncStream 交付输出。
///
/// 取消时先发送 SIGTERM，后端会停止 MinerU 并记录可续跑的进度；
/// 超过宽限时间仍未退出则强制结束。
public final class BackendProcess: @unchecked Sendable {
    private let process = Process()
    private let queue = DispatchQueue(label: "ScribeFlow.BackendProcess")
    private let killGrace: TimeInterval

    public init(runtime: BackendRuntime, command: BackendCommand, killGrace: TimeInterval = 20) {
        process.executableURL = runtime.python
        process.arguments = command.arguments
        process.environment = runtime.environment.merging(command.environment) { _, new in new }
        self.killGrace = killGrace
    }

    public var isRunning: Bool { process.isRunning }

    public func start() throws -> AsyncStream<BackendOutput> {
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr
        process.standardInput = FileHandle.nullDevice

        let (stream, continuation) = AsyncStream.makeStream(of: BackendOutput.self)
        let group = DispatchGroup()
        let queue = self.queue

        func pump(_ pipe: Pipe, _ transform: @escaping @Sendable (String) -> BackendOutput?) {
            group.enter()
            let buffer = BufferBox()
            pipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                queue.async {
                    let lines = data.isEmpty ? buffer.value.finish() : buffer.value.append(data)
                    for line in lines {
                        if let output = transform(line) { continuation.yield(output) }
                    }
                    if data.isEmpty {
                        handle.readabilityHandler = nil
                        group.leave()
                    }
                }
            }
        }

        pump(stdout) { line in
            if let event = BackendEvent.decode(line: line) { return .event(event) }
            return line.isEmpty ? nil : .log(line)
        }
        pump(stderr) { line in line.isEmpty ? nil : .log(line) }

        group.enter()
        process.terminationHandler = { _ in group.leave() }
        group.notify(queue: queue) { [process] in
            continuation.yield(.exited(process.terminationStatus))
            continuation.finish()
        }

        do {
            try process.run()
        } catch {
            stdout.fileHandleForReading.readabilityHandler = nil
            stderr.fileHandleForReading.readabilityHandler = nil
            continuation.finish()
            throw error
        }
        return stream
    }

    public func cancel() {
        guard process.isRunning else { return }
        process.terminate()
        let pid = process.processIdentifier
        queue.asyncAfter(deadline: .now() + killGrace) { [process] in
            if process.isRunning { kill(pid, SIGKILL) }
        }
    }
}

/// 只在串行队列上访问的行缓冲。
private final class BufferBox: @unchecked Sendable {
    var value = LineBuffer()
}
