import Foundation

public enum BackendRuntimeError: LocalizedError, Equatable {
    case notFound

    public var errorDescription: String? {
        "找不到应用内置的 Python 后端。请重新安装 ScribeFlow；开发时可设置环境变量 SCRIBEFLOW_PYTHON 指向项目 .venv 中的 python。"
    }
}

/// 运行后端所需的 Python 解释器和环境变量。
public struct BackendRuntime: Equatable, Sendable {
    public var python: URL
    public var environment: [String: String]

    public init(python: URL, environment: [String: String]) {
        self.python = python
        self.environment = environment
    }

    /// 查找顺序：环境变量 `SCRIBEFLOW_PYTHON`（开发用）→ 应用包内 `Resources/runtime`。
    public static func locate(
        resources: URL? = Bundle.main.resourceURL,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        isExecutable: (String) -> Bool = FileManager.default.isExecutableFile(atPath:)
    ) throws -> BackendRuntime {
        var env = environment
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        if let override = environment["SCRIBEFLOW_PYTHON"], !override.isEmpty, isExecutable(override) {
            return BackendRuntime(python: URL(fileURLWithPath: override), environment: env)
        }
        if let resources {
            let runtime = resources.appendingPathComponent("runtime", isDirectory: true)
            let python = runtime.appendingPathComponent("python/bin/python3.12")
            if isExecutable(python.path) {
                env["PYTHONPATH"] = runtime.appendingPathComponent("site-packages", isDirectory: true).path
                env["PYTHONNOUSERSITE"] = "1"
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                env.removeValue(forKey: "PYTHONHOME")
                let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
                    ?? URL(fileURLWithPath: NSTemporaryDirectory())
                env["NUMBA_CACHE_DIR"] = caches.appendingPathComponent("ScribeFlow/numba").path
                return BackendRuntime(python: python, environment: env)
            }
        }
        throw BackendRuntimeError.notFound
    }
}
