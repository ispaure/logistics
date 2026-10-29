// TEST_STAGE = TestStage.EXTENDED
import XCTest

final class IncomingFilesUITests: XCTestCase {
    func testDocumentInteractionMenuReceivesOneFile() throws {
        continueAfterFailure = false
        let sender = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsincomingsender")
        sender.launch()
        sender.buttons["Open fixture in app"].tap()
        // iOS 27 presents the share extension in this document interaction menu.
        // Receiving must finish in the extension; opening the main app is explicit.
        let target = sender.cells["Inbox QA"].firstMatch
        XCTAssertTrue(target.waitForExistence(timeout: 15), sender.debugDescription)
        target.tap()
        let result = sender.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "1 file(s) received.")).firstMatch
        XCTAssertTrue(result.waitForExistence(timeout: 30), sender.debugDescription)
        sender.buttons["Done"].firstMatch.tap()
        XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsinboxqa").activate()
    }

    func testShareExtensionReceivesTwoFiles() throws {
        continueAfterFailure = false
        let sender = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsincomingsender")
        sender.launch()
        sender.buttons["Share fixture files"].tap()
        let target = sender.cells["Inbox QA"].firstMatch
        XCTAssertTrue(target.waitForExistence(timeout: 15), sender.debugDescription)
        target.tap()
        let result = sender.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "2 file(s) received.")).firstMatch
        XCTAssertTrue(result.waitForExistence(timeout: 30), sender.debugDescription)
        sender.buttons["Done"].firstMatch.tap()
        XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsinboxqa").activate()
    }
}
