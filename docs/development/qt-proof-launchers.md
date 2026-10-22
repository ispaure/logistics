# PySide6 iOS reuse proof

This separate experimental app keeps the Toga app intact. It hosts the actual
commonUtils FileBrowser with two independently navigable tabs, CodeEdit with
Pygments syntax highlighting and a private save button, MarkdownViewer, and the
compiled Logistics rclone bridge. It uses synthetic private files and an in-memory
rclone connection, never real user credentials or remote writes.

The browser omits column view explicitly because Qt 6.12/Python 3.15 crashes in
QColumnView while changing a populated root. List/thumbnail navigation remains
available. This proof is not a replacement mobile application or a release gate.
See [the result and limitations](mobile-qt-proof.md).

## Reproduce on an Apple Silicon Mac

Use a host Python environment containing PySide6 6.12.0, Pygments 2.19.2 and tqdm;
Xcode, an arm64 iOS simulator, and the pinned Go toolchain are also required.
Download the public arm64 simulator wheels from Qt's
[PySide6 archive](https://download.qt.io/official_releases/QtForPython/pyside6/)
and [shiboken6 archive](https://download.qt.io/official_releases/QtForPython/shiboken6/).
Verify their published SHA256 values before deploying:

- `pyside6-6.12.0-6.12.0-cp315-cp315-ios_arm64_simulator.whl`:
  `58c7ca345de5443e81253b959527485633eaa7b203a92988bc2dbd1192083e73`
- `shiboken6-6.12.0-6.12.0-cp315-cp315-ios_arm64_simulator.whl`:
  `289fd2fcfa82e93a4218399eded8227bc2830351ae900a3db672ef8b59eaa381`

Qt's deployment helper uses Python-Apple-support 3.15.0rc2; supply its verified
Python.xcframework using `--xcframework-path`, or use the tool's checksummed
framework downloader. Current deployment documentation is
[Qt's iOS deployment guide](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-ios-deploy.html).

Run from the Logistics checkout, with tools available in the selected environment.
Use a **fresh** disposable staging directory, not the repository itself:

```sh
python mobile_build/qt_proof/prepare.py /tmp/logistics-qt-proof
pyside6-ios-deploy /tmp/logistics-qt-proof/main.py --name LogisticsQtProof \
  --bundle-id io.github.ispaure.logisticsqtproof \
  --wheel-pyside /path/to/pyside6-simulator.whl \
  --wheel-shiboken /path/to/shiboken6-simulator.whl \
  --xcframework-path /path/to/Python.xcframework
python mobile_build/qt_proof/link_ios.py /tmp/logistics-qt-proof --go /path/to/go
xcodebuild -project /tmp/logistics-qt-proof/deployment/ios_arm64_simulator/LogisticsQtProof.xcodeproj \
  -scheme LogisticsQtProof -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/logistics-qt-build ARCHS=arm64 ONLY_ACTIVE_ARCH=YES \
  CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES
xcrun simctl install SIMULATOR_UUID /tmp/logistics-qt-build/Build/Products/Debug-iphonesimulator/LogisticsQtProof.app
xcrun simctl launch SIMULATOR_UUID io.github.ispaure.logisticsqtproof
python mobile_build/qt_proof/collect.py SIMULATOR_UUID /tmp/logistics-qt-evidence
```

The app runs programmatic checks shortly after startup and writes evidence and
screenshots into its own private container. Collection rejects incomplete/stale
reports. `link_ios.py` reproducibly adds rclone, zlib and non-Python resources and
removes unneeded permission descriptions. Simulator ad hoc signing is needed for
Python's embedded extension frameworks; no Apple account or device signing is used.
The debug bundle is unoptimized and should not be used to estimate release size.
