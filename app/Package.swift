// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "ScribeFlow",
    defaultLocalization: "zh-Hans",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "ScribeFlow", targets: ["ScribeFlow"]),
        .library(name: "ScribeFlowCore", targets: ["ScribeFlowCore"]),
    ],
    targets: [
        // 与界面无关的逻辑：事件协议、命令构造、进程管理、进度状态。可在命令行单独测试。
        .target(name: "ScribeFlowCore"),
        .executableTarget(name: "ScribeFlow", dependencies: ["ScribeFlowCore"]),
        .testTarget(
            name: "ScribeFlowCoreTests",
            dependencies: ["ScribeFlowCore"],
            resources: [.copy("Resources")]
        ),
    ]
)
