import XCTest
@testable import ScribeFlowCore

final class BackendRuntimeTests: XCTestCase {
    func testBundledRuntimeIsPreferredWithoutOverride() throws {
        let resources = URL(fileURLWithPath: "/Applications/ScribeFlow.app/Contents/Resources")
        let runtime = try BackendRuntime.locate(
            resources: resources,
            environment: ["PYTHONHOME": "/bad", "PATH": "/usr/bin"],
            isExecutable: { $0.hasSuffix("runtime/python/bin/python3.12") }
        )
        XCTAssertEqual(runtime.python.path, resources.path + "/runtime/python/bin/python3.12")
        XCTAssertEqual(runtime.environment["PYTHONPATH"], resources.path + "/runtime/site-packages")
        XCTAssertNil(runtime.environment["PYTHONHOME"])
        XCTAssertEqual(runtime.environment["PYTHONUNBUFFERED"], "1")
    }

    func testDevelopmentOverride() throws {
        let runtime = try BackendRuntime.locate(
            resources: nil,
            environment: ["SCRIBEFLOW_PYTHON": "/repo/.venv/bin/python"],
            isExecutable: { _ in true }
        )
        XCTAssertEqual(runtime.python.path, "/repo/.venv/bin/python")
        XCTAssertNil(runtime.environment["PYTHONPATH"])
    }

    func testMissingRuntimeThrows() {
        XCTAssertThrowsError(try BackendRuntime.locate(resources: nil, environment: [:], isExecutable: { _ in false }))
    }
}
