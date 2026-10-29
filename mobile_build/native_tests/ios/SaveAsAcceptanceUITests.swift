// TEST_STAGE = TestStage.EXTENDED
import XCTest
final class SaveAsAcceptanceTests: XCTestCase {
 func testSaveAsAndSystemPickers() {
  continueAfterFailure = false
  let app = XCUIApplication(bundleIdentifier: "io.github.ispaure.logisticssaveasqa")
  app.activate()
  let editor = app.textViews.firstMatch
  XCTAssertTrue(editor.waitForExistence(timeout: 45), app.debugDescription)
  editor.tap(); editor.typeText("Tap draft exact bytes")
  let sourceActions = app.buttons["Document actions"].firstMatch
  XCTAssertTrue(sourceActions.waitForExistence(timeout: 10), app.debugDescription)
  sourceActions.tap()
  let saveAs = app.buttons["Save As…"].firstMatch
  XCTAssertTrue(saveAs.waitForExistence(timeout: 10), app.debugDescription)
  saveAs.tap()
  let folder = app.buttons["New folder"].firstMatch
  XCTAssertTrue(folder.waitForExistence(timeout: 45), app.debugDescription)
  folder.tap()
  let folderName = app.textFields.matching(NSPredicate(format: "placeholderValue == %@", "New folder name")).firstMatch
  XCTAssertTrue(folderName.waitForExistence(timeout: 10), app.debugDescription)
  folderName.tap(); folderName.typeText("Tapped")
  app.buttons["Create"].firstMatch.tap()
  let name = app.textFields.matching(NSPredicate(format: "placeholderValue == %@", "File name")).firstMatch
  XCTAssertTrue(name.waitForExistence(timeout: 10), app.debugDescription)
  name.tap()
  if let value = name.value as? String { name.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count)) }
  name.typeText("Tapped copy")
  app.buttons["Save here"].firstMatch.tap()
  let ordinaryActions = app.buttons["Document actions"].firstMatch
  let systemActions = app.buttons["More"].firstMatch
  let deadline = Date().addingTimeInterval(40)
  while !ordinaryActions.exists && !systemActions.exists && Date() < deadline { Thread.sleep(forTimeInterval: 0.2) }
  let actions = ordinaryActions.exists ? ordinaryActions : systemActions
  XCTAssertTrue(actions.exists, app.debugDescription)
  Thread.sleep(forTimeInterval: 2)
  actions.tap()
  let again = app.buttons["Save As…"].firstMatch
  XCTAssertTrue(again.waitForExistence(timeout: 10), app.debugDescription)
  again.tap()
  let cancel = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Cancel")).firstMatch
  func waitHittable(_ element: XCUIElement) {
   let limit = Date().addingTimeInterval(20)
   while (!element.exists || !element.isHittable) && Date() < limit { Thread.sleep(forTimeInterval: 0.2) }
   XCTAssertTrue(element.exists && element.isHittable, app.debugDescription)
  }
  func cancelPicker(systemOpen: Bool = false) {
   XCTAssertTrue(cancel.waitForExistence(timeout: 30), app.debugDescription)
   Thread.sleep(forTimeInterval: 2)
   if cancel.isHittable {
    cancel.tap()
   } else if systemOpen {
    // The iOS 27 Open sheet exposes its visible Close icon as a
    // non-hittable accessibility container. Tap its observed screen position.
    app.coordinate(withNormalizedOffset: CGVector(dx: 0.75, dy: 0.115)).tap()
   } else {
    // iOS 27 export sheets expose no hittable Cancel control. Dismiss
    // the observed draggable sheet using its native presentation gesture.
    let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.09))
    let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.90))
    start.press(forDuration: 0.1, thenDragTo: end)
   }
  }
  cancelPicker()
  waitHittable(actions)
  actions.tap()
  let exportItem = app.buttons["Export…"].firstMatch
  XCTAssertTrue(exportItem.waitForExistence(timeout: 10), app.debugDescription)
  exportItem.tap()
  cancelPicker()
  XCTAssertTrue(app.staticTexts["Export cancelled."].waitForExistence(timeout: 15), app.debugDescription)
  waitHittable(actions)
  actions.tap()
  let documents = app.buttons["All documents"].firstMatch
  XCTAssertTrue(documents.waitForExistence(timeout: 10), app.debugDescription)
  documents.tap()
  let library = app.buttons["Open Books & Comics library"].firstMatch
  for _ in 0..<5 {
   if library.exists && library.isHittable { break }
   app.scrollViews.firstMatch.swipeUp()
  }
  XCTAssertTrue(library.waitForExistence(timeout: 10), app.debugDescription)
  library.tap()
  let importItem = app.buttons["Import a book or comic…"].firstMatch
  XCTAssertTrue(importItem.waitForExistence(timeout: 15), app.debugDescription)
  importItem.tap()
  cancelPicker(systemOpen: true)
  waitHittable(importItem)
  // Reopen after cancellation to prove the native operation was released.
  importItem.tap()
  cancelPicker(systemOpen: true)
  waitHittable(importItem)
  let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
  image.name = "Actual Save As and system picker cancellations"; image.lifetime = .keepAlways
  add(image)
  print("SAVE_AS_ACTUAL_TAPS_PASSED")
 }
}
