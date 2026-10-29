import Foundation

/// A bounded display-only transport. Never contains application documents or credentials.
struct WatchValueSnapshot: Codable {
    var updatedAt: Date
    var values: [String: WidgetValueRecord]
    static let maximumBytes = 60_000
    static let maximumValues = 16

    /// Keep the current publication and fold counter when bounding the transport.
    /// Character limits alone do not bound UTF-8 (a grapheme can contain many scalars).
    mutating func include(name: String, record: WidgetValueRecord, now: Date = Date()) throws {
        var candidate = self
        candidate.values[name] = record
        candidate.updatedAt = max(now, updatedAt.addingTimeInterval(0.001))
        while true {
            let bytes = try JSONEncoder().encode(candidate).count
            if candidate.values.count <= Self.maximumValues, bytes <= Self.maximumBytes { break }
            guard let oldest = candidate.values.filter({ $0.key != "DuoFoldCount" && $0.key != name })
                .min(by: { left, right in
                    left.value.updatedAt == right.value.updatedAt ? left.key < right.key : left.value.updatedAt < right.value.updatedAt
                })?.key else { throw WidgetValueStore.StoreError.oversizedContent }
            candidate.values.removeValue(forKey: oldest)
        }
        // Do not mutate the caller's snapshot if the incoming record itself is invalid.
        _ = try Self.decode(JSONEncoder().encode(candidate))
        self = candidate
    }

    static func decode(_ data: Data) throws -> Self {
        guard data.count <= maximumBytes else { throw WidgetValueStore.StoreError.invalidRecord }
        let snapshot = try JSONDecoder().decode(Self.self, from: data)
        guard snapshot.updatedAt.timeIntervalSinceReferenceDate.isFinite,
              snapshot.values.count <= maximumValues,
              snapshot.values.allSatisfy({ name, record in
                  !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && name.count <= 64 &&
                  record.title.count <= 64 && record.value.count <= 512 &&
                  record.updatedAt.timeIntervalSinceReferenceDate.isFinite
              }) else { throw WidgetValueStore.StoreError.invalidRecord }
        return snapshot
    }

    static func read(from url: URL) throws -> Self? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        guard try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0 <= maximumBytes else {
            throw WidgetValueStore.StoreError.invalidRecord
        }
        return try decode(Data(contentsOf: url))
    }

    /// Called on the receiver's serial queue. Delayed transfers must not roll back the display.
    static func receive(_ data: Data, at url: URL) throws -> Self? {
        let incoming = try decode(data)
        if let previous = try? read(from: url), incoming.updatedAt <= previous.updatedAt { return nil }
        try incoming.save(to: url)
        return incoming
    }

    func save(to url: URL) throws {
        let data = try JSONEncoder().encode(self)
        _ = try Self.decode(data)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        #if os(iOS)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #else
        try data.write(to: url, options: .atomic)
        #endif
    }
}
