import SwiftUI
import WatchKit

@main
struct LogisticsWatchApp: App {
    @WKApplicationDelegateAdaptor(WatchApplicationDelegate.self) var delegate
    @StateObject private var receiver = WatchValueReceiver.shared
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if let snapshot = receiver.snapshot, !snapshot.values.isEmpty {
                            ForEach(snapshot.values.keys.sorted { left, right in
                                if left == "DuoFoldCount" { return right != left }
                                if right == "DuoFoldCount" { return false }
                                return left < right
                            }, id: \.self) { name in
                                if let record = snapshot.values[name] {
                                    VStack(alignment: .leading) {
                                        Text(record.title.isEmpty ? name : record.title).font(.headline)
                                        Text(record.value.isEmpty ? "—" : record.value)
                                            .font(.system(.largeTitle, design: .rounded)).minimumScaleFactor(0.5)
                                            .lineLimit(3).privacySensitive()
                                        Text(record.updatedAt, style: .relative).font(.caption2).foregroundStyle(.secondary)
                                    }.accessibilityElement(children: .combine)
                                }
                            }
                        } else {
                            Text("No values yet").font(.headline)
                            Text("Run your fold counter or Set Widget Value on your iPhone, then refresh.").font(.caption)
                        }
                        if let status = receiver.status { Text(status).font(.caption) }
                        Button("Refresh from iPhone", systemImage: "arrow.clockwise") { receiver.refresh() }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal)
                }.navigationTitle("Logistics")
            }.onChange(of: phase, initial: true) { _, phase in if phase == .active { receiver.refresh() } }
        }
    }
}
