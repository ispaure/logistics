import AppIntents
import SwiftUI
import WidgetKit

struct SelectWidgetValue: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Widget Value"
    static var description = IntentDescription("Choose the name used by Set Widget Value in Shortcuts.")
    @Parameter(title: "Name", default: "DuoFoldCount") var name: String
}

struct ValueEntry: TimelineEntry {
    let date: Date
    let record: WidgetValueRecord?
    let failed: Bool
}

struct ValueProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> ValueEntry {
        ValueEntry(date: Date(), record: WidgetValueRecord(title: "Folds", value: "25", updatedAt: Date()), failed: false)
    }

    func snapshot(for configuration: SelectWidgetValue, in context: Context) async -> ValueEntry {
        if context.isPreview { return placeholder(in: context) }
        return entry(name: configuration.name)
    }

    func timeline(for configuration: SelectWidgetValue, in context: Context) async -> Timeline<ValueEntry> {
        // No periodic work: an explicit Set Widget Value action requests a refresh.
        Timeline(entries: [entry(name: configuration.name)], policy: .never)
    }

    private func entry(name: String) -> ValueEntry {
        do {
            let store = try WidgetValueStore(appGroup: LogisticsWidgetSettings.appGroup)
            let key = LogisticsWidgetSettings.storageName(name)
            let record = try store.read(name: key) ?? (key == "DuoFoldCount" ? store.read(name: "folds") : nil)
            return ValueEntry(date: Date(), record: record, failed: false)
        } catch {
            return ValueEntry(date: Date(), record: nil, failed: true)
        }
    }
}

@main
struct LogisticsValueWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: LogisticsWidgetSettings.kind, intent: SelectWidgetValue.self,
                               provider: ValueProvider()) { entry in
            WidgetValueView(title: entry.record?.title ?? "Widget Value",
                            value: entry.record?.value ?? "—",
                            detail: entry.record == nil
                                ? (entry.failed ? "Value unavailable. Run Set Widget Value again." : "Set a value from Shortcuts to get started.")
                                : nil)
                .containerBackground(.background, for: .widget)
                .privacySensitive()
        }
        .configurationDisplayName("Shortcut Value")
        .description("A number or short text saved by your Shortcuts automation.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
