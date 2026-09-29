import AppKit
import SwiftUI

@main
struct ScribeFlowApp: App {
    @State private var model = AppModel()

    init() {
        Preferences.registerDefaults()
    }

    var body: some Scene {
        WindowGroup("ScribeFlow") {
            ContentView()
                .environment(model)
                .frame(minWidth: 680, minHeight: 620)
        }
        .defaultSize(width: 760, height: 780)
        .commands {
            CommandGroup(after: .newItem) {
                Button("打开 PDF…") { model.choosePDF() }
                    .keyboardShortcut("o")
                    .disabled(model.progress.isActive)
                Button("重新生成已有结果…") { model.chooseOutputToReprocess() }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                    .disabled(model.progress.isActive)
            }
        }

        Settings {
            SettingsView()
        }
    }
}
