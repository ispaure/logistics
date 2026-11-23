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
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "file-browser-after-native-drops"
        screenshot.lifetime = .keepAlways
        add(screenshot)

        let menu = app.buttons["File and folder actions"].firstMatch
        XCTAssertTrue(app.staticTexts["Group destination"].firstMatch.waitForExistence(timeout: 8),
                      app.debugDescription)
        menu.tap()
        let select = app.buttons["Select items"].firstMatch
        XCTAssertTrue(select.waitForExistence(timeout: 8), app.debugDescription)
        select.tap()
        let first = app.cells["List source. Folder"].firstMatch
        let second = app.cells["Tile source.txt. File"].firstMatch
        XCTAssertTrue(first.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertEqual(first.value as? String, "Not selected")
        first.tap()
        second.tap()
        XCTAssertTrue(app.staticTexts["2 selected"].firstMatch.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertEqual(first.value as? String, "Selected")
        XCTAssertEqual(second.value as? String, "Selected")
        let selection = XCTAttachment(screenshot: app.screenshot())
        selection.name = "selected-files-in-list"
        selection.lifetime = .keepAlways
        add(selection)

        XCTAssertFalse(app.buttons["Show tiles"].firstMatch.exists, app.debugDescription)
        XCTAssertFalse(menu.exists, app.debugDescription)
        XCTAssertTrue(app.buttons["Delete selected items"].firstMatch.exists, app.debugDescription)
        let exitSelection = app.buttons["Exit selection"].firstMatch
        XCTAssertTrue(exitSelection.waitForExistence(timeout: 8), app.debugDescription)
        exitSelection.tap()
        XCTAssertTrue(menu.waitForExistence(timeout: 8), app.debugDescription)
        app.buttons["Show tiles"].firstMatch.tap()
        let item = app.buttons["Tile source.txt"].firstMatch
        XCTAssertTrue(item.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertFalse(app.buttons["Actions for Tile source.txt"].exists, app.debugDescription)
        item.press(forDuration: 0.8)
        let details = app.buttons["Details"].firstMatch
        XCTAssertTrue(details.waitForExistence(timeout: 8), app.debugDescription)
        details.tap()
        let closeDetails = app.buttons["Close details"].firstMatch
        XCTAssertTrue(closeDetails.waitForExistence(timeout: 8), app.debugDescription)
        let detailsScreenshot = XCTAttachment(screenshot: app.screenshot())
        detailsScreenshot.name = "file-details-panel"
        detailsScreenshot.lifetime = .keepAlways
        add(detailsScreenshot)
        closeDetails.tap()
        XCTAssertTrue(item.waitForExistence(timeout: 8), app.debugDescription)
        menu.tap()
        XCTAssertTrue(select.waitForExistence(timeout: 8), app.debugDescription)
        select.tap()
        let firstTile = app.buttons["Select List source"].firstMatch
        XCTAssertTrue(firstTile.waitForExistence(timeout: 8), app.debugDescription)
        firstTile.tap()
        app.buttons["Select Tile source.txt"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["2 selected"].firstMatch.waitForExistence(timeout: 8), app.debugDescription)
        let selectedTiles = XCTAttachment(screenshot: app.screenshot())
        selectedTiles.name = "selected-files-in-tiles"
        selectedTiles.lifetime = .keepAlways
        add(selectedTiles)
        let batch = app.buttons["Move…"].firstMatch
        XCTAssertTrue(batch.isEnabled, app.debugDescription)
        batch.tap()
        let group = app.staticTexts["Group destination"].firstMatch
        if !group.waitForExistence(timeout: 3) {
            let parent = app.staticTexts["Drop destination"].firstMatch
            XCTAssertTrue(parent.waitForExistence(timeout: 8), app.debugDescription)
            parent.tap()
        }
        XCTAssertTrue(group.waitForExistence(timeout: 8), app.debugDescription)
        group.tap()
        let move = app.buttons["Move here"].firstMatch
        XCTAssertTrue(move.waitForExistence(timeout: 8), app.debugDescription)
        move.tap()
        XCTAssertTrue(app.buttons["File and folder actions"].firstMatch.waitForExistence(timeout: 8),
                      app.debugDescription)
    }
}
