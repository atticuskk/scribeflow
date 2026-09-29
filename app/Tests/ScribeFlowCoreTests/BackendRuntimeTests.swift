import Foundation
import Testing
@testable import ScribeFlowCore

struct BackendRuntimeTests {
    @Test func bundledRuntimeIsPreferredWithoutOverride() throws {
        let resources = URL(fileURLWithPath: "/Applications/ScribeFlow.app/Contents/Resources")
        let runtime = try BackendRuntime.locate(
            resources: resources,
            environment: ["PYTHONHOME": "/bad", "PATH": "/usr/bin"],
            isExecutable: { $0.hasSuffix("runtime/python/bin/python3.12") }
        )
        #expect(runtime.python.path == resources.path + "/runtime/python/bin/python3.12")
        #expect(runtime.environment["PYTHONPATH"] == resources.path + "/runtime/site-packages")
        #expect(runtime.environment["PYTHONHOME"] == nil)
        #expect(runtime.environment["PYTHONUNBUFFERED"] == "1")
    }

    @Test func developmentOverride() throws {
        let runtime = try BackendRuntime.locate(
            resources: nil,
            environment: ["SCRIBEFLOW_PYTHON": "/repo/.venv/bin/python"],
            isExecutable: { _ in true }
        )
        #expect(runtime.python.path == "/repo/.venv/bin/python")
        #expect(runtime.environment["PYTHONPATH"] == nil)
    }

    @Test func missingRuntimeThrows() {
        #expect(throws: BackendRuntimeError.notFound) {
            try BackendRuntime.locate(resources: nil, environment: [:], isExecutable: { _ in false })
        }
    }
}
