// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// TEST_STAGE = TestStage.EXTENDED
import XCTest

final class OutboundShareUITests: XCTestCase {
    private let sender = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsstorageqa")
    private let filename = "Selected payload.logisticsfixture"
    private let receiver = "Outbound QA Receiver"

    func testSelectedFileShare() {
        continueAfterFailure = false
        sender.launch()
        choose("Add to Favourites")
        choose("Remove from Favourites")

        choose("Send to App…")
        let extensionCell = shareCell()
        tapReady(extensionCell, "native share destination")
        capture("outbound-ios-cancel")
        let backdrop = sender.otherElements["PopoverDismissRegion"].firstMatch
        let popover = sender.popovers.firstMatch
        XCTAssertTrue(backdrop.exists && popover.exists)
        let point = CGPoint(x: backdrop.frame.midX, y: backdrop.frame.minY + 0.15 * backdrop.frame.height)
        XCTAssertFalse(popover.frame.contains(point))
        sender.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: point.x - sender.frame.minX, dy: point.y - sender.frame.minY)).tap()
        XCTAssertTrue(extensionCell.waitForNonExistence(timeout: 15))

        choose("Send to App…")
        tap(shareCell(), "choose generated endpoint")
        let receipt = sender.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "1 file(s) received.")).firstMatch
        tapReady(receipt, "receiver receipt")
        XCTAssertFalse(receipt.label.contains("Some files could not be received"))
        capture("outbound-ios-receiver")
        tap(sender.buttons["Done"].firstMatch, "finish receiving")
        XCTAssertTrue(receipt.waitForNonExistence(timeout: 15))
    }

    private func row() -> XCUIElement {
        sender.buttons["Select " + filename].firstMatch
    }

    private func label(_ title: String) -> XCUIElement {
        sender.descendants(matching: .any).matching(NSPredicate(format: "label == %@", title)).firstMatch
    }

    private func choose(_ command: String) {
        tap(row(), "select fixture file row")
        tap(label(command), command)
    }

    private func shareCell() -> XCUIElement {
        sender.cells.matching(NSPredicate(format: "identifier == %@ AND label == %@", "shareCell", receiver)).firstMatch
    }

    private func tapReady(_ element: XCUIElement, _ checkpoint: String) {
        guard element.waitForExistence(timeout: 25) && element.isHittable else {
            capture("failed-" + checkpoint)
            let hierarchy = XCTAttachment(string: sender.debugDescription)
            hierarchy.lifetime = .keepAlways
            add(hierarchy)
            XCTFail("Element unavailable at " + checkpoint)
            return
        }
    }

    private func tap(_ element: XCUIElement, _ checkpoint: String) {
        tapReady(element, checkpoint)
        element.tap()
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
