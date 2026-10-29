// TEST_STAGE = TestStage.EXTENDED
import XCTest
final class DestinationTests: XCTestCase {
 func testDestinationWorkflow() {
  continueAfterFailure = false
  let app = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticsdestinationqa")
  app.activate()
  let folder = app.buttons["New folder"].firstMatch
  XCTAssertTrue(folder.waitForExistence(timeout: 30), app.debugDescription)
  folder.tap()
  let folderName = app.textFields.matching(NSPredicate(format: "placeholderValue == %@", "New folder name")).firstMatch
  XCTAssertTrue(folderName.waitForExistence(timeout: 10), app.debugDescription)
  folderName.tap(); folderName.typeText("Native folder")
  app.buttons["Create"].firstMatch.tap()
  let name = app.textFields.matching(NSPredicate(format: "placeholderValue == %@", "File name")).firstMatch
  XCTAssertTrue(name.waitForExistence(timeout: 10), app.debugDescription)
  name.tap()
  if let value = name.value as? String { name.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count)) }
  name.typeText("Native saved")
  app.buttons["Save here"].firstMatch.tap()
  let move = app.buttons["Move here"].firstMatch
  XCTAssertTrue(move.waitForExistence(timeout: 40), app.debugDescription)
  move.tap()
  XCTAssertTrue(app.buttons["File and folder actions"].firstMatch.waitForExistence(timeout: 30), app.debugDescription)
  let hidden = app.cells.matching(NSPredicate(format: "label CONTAINS %@", ".Hidden.txt")).firstMatch
  XCTAssertTrue(hidden.waitForExistence(timeout: 20), app.debugDescription)
  let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
  image.name = "Hidden rows after native Save and Move"; image.lifetime = .keepAlways
  add(image)
  app.tables.firstMatch.swipeUp(); app.tables.firstMatch.swipeDown()
  Thread.sleep(forTimeInterval: 25)
  print("NATIVE_DESTINATION_TAPS_PASSED")
 }
}
