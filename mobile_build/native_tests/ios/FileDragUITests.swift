// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// TEST_STAGE = TestStage.EXTENDED
import XCTest

final class FileDragUITests: XCTestCase {
    func testLongPressMovesFolderInListAndFileInTiles() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsnotebookqa")
        app.activate()
        let folder = app.staticTexts["List source"].firstMatch
        let destination = app.staticTexts["Drop destination"].firstMatch
        XCTAssertTrue(folder.waitForExistence(timeout: 60), app.debugDescription)
        XCTAssertTrue(destination.exists, app.debugDescription)
        folder.press(forDuration: 0.8, thenDragTo: destination, withVelocity: .slow, thenHoldForDuration: 1.8)
        XCTAssertTrue(folder.waitForNonExistence(timeout: 12), app.debugDescription)

        let tile = app.buttons["Tile source.txt"].firstMatch
        let target = app.buttons["Drop destination"].firstMatch
        XCTAssertTrue(tile.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertTrue(target.exists, app.debugDescription)
        tile.press(forDuration: 0.8, thenDragTo: target, withVelocity: .slow, thenHoldForDuration: 1.8)
        XCTAssertTrue(app.navigationBars["Drop destination"].waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertTrue(tile.waitForExistence(timeout: 8), app.debugDescription)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "file-browser-after-native-drops"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }
}
