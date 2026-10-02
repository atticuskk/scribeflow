import AppKit
import SwiftUI

@main
struct ScribeFlowApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    init() {
        Preferences.registerDefaults()
    }

    var body: some Scene {
        WindowGroup("ScribeFlow") {
            ContentView()
                .environment(appDelegate.model)
                .frame(minWidth: 680, minHeight: 620)
        }
        .defaultSize(width: 760, height: 780)
        .commands {
            CommandGroup(after: .newItem) {
                Button("打开 PDF…") { appDelegate.model.choosePDF() }
                    .keyboardShortcut("o")
                    .disabled(appDelegate.model.progress.isActive)
                Button("重新生成已有结果…") { appDelegate.model.chooseOutputToReprocess() }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                    .disabled(appDelegate.model.progress.isActive)
            }
        }

        Settings {
            SettingsView()
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel()

    /// 转换进行中直接退出会让后端和 MinerU 留在后台占用内存：先停止任务（进度会保存），等后端退出后再退出。
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        let waiting = model.stopBeforeQuit { sender.reply(toApplicationShouldTerminate: true) }
        return waiting ? .terminateLater : .terminateNow
    }
}
