# PySide6 iOS reuse proof

Experimental simulator fixture for commonUtils FileBrowser, CodeEdit and MarkdownViewer with compiled rclone. Uses synthetic private data. Qt 6.12/Python 3.15 column navigation is disabled after a populated-root crash.

## Reproduce on an Apple Silicon Mac

Use a [retention scratch workspace](../testing/validation-artifacts.md) and an owned disposable simulator. Set `LOGISTICS_QT_SCRATCH` to that path. Use Xcode, pinned Go, PySide6 6.12.0, Pygments 2.19.2, tqdm and Python Apple Support 3.15.0rc2. Verify the published SHA-256 values for the arm64 simulator PySide6/shiboken6 wheels and Python XCFramework. See the [Qt deployment guide](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-ios-deploy.html).

- `pyside6-6.12.0-6.12.0-cp315-cp315-ios_arm64_simulator.whl`:
  `58c7ca345de5443e81253b959527485633eaa7b203a92988bc2dbd1192083e73`
- `shiboken6-6.12.0-6.12.0-cp315-cp315-ios_arm64_simulator.whl`:
  `289fd2fcfa82e93a4218399eded8227bc2830351ae900a3db672ef8b59eaa381`

```sh
python mobile_build/qt_proof/prepare.py "${LOGISTICS_QT_SCRATCH}/stage"
pyside6-ios-deploy "${LOGISTICS_QT_SCRATCH}/stage"/main.py --name LogisticsQtProof \
  --bundle-id io.github.ispaure.logisticsqtproof \
  --wheel-pyside /path/to/pyside6-simulator.whl \
  --wheel-shiboken /path/to/shiboken6-simulator.whl \
  --xcframework-path /path/to/Python.xcframework
python mobile_build/qt_proof/link_ios.py "${LOGISTICS_QT_SCRATCH}/stage" --go /path/to/go
xcodebuild -project "${LOGISTICS_QT_SCRATCH}/stage"/deployment/ios_arm64_simulator/LogisticsQtProof.xcodeproj \
  -scheme LogisticsQtProof -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "${LOGISTICS_QT_SCRATCH}/build" ARCHS=arm64 ONLY_ACTIVE_ARCH=YES \
  CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES
xcrun simctl install SIMULATOR_UUID "${LOGISTICS_QT_SCRATCH}/build"/Build/Products/Debug-iphonesimulator/LogisticsQtProof.app
xcrun simctl launch SIMULATOR_UUID io.github.ispaure.logisticsqtproof
python mobile_build/qt_proof/collect.py SIMULATOR_UUID test-results/qt-proof
```

Expect a complete fresh report and screenshots in ignored `test-results/qt-proof/`. Retire the simulator and scratch after collection.
