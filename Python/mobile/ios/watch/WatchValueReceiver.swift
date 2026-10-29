import Foundation
import WatchConnectivity
import WatchKit
import WidgetKit
import SwiftUI
import os

enum WatchValueStorage {
    static func location() throws -> URL {
        try WidgetValueStore(appGroup: LogisticsWidgetSettings.appGroup).directory.appendingPathComponent("watch.json")
    }
}

final class WatchValueReceiver: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = WatchValueReceiver()
    @Published private(set) var snapshot: WatchValueSnapshot?
    @Published private(set) var status: String?
    private let queue = DispatchQueue(label: "Logistics.watch-receiver")
    private var pendingTasks = Set<WKWatchConnectivityRefreshBackgroundTask>()
    private var observation: NSKeyValueObservation?
    // Only a foreground/user request should wake the phone. Background deliveries need no reply.
    private var refreshPending = false
    private let logger = Logger(subsystem: "io.github.ispaure.logisticsmobile.watchkitapp", category: "values")

    override init() {
        super.init()
        do { snapshot = try WatchValueSnapshot.read(from: WatchValueStorage.location()) }
        catch { status = "Saved value unavailable. Refresh from your iPhone." }
    }

    func start() {
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        session.delegate = self
        observation = session.observe(\.hasContentPending, options: [.new]) { _, _ in
            self.queue.async { self.completeTasks() }
        }
        session.activate()
    }

    func refresh() {
        queue.async {
            let session = WCSession.default
            guard session.activationState == .activated else {
                self.refreshPending = true
                session.activate()
                return
            }
            self.refreshPending = false
            // A Watch-originated message can wake the paired iPhone in the background.
            session.sendMessage(["requestValues": true], replyHandler: { reply in
                self.receive(reply)
            }, errorHandler: { _ in
                DispatchQueue.main.async { self.status = "iPhone unavailable. Showing the last received value." }
            })
        }
    }

    private func receive(_ payload: [String: Any]) {
        queue.async {
            defer { self.completeTasks() }
            guard let data = payload["values"] as? Data else { return }
            do {
                let url = try WatchValueStorage.location()
                let incoming = try WatchValueSnapshot.receive(data, at: url)
                DispatchQueue.main.async { self.status = nil }
                guard let incoming else { return }
                WidgetCenter.shared.reloadTimelines(ofKind: LogisticsWidgetSettings.kind)
                DispatchQueue.main.async { self.snapshot = incoming; self.status = nil }
            } catch {
                self.logger.error("Could not receive Watch values: \(error.localizedDescription, privacy: .public)")
                DispatchQueue.main.async { self.status = "Could not save the update. Refresh to try again." }
            }
        }
    }

    func handle(_ tasks: Set<WKRefreshBackgroundTask>) {
        queue.async {
            for task in tasks {
                if let connectivity = task as? WKWatchConnectivityRefreshBackgroundTask {
                    self.pendingTasks.insert(connectivity)
                } else { task.setTaskCompletedWithSnapshot(false) }
            }
            self.completeTasks()
        }
    }

    private func completeTasks() {
        guard WCSession.default.activationState == .activated, !WCSession.default.hasContentPending else { return }
        pendingTasks.forEach { $0.setTaskCompletedWithSnapshot(false) }
        pendingTasks.removeAll()
    }

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        receive(session.receivedApplicationContext)
        queue.async {
            if activationState == .activated, self.refreshPending { self.refresh() }
        }
    }
    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) { receive(applicationContext) }
    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) { receive(message) }
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) { receive(userInfo) }
}

final class WatchApplicationDelegate: NSObject, WKApplicationDelegate {
    func applicationDidFinishLaunching() { WatchValueReceiver.shared.start() }
    func handle(_ backgroundTasks: Set<WKRefreshBackgroundTask>) { WatchValueReceiver.shared.handle(backgroundTasks) }
}
