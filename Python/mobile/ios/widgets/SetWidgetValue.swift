import AppIntents
import ExtensionFoundation
import WidgetKit

struct SetWidgetValue: AppIntent {
    static var title: LocalizedStringResource = "Set Widget Value"
    static var description = IntentDescription(
        "Display a number or short text in a Logistics widget without opening Logistics. Use the same name in the action and widget."
    )
    static var openAppWhenRun: Bool = false
    // Only explicit, non-sensitive display values belong here. No app credentials are accessed.
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    @Parameter(title: "Name", default: "DuoFoldCount") var name: String
    @Parameter(title: "Value") var value: String
    @Parameter(title: "Title", default: "Folds") var label: String

    static var parameterSummary: some ParameterSummary {
        Summary("Set widget \(\.$name) to \(\.$value)") {
            \.$label
        }
    }

    func perform() async throws -> some IntentResult {
        let store = try WidgetValueStore(appGroup: LogisticsWidgetSettings.appGroup)
        if try store.set(name: LogisticsWidgetSettings.storageName(name), title: label, value: value) {
            WidgetCenter.shared.reloadTimelines(ofKind: LogisticsWidgetSettings.kind)
        }
        // Persist a Watch snapshot too; the following Sync action sends it from the phone app.
        await WatchValuePublisher.shared.publish(name: name)
        return .result()
    }
}

// Compiled only into this native extension, never the Python application target.
@main
struct LogisticsWidgetActions: AppIntentsExtension {}
