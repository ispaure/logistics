// TEST_STAGE = TestStage.EXTENDED
import XCTest
final class NavigationUITests: XCTestCase {
 func testToolbarMenuSingleTap() throws {
  continueAfterFailure = false
  let app = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsduotoolbarqa")
  app.activate()
  let ordinary = app.buttons["Documentation actions"].firstMatch
  let system = app.buttons["More"].firstMatch
  let deadline = Date().addingTimeInterval(60)
  while !ordinary.exists && !system.exists && Date() < deadline { Thread.sleep(forTimeInterval: 0.25) }
  let button = ordinary.exists ? ordinary : system
  XCTAssertTrue(button.exists, app.debugDescription)
  button.tap()
  let find = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Find in this page")).firstMatch
  XCTAssertTrue(find.waitForExistence(timeout: 5), app.debugDescription)
  let screenshot = XCTAttachment(screenshot: app.screenshot())
  screenshot.name = "native-toolbar-menu-single-tap"; screenshot.lifetime = .keepAlways; add(screenshot)
 }
}
