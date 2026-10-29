// TEST_STAGE = TestStage.EXTENDED
import Foundation

@main
struct WatchValueSnapshotChecks {
    static func main() throws {
        func check(_ condition: Bool) { precondition(condition) }
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let url = root.appendingPathComponent("watch.json")
        check(try WatchValueSnapshot.read(from: url) == nil)
        let date = Date(timeIntervalSince1970: 1000)
        let record = WidgetValueRecord(title: "Folds", value: "1234", updatedAt: date)
        let snapshot = WatchValueSnapshot(updatedAt: date, values: ["DuoFoldCount": record])
        try snapshot.save(to: url)
        let reopened = try WatchValueSnapshot.read(from: url)!
        precondition(reopened.values["DuoFoldCount"] == record)
        precondition(reopened.updatedAt == date)
        // Explicit empty values must survive transport, including non-ASCII custom names.
        let empty = WatchValueSnapshot(updatedAt: date, values: ["温度": .init(title: "", value: "", updatedAt: date)])
        try empty.save(to: url)
        check(try WatchValueSnapshot.read(from: url)!.values["温度"]!.value == "")
        func rejected(_ body: () throws -> Void) {
            do { try body(); fatalError("Invalid snapshot was accepted") } catch {}
        }
        rejected { _ = try WatchValueSnapshot.decode(Data(repeating: 0, count: 60_001)) }
        rejected { _ = try WatchValueSnapshot.decode(Data("broken".utf8)) }
        rejected { try WatchValueSnapshot(updatedAt: date, values: [" ": record]).save(to: url) }
        rejected { try WatchValueSnapshot(updatedAt: date, values: [String(repeating: "n", count: 65): record]).save(to: url) }
        rejected { try WatchValueSnapshot(updatedAt: date, values: ["x": .init(title: "", value: String(repeating: "v", count: 513), updatedAt: date)]).save(to: url) }
        rejected { try WatchValueSnapshot(updatedAt: date, values: Dictionary(uniqueKeysWithValues: (0..<17).map { ("\($0)", record) })).save(to: url) }
        // Rejected writes preserve the last valid cached value.
        check(try WatchValueSnapshot.read(from: url)!.values["温度"]!.value == "")
        let next = WatchValueSnapshot(updatedAt: date.addingTimeInterval(1), values: ["DuoFoldCount": record])
        check(try WatchValueSnapshot.receive(JSONEncoder().encode(next), at: url) != nil)
        check(try WatchValueSnapshot.receive(JSONEncoder().encode(snapshot), at: url) == nil)
        check(try WatchValueSnapshot.receive(JSONEncoder().encode(next), at: url) == nil)
        check(try WatchValueSnapshot.read(from: url)!.values["DuoFoldCount"] == record)
        // A newer explicit counter reset is valid; counts themselves do not determine ordering.
        let reset = WatchValueSnapshot(updatedAt: date.addingTimeInterval(2), values: ["DuoFoldCount": .init(title: "Folds", value: "0", updatedAt: date)])
        check(try WatchValueSnapshot.receive(JSONEncoder().encode(reset), at: url) != nil)
        check(try WatchValueSnapshot.read(from: url)!.values["DuoFoldCount"]!.value == "0")
        try Data("broken".utf8).write(to: url)
        check(try WatchValueSnapshot.receive(JSONEncoder().encode(reset), at: url) != nil)
        // Every individual record is valid, but a collection can exceed the transport byte limit.
        let richValue = String(repeating: "a" + String(repeating: "\u{0301}", count: 7), count: 512)
        let richStore = WidgetValueStore(container: root.appendingPathComponent("rich"))
        try richStore.set(name: "rich", title: "Large value", value: richValue, now: date)
        check(try richStore.read(name: "rich")!.value == richValue)
        var bounded = snapshot
        for index in 0..<12 {
            let name = "custom\(index)"
            let largeRecord = WidgetValueRecord(title: "Large value", value: richValue,
                                                updatedAt: date.addingTimeInterval(Double(index)))
            try bounded.include(name: name, record: largeRecord, now: date)
            check(bounded.values[name] == largeRecord)
            check(bounded.values["DuoFoldCount"] == record)
            check(try JSONEncoder().encode(bounded).count <= WatchValueSnapshot.maximumBytes)
        }
        check(bounded.values["custom0"] == nil)
        check(bounded.values.count < 13)
        for index in 0..<20 {
            try bounded.include(name: "small\(index)", record: record, now: date)
        }
        check(bounded.values.count == WatchValueSnapshot.maximumValues)
        check(bounded.values["DuoFoldCount"] == record)
        check(bounded.values["small19"] == record)
        print("Watch snapshot round-trip, empty values, limits and invalid-input checks passed")
    }
}
