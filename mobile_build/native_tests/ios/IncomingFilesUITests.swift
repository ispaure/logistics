// TEST_STAGE = TestStage.EXTENDED
import UIKit
import XCTest

final class IncomingFilesUITests: XCTestCase {
    private enum FilesLifecycle: String {
        case cold
        case warm
        case resume
    }

    private let sender = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsincomingsender")
    private let receiver = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsinboxqa")
    private let targetName = "Logisticks"
    private var deviceLabel: String {
        UIDevice.current.userInterfaceIdiom == .pad ? "On My Tablet" : "On My Phone"
    }

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testOpenInActivatesMainApp() {
        stopReceiver()
        launchSender()
        sender.buttons["Open fixture in app"].tap()

        let targets = sender.descendants(matching: .any).matching(NSPredicate(
            format: "label == %@ OR label == %@", targetName, "Open in \(targetName)"
        ))
        let target = targets.firstMatch
        let offered = target.waitForExistence(timeout: 15)
        capture("open-in-menu", apps: [sender])
        XCTAssertTrue(offered, "iOS offered no Logisticks destination in the Open In menu")

        let selected = targets.matching(NSPredicate(
            format: "NOT identifier IN %@", ["shareCell", "cellTitleLabel"]
        )).firstMatch
        let mainOffered = selected.exists
        addText("open-in-selection", mainOffered ? selected.debugDescription : target.debugDescription)
        XCTAssertTrue(mainOffered, "The document interaction menu offered only the Logisticks Share extension")
        selected.tap()

        let activated = receiver.wait(for: .runningForeground, timeout: 25)
        capture("open-in-after-selection", apps: activated ? [receiver] : [sender])
        addText("open-in-app-state", "receiver: \(receiver.state); sender: \(sender.state)")
        XCTAssertTrue(activated, "The OS selection did not activate the Logisticks main app")
    }

    func testShareExtensionReceivesTwoFiles() {
        stopReceiver()
        launchSender()
        sender.buttons["Share fixture files"].tap()
        selectShareExtension()
        assertShareResult(count: 2)
        sender.buttons["Done"].firstMatch.tap()
    }

    func testFilesOpenWithActivatesMainApp() {
        if UIDevice.current.userInterfaceIdiom == .pad {
            openFilesWithIPadWindows()
            return
        }
        openFromFiles(folder: "files-open", name: "Files Open With café 漢字.txt",
                      marker: "Files Open With source receipt", lifecycle: .cold)
    }

    func testFilesOpenWithWarmMainApp() {
        openFromFiles(folder: "warm", name: "Warm café 漢字.txt",
                      marker: "Warm source receipt", lifecycle: .warm)
    }

    func testFilesOpenWithResumesMainApp() {
        openFromFiles(folder: "resume", name: "Resume café 漢字.txt",
                      marker: "Resume source receipt", lifecycle: .resume)
    }

    private func openFilesWithIPadWindows() {
        launchSender()
        receiver.launch()
        showAppSettings(phase: "ipad-delivery-primary")
        XCTAssertEqual(receiver.windows.count, 1, "Start with the primary workspace only")
        XCTAssertFalse(receiver.buttons["Close window"].firstMatch.exists)
        tap(receiver.buttons["New window"].firstMatch, in: receiver, checkpoint: "ipad-delivery-new-window")
        showAppSettings(phase: "ipad-delivery-secondary")
        assertIPadSettingsWindows(checkpoint: "ipad-delivery-before-files")

        let name = "Files Open With café 漢字.txt"
        let marker = "Files Open With source receipt"
        let files = openFilesMenu(folder: "files-open", name: name)
        let receiverState = receiver.state
        let filesState = files.state
        addText("ipad-delivery-before-os-selection", "receiver: \(receiverState); Files: \(filesState)")
        XCTAssertEqual(filesState, .runningForeground)
        XCTAssertTrue(isRunning(receiverState), "Both existing receiver windows require a live process")
        tap(files.buttons[targetName].firstMatch, in: files, checkpoint: "ipad-delivery-open-with-apps")
        let activated = receiver.wait(for: .runningForeground, timeout: 25)
        capture("ipad-delivery-after-os-selection", apps: activated ? [receiver] : [files])
        XCTAssertTrue(activated, "Files Open With did not foreground Logisticks")
        let delivered = ipadWindowSubtrees(checkpoint: "ipad-delivery-returned-window", count: 3)
        let active = delivered.filter { $0.hasPrefix(" (Main),") }
        XCTAssertEqual(active.count, 1)
        XCTAssertTrue(active.first.map(isIPadHomeWindow) == true,
                      "Files Open With must foreground the new Home window")
        XCTAssertTrue(receiver.buttons["Open Document"].firstMatch.isHittable,
                      "The new Home window must be interactive")
        let originalSettings = delivered.filter { !$0.hasPrefix(" (Main),") && isIPadAppSettingsWindow($0) }
        XCTAssertEqual(originalSettings.filter { hasCloseWindow($0) }.count, 1,
                       "The original secondary workspace must retain App Settings")
        XCTAssertEqual(originalSettings.filter { !hasCloseWindow($0) }.count, 1,
                       "The original primary workspace must retain App Settings")

        addText("ipad-window-delivery-proof", """
        {"schema":1,"route":"files-open-with","windows_before":2,"windows_after":3,"active_window_after_delivery":"new-home","primary_app_settings_preserved":true,"secondary_app_settings_preserved":true}
        """)
        // Scene delivery is complete. Reopen the app before using its ordinary
        // device browser; OS-generated window titles do not identify a host.
        stopReceiver()
        receiver.launch()
        openReceivedFile(name: name, marker: marker, phase: "ipad-delivery-after-restart")
        stopReceiver()
        receiver.launch()
        openReceivedFile(name: name, marker: marker, phase: "ipad-delivery-relaunched")
        addText("ipad-window-routing-proof", """
        {"schema":3,"route":"files-open-with","windows_before":2,"windows_after":3,"active_window_after_delivery":"new-home","primary_app_settings_preserved":true,"secondary_app_settings_preserved":true,"restart_before_read":true,"read_window":"primary-after-restart","opened_from_on_my_tablet":true,"reopened_from_on_my_tablet":true}
        """)
    }

    private func assertIPadSettingsWindows(checkpoint: String) {
        let windows = ipadWindowSubtrees(checkpoint: checkpoint, count: 2)
        let secondary = receiver.windows.containing(.button, identifier: "Close window")
        XCTAssertEqual(secondary.count, 1, "Only the secondary workspace should own Close window")
        XCTAssertTrue(secondary.firstMatch.buttons["Close window"].firstMatch.isHittable,
                      "The secondary workspace must be interactive")
        let main = windows.first { $0.hasPrefix(" (Main),") }
        let other = windows.first { !$0.hasPrefix(" (Main),") }
        XCTAssertTrue(main.map { isIPadAppSettingsWindow($0) && hasCloseWindow($0) } == true,
                      "The preexisting secondary workspace must be the main window")
        XCTAssertTrue(other.map { isIPadAppSettingsWindow($0) && !hasCloseWindow($0) } == true,
                       "The other window must still show the primary workspace's App Settings")
    }

    private func ipadWindowSubtrees(checkpoint: String, count: Int) -> [String] {
        let hierarchy = receiver.debugDescription
        addText(checkpoint, hierarchy)
        XCTAssertEqual(receiver.windows.count, count, "Unexpected number of Logisticks windows")
        let subtree = hierarchy.components(separatedBy: "\nPath to element:").first ?? ""
        let windows = subtree.components(separatedBy: "\n    Window").dropFirst()
        XCTAssertEqual(windows.count, count, "Unexpected number of XCTest window subtrees")
        return Array(windows)
    }

    private func isIPadAppSettingsWindow(_ window: String) -> Bool {
        window.contains("label: 'Settings', Selected")
            && window.contains("label: 'Restore last document'")
            && window.contains("label: 'New window'")
    }

    private func hasCloseWindow(_ window: String) -> Bool {
        window.contains("label: 'Close window'")
    }

    private func isIPadHomeWindow(_ window: String) -> Bool {
        window.contains("label: 'Home', Selected") && window.contains("label: 'Open Document'")
    }

    func testInspectIPadWindowControls() throws {
        try XCTSkipUnless(UIDevice.current.userInterfaceIdiom == .pad, "This diagnostic requires an iPad")
        receiver.launch()
        showAppSettings(phase: "ipad-primary")
        let closeWindow = receiver.buttons["Close window"].firstMatch
        XCTAssertFalse(closeWindow.exists, "Run the window diagnostic with the primary workspace only")
        tap(receiver.buttons["New window"].firstMatch, in: receiver, checkpoint: "ipad-new-window")
        capture("ipad-after-new-window", apps: [receiver])

        showAppSettings(phase: "ipad-secondary")
        let secondaryVisible = closeWindow.waitForExistence(timeout: 20)
        capture("ipad-secondary-window-controls", apps: [receiver])
        XCTAssertTrue(secondaryVisible && closeWindow.isHittable,
                      "The new window must expose the secondary workspace's Close window action")

        _ = captureIPadSystemWindowMenu()
    }

    private func captureIPadSystemWindowMenu() -> XCUIApplication {
        XCUIDevice.shared.press(.home)
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let appIcon = springboard.icons[targetName].firstMatch
        let iconVisible = appIcon.waitForExistence(timeout: 10)
        capture("ipad-home-window-controls", apps: [springboard])
        XCTAssertTrue(iconVisible && appIcon.isHittable, "The installed Logisticks Home Screen icon is unavailable")
        appIcon.press(forDuration: 0.75)
        capture("ipad-system-app-menu", apps: [springboard])
        return springboard
    }

    private func showAppSettings(phase: String) {
        let tab = receiver.tabBars.buttons["Settings"].firstMatch
        let settings = receiver.buttons["Settings"].firstMatch
        let close = receiver.buttons["Close document"].firstMatch
        let deadline = Date().addingTimeInterval(35)
        while !tab.exists && !settings.exists && !close.exists && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.25)
        }
        if !tab.exists && close.exists && close.isHittable {
            tap(close, in: receiver, checkpoint: "\(phase)-close-reader")
            _ = tab.waitForExistence(timeout: 12)
        }
        tap(tab.exists && tab.isHittable ? tab : settings, in: receiver, checkpoint: "\(phase)-settings")
        tap(receiver.buttons["App"].firstMatch, in: receiver, checkpoint: "\(phase)-app-settings")
    }

    func testDismissShareChooser() {
        stopReceiver()
        launchSender()
        sender.buttons["Share fixture files"].tap()
        let target = shareExtensionCell()
        let offered = target.waitForExistence(timeout: 15)
        capture("chooser-before-dismiss", apps: [sender])
        XCTAssertTrue(offered, "The system chooser must be visible before dismissal")
        let backdrop = sender.otherElements["PopoverDismissRegion"].firstMatch
        let popover = sender.popovers.firstMatch
        XCTAssertTrue(backdrop.exists && popover.exists, "The system chooser has no accessible dismissal backdrop")
        let regions = backdrop.frame
        let menu = popover.frame
        let points = [
            CGPoint(x: regions.midX, y: regions.minY + 0.15 * regions.height),
            CGPoint(x: regions.midX, y: regions.maxY - 0.15 * regions.height),
            CGPoint(x: regions.minX + 0.1 * regions.width, y: regions.midY),
            CGPoint(x: regions.maxX - 0.1 * regions.width, y: regions.midY),
        ]
        let outside = points.first { !menu.insetBy(dx: -12, dy: -12).contains($0) }
        guard let outside else {
            XCTFail("The chooser fills the available dismissal backdrop")
            return
        }
        let offset = CGVector(dx: (outside.x - regions.minX) / regions.width,
                              dy: (outside.y - regions.minY) / regions.height)
        backdrop.coordinate(withNormalizedOffset: offset).tap()
        XCTAssertTrue(target.waitForNonExistence(timeout: 15), "The Share chooser stayed visible")
        XCTAssertEqual(receiver.state, .notRunning)
        XCTAssertTrue(sender.buttons["Share fixture files"].firstMatch.isHittable)
        capture("chooser-after-dismiss", apps: [sender])
    }

    private func openFromFiles(folder: String, name: String, marker: String, lifecycle: FilesLifecycle) {
        var initialProcess: String?
        if lifecycle == .cold {
            stopReceiver()
        }
        launchSender()
        if lifecycle != .cold {
            receiver.launch()
            XCTAssertEqual(receiver.state, .runningForeground)
            initialProcess = foregroundReceiverPID(checkpoint: "\(folder)-receiver-initial-process")
            XCTAssertNotNil(initialProcess, "XCTest did not identify the initial receiver process")
            if lifecycle == .resume {
                XCUIDevice.shared.press(.home)
                let suspended = receiver.wait(for: .runningBackgroundSuspended, timeout: 35)
                addText("\(folder)-receiver-after-home", String(describing: receiver.state))
                XCTAssertTrue(suspended, "The receiver must suspend before the background-resume action")
            }
        }
        let files = openFilesMenu(folder: folder, name: name)
        let state = receiver.state
        XCTAssertEqual(files.state, .runningForeground)
        addText("\(folder)-receiver-before-os-selection", "lifecycle: \(lifecycle.rawValue); receiver: \(state)")
        switch lifecycle {
        case .cold:
            XCTAssertEqual(state, .notRunning)
        case .warm:
            XCTAssertTrue(state == .runningBackground || state == .runningBackgroundSuspended,
                          "The warm receiver process must still exist behind Files")
        case .resume:
            XCTAssertEqual(state, .runningBackgroundSuspended)
        }
        tap(files.buttons[targetName].firstMatch, in: files, checkpoint: "files-open-with-apps")
        let activated = receiver.wait(for: .runningForeground, timeout: 25)
        capture("files-after-open-with", apps: activated ? [receiver] : [files])
        addText("files-open-app-state", "receiver: \(receiver.state); Files: \(files.state)")
        XCTAssertTrue(activated, "Files Open With did not bring the Logisticks main app to foreground")
        let deliveredProcess = foregroundReceiverPID(checkpoint: "\(folder)-receiver-delivery-process")
        XCTAssertNotNil(deliveredProcess, "XCTest did not identify the foreground receiver process")
        if let initialProcess {
            XCTAssertEqual(deliveredProcess, initialProcess, "The warm delivery must retain the receiver process")
        }
        openReceivedFile(name: name, marker: marker, phase: "\(folder)-initial")
        stopReceiver()
        receiver.launch()
        openReceivedFile(name: name, marker: marker, phase: "\(folder)-relaunched")
    }

    private func openFilesMenu(folder: String, name: String) -> XCUIApplication {
        let files = XCUIApplication(bundleIdentifier: "com.apple.DocumentsApp")
        files.activate()
        dismissQuickPathTutorial(in: files)
        showFilesDeviceLocation(files)
        for (name, kind) in [("Incoming Sender", "Container"), ("Intake", "Folder"), (folder, "Folder")] {
            let item = files.cells["\(name), \(kind)"].firstMatch
            let grid = files.collectionViews["File View"].firstMatch
            _ = item.waitForExistence(timeout: 20)
            for _ in 0..<3 {
                if item.exists && item.isHittable { break }
                if !grid.exists || !grid.isHittable { break }
                grid.swipeUp()
            }
            capture("files-\(name)", apps: [files])
            XCTAssertTrue(item.exists && item.isHittable, "Files could not find the \(name) \(kind)")
            // Files icon view enters inline rename when the label is tapped.
            item.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.25)).tap()
        }
        let documentNames = [name, (name as NSString).deletingPathExtension]
        let document = files.cells.containing(labels(documentNames)).firstMatch
        let present = document.waitForExistence(timeout: 20)
        capture("files-open-document", apps: [files])
        XCTAssertTrue(present && document.isHittable, "The transferred fixture must be present in Files")
        // Complete first-use keyboard onboarding before opening the context menu.
        // On a fresh simulator its tutorial can cover the menu and block XCTest idle.
        let search = files.searchFields["Search"].firstMatch
        if search.exists && search.isHittable {
            search.tap()
            dismissQuickPathTutorial(in: files, timeout: 4)
            if files.keyboards.firstMatch.exists {
                let navigation = files.navigationBars["FullDocumentManagerViewControllerNavigationBar"].firstMatch
                tap(navigation.buttons["Close"].firstMatch, in: files, checkpoint: "files-close-search")
                XCTAssertTrue(files.keyboards.firstMatch.waitForNonExistence(timeout: 8))
            }
        }
        document.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.25)).press(forDuration: 1.0)
        tap(files.buttons["Open With"].firstMatch, in: files, checkpoint: "files-context-menu")
        return files
    }

    private func foregroundReceiverPID(checkpoint: String) -> String? {
        let hierarchy = receiver.debugDescription
        guard let application = hierarchy.split(separator: "\n").first(where: { $0.contains("Application, ") }),
              let start = application.range(of: "pid: ")?.upperBound else {
            addText(checkpoint, hierarchy)
            return nil
        }
        let pid = application[start...].prefix(while: { $0.isASCII && $0.isNumber })
        addText(checkpoint, String(application))
        return pid.isEmpty ? nil : String(pid)
    }

    private func isRunning(_ state: XCUIApplication.State) -> Bool {
        [.runningForeground, .runningBackground, .runningBackgroundSuspended].contains(state)
    }

    private func showFilesDeviceLocation(_ files: XCUIApplication) {
        let location = UIDevice.current.userInterfaceIdiom == .pad ? "On My iPad" : "On My iPhone"
        let root = files.otherElements["DOC.browsingRoot Source: com.apple.FileProvider.LocalStorage, Title: \(location)"].firstMatch
        let browse = files.buttons["Browse"].firstMatch
        if !root.exists && browse.exists && browse.isHittable {
            browse.tap()
        }
        let back = files.buttons["DOC.navBarButton.backInHistory"].firstMatch
        for _ in 0..<4 {
            if root.exists || !back.exists || !back.isHittable || !back.isEnabled { break }
            back.tap()
        }
        if !root.exists {
            tap(element(in: files, label: location), in: files, checkpoint: "files-device-location")
        }
    }

    func testOpenAndReopenSharedFiles() {
        receiver.activate()
        openSharedFixtures(phase: "initial")
        stopReceiver()
        receiver.launch()
        openSharedFixtures(phase: "relaunched")
    }

    func testCancelRemainingShareFiles() {
        runHeldShare(mode: "cancel")
        let cancel = sender.buttons["Cancel remaining files"].firstMatch
        capture("cancel-provider-holding", apps: [sender])
        XCTAssertTrue(cancel.exists && cancel.isHittable, "The Share extension Cancel action is unavailable")
        print("[IncomingFiles] cancel-provider-action-start\n\(ProcessInfo.processInfo.systemUptime)")
        cancel.tap()
        signalProvider(mode: "cancel", event: "release")
        XCTAssertTrue(cancel.waitForNonExistence(timeout: 15))
        receiver.activate()
        openReceivedFile(name: "Cancel completed café 漢字.txt", marker: "Completed before cancel receipt",
                         phase: "cancel-completed", absent: "Cancel held café 漢字.txt")
    }

    func testShareProviderFailsAfterFirstFile() {
        runHeldShare(mode: "failure")
        print("[IncomingFiles] failure-provider-action-start\n\(ProcessInfo.processInfo.systemUptime)")
        signalProvider(mode: "failure", event: "release")
        assertShareResult(count: 1, failure: true)
        sender.buttons["Done"].firstMatch.tap()
        receiver.activate()
        openReceivedFile(name: "Failure completed café 漢字.txt", marker: "Completed before failure receipt",
                         phase: "provider-failure-completed", absent: "Failure held café 漢字.txt")
    }

    func testShareRetryAfterProviderFailure() {
        launchSender()
        shareOne("failure-second")
        receiver.activate()
        openReceivedFile(name: "Failure held café 漢字.txt", marker: "Held for failure receipt", phase: "provider-retry")
    }

    func testShareKeepsBothFilesWithTheSameName() {
        stopReceiver()
        launchSender()
        shareOne("duplicate-one")
        receiver.activate()
        openReceivedFile(name: "Duplicate café 漢字.txt", marker: "First duplicate source receipt", phase: "duplicate-first")
        XCTAssertEqual(receiver.state, .runningForeground)
        let initialProcess = foregroundReceiverPID(checkpoint: "duplicate-first-reader-process")
        XCTAssertNotNil(initialProcess, "XCTest did not identify the first reader process")

        // Keep the same receiver process alive while the sender offers the second file.
        sender.activate()
        addText("duplicate-after-sender-activation", "receiver: \(receiver.state); sender: \(sender.state)")
        let deadline = Date().addingTimeInterval(15)
        var receiverState = receiver.state
        var senderState = sender.state
        while !(senderState == .runningForeground && isRunning(receiverState)) && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.25)
            receiverState = receiver.state
            senderState = sender.state
        }
        addText("duplicate-before-second-share", "receiver: \(receiverState); sender: \(senderState)")
        XCTAssertEqual(senderState, .runningForeground)
        XCTAssertTrue(isRunning(receiverState), "The receiver must remain alive before the second share")
        shareOne("duplicate-two")
        receiver.activate()
        XCTAssertEqual(receiver.state, .runningForeground)
        let deliveredProcess = foregroundReceiverPID(checkpoint: "duplicate-second-share-process")
        XCTAssertNotNil(deliveredProcess, "XCTest did not identify the receiver process after the second share")
        XCTAssertEqual(deliveredProcess, initialProcess, "The second share must retain the original receiver process")
        capture("duplicate-before-reader-restart", apps: [receiver])
        stopReceiver()
        receiver.launch()
        openDuplicateFixtures(phase: "duplicate-after-restart")
        stopReceiver()
        receiver.launch()
        openDuplicateFixtures(phase: "duplicate-relaunch")
    }

    private func shareOne(_ identifier: String) {
        sender.buttons[identifier].tap()
        selectShareExtension()
        assertShareResult(count: 1)
        sender.buttons["Done"].firstMatch.tap()
    }

    private func openDuplicateFixtures(phase: String) {
        openReceivedFile(name: "Duplicate café 漢字.txt", marker: "First duplicate source receipt",
                         phase: "\(phase)-original")
        openReceivedFile(name: "Duplicate café 漢字 (1).txt", marker: "Second duplicate source receipt",
                         phase: "\(phase)-numbered")
    }

    private func openSharedFixtures(phase: String) {
        openReceivedFile(name: "Share café 漢字.txt", marker: "Share source receipt", phase: "\(phase)-share")
        openReceivedFile(name: "Share two café 漢字.txt", marker: "Second share source receipt",
                         phase: "\(phase)-share-two")
    }

    private func openReceivedFile(name: String, marker: String, phase: String, absent: String? = nil,
                                  window: XCUIElement? = nil) {
        let browser = window ?? receiver
        // On iOS this tab is a native tab-bar button. Its navigation-bar
        // counterpart can bring the folder tree back on a narrow layout.
        let tab = browser.tabBars.buttons["Workspaces"].firstMatch
        let workspaces = browser.buttons["Workspaces"].firstMatch
        let close = browser.buttons["Close document"].firstMatch
        let deadline = Date().addingTimeInterval(35)
        while !tab.exists && !workspaces.exists && !close.exists && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.25)
        }
        if !tab.exists && close.exists && close.isHittable {
            tap(close, in: receiver, checkpoint: "\(phase)-close-reader")
            _ = tab.waitForExistence(timeout: 12)
        }
        let rootBrowser = browser.navigationBars[deviceLabel].buttons["File and folder actions"].firstMatch
        if rootBrowser.exists && rootBrowser.isHittable {
            capture("\(phase)-retained-root", apps: [receiver])
        } else {
            tap(tab.exists && tab.isHittable ? tab : workspaces, in: receiver, checkpoint: "\(phase)-workspaces")
            let roots = browser.buttons.matching(labels(["\(deviceLabel), Local"]))
            // The native transition can expose the new root before it is
            // tappable; its icon and text may also be separate buttons.
            var root = firstHittable(roots, timeout: 8)
            if root == nil {
                let local = browser.buttons.matching(labels(["Local", "Local selected"])).firstMatch
                let browserBack = browser.buttons["Back to Workspaces"].firstMatch
                if !local.exists && browserBack.exists && browserBack.isHittable {
                    browserBack.tap()
                }
                tap(local, in: receiver, checkpoint: "\(phase)-local")
                let onDevice = browser.buttons.matching(labels([deviceLabel, "\(deviceLabel) selected"])).firstMatch
                tap(onDevice, in: receiver, checkpoint: "\(phase)-device-tab")
                root = firstHittable(roots, timeout: 8)
            }
            tap(root ?? roots.firstMatch, in: receiver, checkpoint: "\(phase)-root")
        }

        let row = fileRow(name, in: browser)
        if !row.waitForExistence(timeout: 12) {
            let table = browser.tables.firstMatch
            if table.exists {
                for _ in 0..<5 {
                    if row.exists && row.isHittable { break }
                    table.swipeUp()
                }
            }
        }
        if let absent {
            XCTAssertFalse(fileRow(absent, in: browser).exists, "The incomplete item was visible in the ordinary root")
        }
        tap(row, in: receiver, checkpoint: "\(phase)-file-row")
        let text = browser.textViews.matching(NSPredicate(format: "value CONTAINS %@", marker)).firstMatch
        let opened = text.waitForExistence(timeout: 25)
        capture("\(phase)-reader", apps: [receiver])
        XCTAssertTrue(opened, "The reader did not show the marker from \(name)")
        dismissQuickPathTutorial(in: receiver)
    }

    private func fileRow(_ name: String, in browser: XCUIElement) -> XCUIElement {
        browser.cells.matching(labels(["\(name). File"])).firstMatch
    }

    private func firstHittable(_ query: XCUIElementQuery, timeout: TimeInterval) -> XCUIElement? {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            if let element = query.allElementsBoundByIndex.first(where: { $0.exists && $0.isHittable }) {
                return element
            }
            Thread.sleep(forTimeInterval: 0.2)
        } while Date() < deadline
        return nil
    }

    private func labels(_ names: [String]) -> NSPredicate {
        let forms = names.flatMap { [$0.precomposedStringWithCanonicalMapping, $0.decomposedStringWithCanonicalMapping] }
        return NSPredicate(format: "label IN %@", forms)
    }

    private func runHeldShare(mode: String) {
        stopReceiver()
        launchSender()
        let requested = XCTestExpectation(description: "Source requested second representation: \(mode)")
        let checkpoint = XCTestExpectation(description: "Source acknowledged first-file checkpoint: \(mode)")
        let stopObservingRequest = observeProvider(mode: mode, event: "requested", expectation: requested)
        let stopObservingCheckpoint = observeProvider(mode: mode, event: "checkpoint-observed", expectation: checkpoint)
        defer {
            stopObservingRequest()
            stopObservingCheckpoint()
        }
        sender.buttons[mode].tap()
        selectShareExtension(heldMode: mode)
        let held = XCTWaiter.wait(for: [requested], timeout: 22)
        capture("\(mode)-second-provider-requested", apps: [sender])
        XCTAssertEqual(held, .completed, "The selected extension must request the held content representation")
        XCTAssertTrue(sender.buttons["Cancel remaining files"].firstMatch.exists)
        XCTAssertEqual(receiver.state, .notRunning)
        print("[IncomingFiles] \(mode)-provider-held-main-stopped\n\(ProcessInfo.processInfo.systemUptime)")
        let observed = XCTWaiter.wait(for: [checkpoint], timeout: 12)
        XCTAssertEqual(observed, .completed, "The source must acknowledge the saved first-file checkpoint before interruption")
    }

    private func observeProvider(mode: String, event: String, expectation: XCTestExpectation) -> () -> Void {
        let center = CFNotificationCenterGetDarwinNotifyCenter()
        let observer = Unmanaged.passUnretained(expectation).toOpaque()
        let notification = providerSignal(mode, event)
        CFNotificationCenterAddObserver(center, observer, { _, pointer, _, _, _ in
            if let pointer {
                Unmanaged<XCTestExpectation>.fromOpaque(pointer).takeUnretainedValue().fulfill()
            }
        }, notification, nil, .deliverImmediately)
        return {
            CFNotificationCenterRemoveObserver(center, observer, CFNotificationName(notification), nil)
            withExtendedLifetime(expectation) {}
        }
    }

    private func armHeldProvider(mode: String) {
        let armed = XCTestExpectation(description: "Source armed held representation: \(mode)")
        let stopObserving = observeProvider(mode: mode, event: "armed", expectation: armed)
        defer { stopObserving() }
        signalProvider(mode: mode, event: "arm")
        let result = XCTWaiter.wait(for: [armed], timeout: 5)
        XCTAssertEqual(result, .completed, "The source must arm the held representation without an early load")
        addText("\(mode)-provider-armed", "Source confirmed arm after the extension was offered.")
    }

    private func providerSignal(_ mode: String, _ event: String) -> CFString {
        "io.github.ispaure.logisticsincomingsender.\(mode).\(event)" as CFString
    }

    private func signalProvider(mode: String, event: String) {
        CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(),
                                             CFNotificationName(providerSignal(mode, event)), nil, nil, true)
    }

    private func launchSender() {
        sender.launch()
        XCTAssertTrue(sender.staticTexts["fixture-status"].waitForExistence(timeout: 20), sender.debugDescription)
        XCTAssertEqual(sender.staticTexts["fixture-status"].label, "Intake verified")
    }

    private func stopReceiver() {
        if receiver.state != .notRunning {
            receiver.terminate()
        }
        XCTAssertEqual(receiver.state, .notRunning)
    }

    private func selectShareExtension(heldMode: String? = nil) {
        let target = shareExtensionCell()
        var offered = target.waitForExistence(timeout: 15)
        capture("share-menu", apps: [sender])
        if !offered && heldMode != nil {
            let more = sender.cells.matching(NSPredicate(
                format: "identifier == %@ AND label == %@", "shareCell", "More"
            )).firstMatch
            if more.exists && more.isHittable {
                more.tap()
                capture("held-share-more", apps: [sender])
                offered = target.exists && target.isHittable
            }
        }
        XCTAssertTrue(offered, "The OS share sheet did not expose the Logisticks extension cell")
        if let heldMode {
            XCTAssertTrue(target.isHittable, "The offered Logisticks extension cell must be selectable")
            armHeldProvider(mode: heldMode)
            print("[IncomingFiles] \(heldMode)-provider-selection-start\n\(ProcessInfo.processInfo.systemUptime)")
        }
        target.tap()
    }

    private func shareExtensionCell() -> XCUIElement {
        sender.cells.matching(NSPredicate(format: "identifier == %@ AND label == %@", "shareCell", targetName)).firstMatch
    }

    private func assertShareResult(count: Int, failure: Bool = false) {
        let result = sender.staticTexts.matching(NSPredicate(
            format: "label BEGINSWITH %@ AND label CONTAINS %@",
            "\(count) file(s) received.", deviceLabel
        )).firstMatch
        let received = result.waitForExistence(timeout: 40)
        capture("share-extension-result", apps: [sender])
        XCTAssertTrue(received, "Expected \(count) received files for \(deviceLabel)")
        XCTAssertEqual(result.label.contains("Some files could not be received"), failure)
    }

    private func element(in app: XCUIApplication, label: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label)).firstMatch
    }

    private func dismissQuickPathTutorial(in app: XCUIApplication, timeout: TimeInterval = 0) {
        let tutorial = app.otherElements["UIContinuousPathIntroductionView"].firstMatch
        let explanation = tutorial.staticTexts[
            "Speed up your typing by sliding your finger across the letters to compose a word."
        ].firstMatch
        let presented = timeout > 0 ? explanation.waitForExistence(timeout: timeout) : explanation.exists
        if presented {
            tap(tutorial.buttons["Continue"].firstMatch, in: app, checkpoint: "quickpath-tutorial")
            XCTAssertTrue(explanation.waitForNonExistence(timeout: 8), "QuickPath tutorial still covers the app")
        }
    }

    private func tap(_ element: XCUIElement, in app: XCUIApplication, checkpoint: String) {
        let exists = element.waitForExistence(timeout: 20)
        capture(checkpoint, apps: [app])
        XCTAssertTrue(exists && element.isHittable, "Element unavailable at \(checkpoint)")
        element.tap()
    }

    private func capture(_ name: String, apps: [XCUIApplication]) {
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        screenshot.name = name
        screenshot.lifetime = .keepAlways
        add(screenshot)
        for app in apps {
            addText("\(name)-\(app.identifier)", app.debugDescription)
        }
    }

    private func addText(_ name: String, _ content: String) {
        let attachment = XCTAttachment(string: content)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("[IncomingFiles] \(name)\n\(content)")
    }
}
