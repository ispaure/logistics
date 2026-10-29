import AppIntents
import SwiftUI
import WidgetKit

struct SelectWatchValue: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Widget Value"
    static var description = IntentDescription("Use the same name as Set Widget Value on your iPhone.")
    @Parameter(title: "Name", default: "DuoFoldCount") var name: String
}

struct WatchValueEntry: TimelineEntry {
    let date: Date
    let name: String
    let record: WidgetValueRecord?
}

struct WatchValueProvider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> WatchValueEntry {
        WatchValueEntry(date: Date(), name: "DuoFoldCount", record: WidgetValueRecord(title: "Folds", value: "25", updatedAt: Date()))
    }
    func snapshot(for configuration: SelectWatchValue, in context: Context) async -> WatchValueEntry {
        context.isPreview ? placeholder(in: context) : entry(configuration.name)
    }
    func timeline(for configuration: SelectWatchValue, in context: Context) async -> Timeline<WatchValueEntry> {
        Timeline(entries: [entry(configuration.name)], policy: .never)
    }
    func recommendations() -> [AppIntentRecommendation<SelectWatchValue>] {
        [AppIntentRecommendation(intent: SelectWatchValue(), description: "Folds")]
    }
    private func entry(_ name: String) -> WatchValueEntry {
        let container = try? WidgetValueStore(appGroup: LogisticsWidgetSettings.appGroup)
        let snapshot = container.flatMap { try? WatchValueSnapshot.read(from: $0.directory.appendingPathComponent("watch.json")) }
        return WatchValueEntry(date: Date(), name: LogisticsWidgetSettings.storageName(name),
                               record: snapshot?.values[LogisticsWidgetSettings.storageName(name)])
    }
}

struct WatchValueFace: View {
    @Environment(\.widgetFamily) var family
    let entry: WatchValueEntry
    private var title: String {
        if let title = entry.record?.title, !title.isEmpty { return title }
        return entry.name == "DuoFoldCount" ? "Folds" : entry.name
    }
    private var value: String {
        guard let value = entry.record?.value, !value.isEmpty else { return "—" }
        return value
    }
    var body: some View {
        Group {
            switch family {
            case .accessoryInline:
                Text("\(title): \(value)")
            case .accessoryCircular:
                VStack(spacing: 0) {
                    Text(title).font(.caption2)
                    Text(value).font(.headline).minimumScaleFactor(0.4)
                }
            default:
                VStack(alignment: .leading) {
                    Text(title).font(.caption)
                    Text(value).font(.title2).minimumScaleFactor(0.4)
                    if entry.record == nil { Text("Open Logistics to sync").font(.caption2) }
                }
            }
        }.lineLimit(1).privacySensitive().containerBackground(.background, for: .widget)
    }
}

@main
struct LogisticsWatchWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: LogisticsWidgetSettings.kind, intent: SelectWatchValue.self,
                               provider: WatchValueProvider()) { WatchValueFace(entry: $0) }
            .configurationDisplayName("Shortcut Value")
            .description("Your fold count or another value published by iPhone Shortcuts.")
            .supportedFamilies([.accessoryInline, .accessoryCircular, .accessoryRectangular])
    }
}
