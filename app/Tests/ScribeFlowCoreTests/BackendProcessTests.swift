import Foundation
import Testing
@testable import ScribeFlowCore

struct BackendProcessTests {
    private func script(_ body: String) throws -> BackendRuntime {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("fake-backend-\(UUID().uuidString).sh")
        try "#!/bin/sh\n\(body)\n".write(to: url, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        return BackendRuntime(python: url, environment: ProcessInfo.processInfo.environment)
    }

    @Test func streamsEventsLogsAndExitStatus() async throws {
        let runtime = try script("""
        echo '{"event": "stage", "stage": "ocr", "message": "识别中"}'
        echo 'MinerU | 日志' >&2
        printf '%s' '{"event": "failed", "code": "cancelled", "message": "m", "resumable": true, "log": null}'
        exit 3
        """)
        var options = ConversionOptions()
        options.ai = AIOptions(model: "m", apiKey: "k")
        let process = BackendProcess(runtime: runtime, command: .reprocess(output: URL(fileURLWithPath: "/o"), options: options))
        var outputs: [BackendOutput] = []
        for await output in try process.start() { outputs.append(output) }
        #expect(outputs.contains(.event(.stage(.ocr, message: "识别中"))))
        #expect(outputs.contains(.log("MinerU | 日志")))
        #expect(outputs.contains(.event(.failed(Failure(code: "cancelled", message: "m", resumable: true, log: nil)))))
        #expect(outputs.last == .exited(3))
    }

    @Test func cancelSendsTerminate() async throws {
        let runtime = try script("""
        trap 'echo "{\\"event\\": \\"failed\\", \\"code\\": \\"cancelled\\", \\"message\\": \\"stopped\\", \\"resumable\\": true}"; exit 130' TERM
        echo started >&2
        while true; do sleep 0.1; done
        """)
        let process = BackendProcess(runtime: runtime, command: .reprocess(output: URL(fileURLWithPath: "/o"), options: ConversionOptions()))
        var outputs: [BackendOutput] = []
        for await output in try process.start() {
            outputs.append(output)
            if output == .log("started") { process.cancel() }
        }
        #expect(outputs.last == .exited(130))
        #expect(outputs.contains(.event(.failed(Failure(code: "cancelled", message: "stopped", resumable: true, log: nil)))))
    }
}
