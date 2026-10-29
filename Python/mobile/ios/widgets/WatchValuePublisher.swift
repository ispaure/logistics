import Foundation
#if !LOGISTICS_WIDGET_ACTIONS
import WatchConnectivity
#endif
import os
import Darwin

/// Used by the Shortcuts extension and by the native iPhone lifecycle bridge.
@objc(LogisticsWatchValuePublisher)
final class WatchValuePublisher: NSObject, @unchecked Sendable {
    static let shared = WatchValuePublisher()
    #if !LOGISTICS_WIDGET_ACTIONS
    private let queue = DispatchQueue(label: "Logistics.watch-values")
    private var waiters: [UUID: CheckedContinuation<Void, Never>] = [:]
    #endif
    private let logger = Logger(subsystem: "io.github.ispaure.logisticsmobile", category: "watch-values")
    private static let notification = "io.github.ispaure.logisticsmobile.watch-values" as CFString

    private func snapshot() throws -> WatchValueSnapshot {
        let store = try WidgetValueStore(appGroup: LogisticsWidgetSettings.appGroup)
        return (try? WatchValueSnapshot.read(from: store.directory.appendingPathComponent("watch.json"))) ??
            WatchValueSnapshot(updatedAt: .distantPast, values: [:])
    }

    // All phone processes read-and-send under the same lock, preventing an older
    // extension publication from replacing newer state sent by the containing app.
    private func locked(_ body: (WidgetValueStore) throws -> Void) throws {
        let store = try WidgetValueStore(appGroup: LogisticsWidgetSettings.appGroup)
        try FileManager.default.createDirectory(at: store.directory, withIntermediateDirectories: true)
        let fd = open(store.directory.appendingPathComponent("watch.lock").path, O_CREAT | O_RDWR, 0o600)
        guard fd >= 0 else { throw WidgetValueStore.StoreError.containerUnavailable }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else { throw WidgetValueStore.StoreError.containerUnavailable }
        defer { flock(fd, LOCK_UN) }
        try body(store)
    }

    /// Persist first, even if the Watch is absent. A later launch retries the latest snapshot.
    func publish(name: String) async {
        do {
            try locked { store in
                var saved = try snapshot()
                let key = LogisticsWidgetSettings.storageName(name)
                let record = try store.read(name: key) ?? (key == "DuoFoldCount" ? store.read(name: "folds") : nil)
                if let record, saved.values[key] != record {
                    try saved.include(name: key, record: record)
                    try saved.save(to: store.directory.appendingPathComponent("watch.json"))
                }
            }
        } catch {
            logger.error("Could not prepare Watch values: \(error.localizedDescription, privacy: .public)")
            return
        }
        CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(),
                                             CFNotificationName(Self.notification), nil, nil, true)
        #if !LOGISTICS_WIDGET_ACTIONS
        await sendLatest()
        #endif
    }

    #if !LOGISTICS_WIDGET_ACTIONS
    func sendLatest() async {
        guard WCSession.isSupported() else { return }
        // Await activation while the intent is alive, with a bounded wait if connectivity is unavailable.
        await withCheckedContinuation { continuation in
            queue.async {
                let id = UUID()
                self.waiters[id] = continuation
                let session = WCSession.default
                session.delegate = self
                if session.activationState == .activated {
                    self.send(session)
                    self.finish()
                } else {
                    session.activate()
                    self.queue.asyncAfter(deadline: .now() + 3) {
                        self.waiters.removeValue(forKey: id)?.resume()
                    }
                }
            }
        }
    }

    private func finish() {
        let pending = waiters
        waiters.removeAll()
        pending.values.forEach { $0.resume() }
    }

    private func send(_ session: WCSession) {
        guard session.activationState == .activated, session.isPaired, session.isWatchAppInstalled else { return }
        do {
            try locked { _ in
                let saved = try snapshot()
                guard !saved.values.isEmpty else { return }
                let encoder = JSONEncoder()
                encoder.outputFormatting = .sortedKeys
                let data = try encoder.encode(saved)
                guard (session.applicationContext["values"] as? Data) != data else { return }
                try session.updateApplicationContext(["values": data])
                // Coalesce the display-only background queue; keep the most recent total, not every fold.
                for transfer in session.outstandingUserInfoTransfers where transfer.userInfo["logisticsValues"] as? Bool == true {
                    transfer.cancel()
                }
                session.transferUserInfo(["logisticsValues": true, "values": data])
                // Foreground delivery improves the open Watch app; background context remains authoritative.
                if session.isReachable { session.sendMessage(["values": data], replyHandler: nil, errorHandler: nil) }
            }
        } catch {
            logger.error("Watch values remain pending: \(error.localizedDescription, privacy: .public)")
        }
    }

    @objc static func start() {
        CFNotificationCenterAddObserver(CFNotificationCenterGetDarwinNotifyCenter(), nil, { _, _, _, _, _ in
            Task { await WatchValuePublisher.shared.sendLatest() }
        }, notification, nil, .deliverImmediately)
        retry()
    }

    @objc static func retry() {
        Task {
            await shared.publish(name: "DuoFoldCount")
            // Keep the phone session usable even if importing an old fold record failed.
            await shared.sendLatest()
        }
    }

    #endif
}

#if !LOGISTICS_WIDGET_ACTIONS
extension WatchValuePublisher: WCSessionDelegate {
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        queue.async { self.send(session); self.finish() }
    }
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { session.activate() }
    func sessionWatchStateDidChange(_ session: WCSession) { queue.async { self.send(session) } }
    func session(_ session: WCSession, didReceiveMessage message: [String: Any], replyHandler: @escaping ([String: Any]) -> Void) {
        do { replyHandler(["values": try JSONEncoder().encode(snapshot())]) }
        catch { replyHandler([:]) }
    }
}

#endif
