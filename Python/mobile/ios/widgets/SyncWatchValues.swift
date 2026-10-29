import AppIntents

/// Compiled only into the containing iPhone app: Watch Connectivity needs that process.
@available(iOS 17.0, *)
struct SyncWidgetValuesToWatch: AppIntent {
    static var title: LocalizedStringResource = "Sync Widget Values to Watch"
    static var description = IntentDescription(
        "Send saved Shortcut widget values to your paired Apple Watch. Place after Set Widget Value."
    )
    static var openAppWhenRun: Bool = false
    static var authenticationPolicy: IntentAuthenticationPolicy = .alwaysAllowed

    @available(iOS 27.0, *)
    static var allowedExecutionTargets: IntentExecutionTargets { .main }

    func perform() async throws -> some IntentResult {
        // Import the existing fold snapshot too, without incrementing its authoritative counter.
        await WatchValuePublisher.shared.publish(name: "DuoFoldCount")
        await WatchValuePublisher.shared.sendLatest()
        return .result()
    }
}
