# PDF reader and search verification — 2026-10-17

The isolated native PDF probe exercised real PDFKit rendering on the iOS 27.0
phone simulator and real PdfRenderer rendering on the Android emulator. Both
passed local first-open, rendering, numeric page jumps, whole-document embedded
text search, reading mode and PDF byte release. The fixtures contain synthetic
PDF text and no user documents or account data. These are local development
snapshots, not distribution builds or physical-device certification.

- [iOS report](ios-result.json)
- [iOS reading view](ios-reading.png)
- [iOS search panel](ios-search.png)
- [Android report](android-result.json)
- [Android reading view](android-reading.png)
- [Desktop compact reader](desktop-reading.png)

The native Android probe reproduced `Invalid ID: 63` in Bitmap.eraseColor before
forcing Chaquopy's Java int overload with jint(-1). The iOS probe exposed a cold
opening path that had not initialized provider controls; first opening now also
waits for the initial credential restore task.

Search regressions verify nested LocalCrypt matches with one recursive rclone
listing, a match beyond 10,000 entries, cancellation, and 400 ms trailing-edge
callbacks on native and Qt event loops. Desktop PDF rendering and mobile
local/remote/LocalCrypt sessions have focused host regression coverage.

Probe source: [native PDF probe](../../../../Mobile/native_tests/tests/logisticsmobile/pdf_probe.py).

## Host validation results

- Focused desktop PDF/LocalCrypt/debounce checks: 52 passed.
- Git search suite: 52 passed; IDE browser: 6 passed; remote browser: 8 passed.
- Focused mobile PDF/browser/LocalCrypt/remote-reader checks: 24 passed.
- Mobile LocalCrypt core checks: 11 run, 2 native bridge checks skipped.
- Ruff checks over the changed search/PDF implementation passed.
- Full mobile suite with loopback fixture access: 407 run, 406 passed and one
  legacy credential-folder visibility assertion failed in
  test_workspace_navigation.WorkspaceNavigationTests.test_legacy_credentials_use_prefix_without_dash_and_toggle_in_place.
  The failure expected Personal/MyLegacy folders but received only All; the PDF
  and search checks passed.
