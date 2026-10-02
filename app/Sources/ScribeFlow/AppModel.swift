import AppKit
import UniformTypeIdentifiers
import Observation
import ScribeFlowCore

/// 界面状态与后端进程之间的桥梁。
@MainActor
@Observable
final class AppModel {
    var inputPDF: URL?
    var outputParent: URL?
    private(set) var progress = ConversionProgress()
    private(set) var logLines: [String] = []
    private(set) var lastOutput: URL?
    var alertMessage: String?

    private var process: BackendProcess?
    private var lastCommand: BackendCommand?
    private var openWhenDone = false
    private var onBackendExit: (() -> Void)?
    private static let maxLogLines = 3000

    var proposedOutput: URL? {
        guard let inputPDF, let outputParent else { return nil }
        let stem = inputPDF.deletingPathExtension().lastPathComponent
        return outputParent.appendingPathComponent("\(stem)-Markdown", isDirectory: true)
    }

    var canStart: Bool {
        proposedOutput != nil && !progress.isActive
    }

    // MARK: 选择文件

    func selectInput(_ url: URL) {
        guard url.pathExtension.lowercased() == "pdf" else {
            alertMessage = "请选择 PDF 文件。"
            return
        }
        inputPDF = url
        if outputParent == nil {
            outputParent = url.deletingLastPathComponent()
        }
        if !progress.isActive {
            progress = ConversionProgress()
        }
    }

    func choosePDF() {
        let panel = NSOpenPanel()
        panel.title = "选择扫描版 PDF"
        panel.allowedContentTypes = [.pdf]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            selectInput(url)
        }
    }

    func chooseOutputParent() {
        let panel = NSOpenPanel()
        panel.title = "选择输出位置"
        panel.prompt = "选择"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        if panel.runModal() == .OK, let url = panel.url {
            outputParent = url
        }
    }

    func chooseOutputToReprocess() {
        let panel = NSOpenPanel()
        panel.title = "选择 ScribeFlow 生成的输出文件夹"
        panel.prompt = "重新生成"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        if panel.runModal() == .OK, let url = panel.url {
            reprocess(output: url)
        }
    }

    // MARK: 运行

    func startConversion() {
        guard let input = inputPDF, let output = proposedOutput else { return }
        withOptions { options in
            run(.convert(input: input, output: output, options: options))
        }
    }

    /// 在上一次转换命令的基础上修改选项后重试，例如改为覆盖、重新开始或继续。
    func retry(_ change: (inout ConversionOptions) -> Void = { _ in }) {
        guard case let .convert(input, output, options)? = lastCommand else { return }
        var updated = options
        change(&updated)
        run(.convert(input: input, output: output, options: updated))
    }

    func reprocess(output: URL? = nil) {
        guard let target = output ?? lastOutput else { return }
        withOptions { options in
            run(.reprocess(output: target, options: options))
        }
    }

    func cancel() {
        guard let process, process.isRunning else { return }
        progress.beginCancelling()
        process.cancel()
    }

    /// 退出应用前停止正在运行的后端，后端退出（必要时被强制结束）后调用 `done`。
    /// 没有正在运行的任务时返回 false，可以立即退出。
    func stopBeforeQuit(_ done: @escaping () -> Void) -> Bool {
        guard let process, process.isRunning else { return false }
        onBackendExit = done
        if progress.phase != .cancelling { cancel() }
        return true
    }

    private func withOptions(_ body: (ConversionOptions) -> Void) {
        do {
            body(try Preferences.conversionOptions())
        } catch {
            alertMessage = error.localizedDescription
        }
    }

    private func run(_ command: BackendCommand) {
        guard !progress.isActive else { return }
        logLines = []
        lastCommand = command
        openWhenDone = UserDefaults.standard.bool(forKey: Preferences.openWhenDone)
        progress.begin(message: "正在启动…")
        do {
            let process = BackendProcess(runtime: try BackendRuntime.locate(), command: command)
            let stream = try process.start()
            self.process = process
            Task { [weak self] in
                for await output in stream {
                    self?.handle(output)
                }
            }
        } catch {
            progress.apply(.failed(Failure(code: "internal", message: error.localizedDescription, resumable: false, log: nil)))
        }
    }

    private func handle(_ output: BackendOutput) {
        switch output {
        case let .event(event):
            progress.apply(event)
            if case let .completed(result) = event {
                let url = URL(fileURLWithPath: result.output, isDirectory: true)
                lastOutput = url
                if openWhenDone { NSWorkspace.shared.open(url) }
            }
        case let .log(line):
            logLines.append(line)
            if logLines.count > Self.maxLogLines {
                logLines.removeFirst(logLines.count - Self.maxLogLines)
            }
        case let .exited(status):
            progress.processExited(status: status)
            process = nil
            onBackendExit?()
            onBackendExit = nil
        }
    }

    // MARK: 打开文件

    func open(path: String) {
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    func reveal(path: String) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }
}
