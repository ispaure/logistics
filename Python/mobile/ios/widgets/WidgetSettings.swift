enum LogisticsWidgetSettings {
    static let appGroup = "group.io.github.ispaure.logisticsmobile"
    static let kind = "LogisticsValueWidget"

    // Keep widgets/actions created with the original default working after updates.
    static func storageName(_ name: String) -> String {
        name == "folds" ? "DuoFoldCount" : name
    }
}
