import XCTest

final class MarkdownAdaptiveUITests: XCTestCase {
    func dockKeyboard(_ app: XCUIApplication) {
        let keyboard = app.keyboards.firstMatch
        if keyboard.exists && keyboard.frame.width < app.frame.width * 0.7 {
            keyboard.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0))
                .withOffset(CGVector(dx: keyboard.frame.width * 0.5, dy: keyboard.frame.height + 30)).tap()
            let full = app.buttons["Full"].firstMatch
            XCTAssertTrue(full.waitForExistence(timeout: 5), app.debugDescription)
            full.tap()
            Thread.sleep(forTimeInterval: 1)
        }
    }

    func testIPadKeyboardAndAccessibility() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsmarkdownqa")
        app.activate()
        let format = app.buttons["Markdown formatting"].firstMatch
        XCTAssertTrue(format.waitForExistence(timeout: 30), app.debugDescription)
        print("MARKDOWN_INITIAL_TREE=\(app.debugDescription)")
        let text = app.webViews.firstMatch
        text.coordinate(withNormalizedOffset: CGVector(dx: 0.4, dy: 0.3)).tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10), app.debugDescription)
        print("MARKDOWN_KEYBOARD_TREE=\(app.debugDescription)")
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "ipad-docked-keyboard"; shot.lifetime = .keepAlways; add(shot)
        var issues: [String] = []
        try app.performAccessibilityAudit(for: [.hitRegion, .sufficientElementDescription, .trait, .contrast]) { issue in
            issues.append(String(describing: issue))
            return true
        }
        print("MARKDOWN_ACCESSIBILITY_ISSUES=\(issues)")
        dockKeyboard(app)
        let docked = app.keyboards.firstMatch.frame
        app.keyboards.firstMatch.pinch(withScale: 0.4, velocity: -1)
        Thread.sleep(forTimeInterval: 1.5)
        let floating = app.keyboards.firstMatch.frame
        print("MARKDOWN_KEYBOARD_FRAMES=\(docked) -> \(floating)")
        XCTAssertLessThan(floating.width, app.frame.width * 0.7, app.debugDescription)
        app.webViews.firstMatch.textViews.element(boundBy: 1).tap()
        app.typeText(" floating input")
        format.tap()
        print("MARKDOWN_OPEN_MENU_TREE=\(app.debugDescription)")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Insert link")).firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        try app.performAccessibilityAudit(for: [.hitRegion, .sufficientElementDescription, .trait, .contrast, .textClipped]) { issue in
            issues.append(String(describing: issue)); return true
        }
        print("MARKDOWN_MENU_AUDIT_ISSUES=\(issues)")
        app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Insert link")).firstMatch.tap()
        XCTAssertTrue(app.textFields.firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        app.buttons["Cancel"].firstMatch.tap()
        app.webViews.firstMatch.textViews.element(boundBy: 1).tap()
        dockKeyboard(app)
        XCTAssertGreaterThan(app.keyboards.firstMatch.frame.width, app.frame.width * 0.8)
        print("MARKDOWN_DOCK_RESTORED=\(app.keyboards.firstMatch.frame)")
        XCTAssertTrue(issues.isEmpty, issues.joined(separator: "\n"))
        let after = XCTAttachment(screenshot: app.screenshot())
        after.name = "ipad-keyboard-options"; after.lifetime = .keepAlways; add(after)
        print("MARKDOWN_FINAL_TREE=\(app.debugDescription)")
    }
}
