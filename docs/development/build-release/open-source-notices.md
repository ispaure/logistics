# Open-source notices and dependency coverage

Settings exposes the offline notices under **Open-source licenses** (under **About** on mobile). `Python/services/open_source.py` retains publisher text and flags missing or incomplete entries. Verify redistribution, source and relinking obligations against the shipped artifact.

## Inventory owners

| Component | Sources |
| --- | --- |
| App, commonUtils and vendored code | Retained upstream notices |
| Python runtime closure | Wheel RECORD/license metadata and full texts for installed dependencies and requested extras |
| Qt/PySide and WebEngine | Version-matched Qt supplements, `qt-source-index.json`, `qt-source-notices.json` and independently versioned `qtwebengine-source-notices.json` |
| Desktop rclone, VLC, mount tools | Pinned rclone dependency union, retained VLC notices and macFUSE/WinFsp publisher texts |
| Mobile Go | Target OS and both supported architectures in `mobile/native-licenses/manifest.json` |
| Android | Variant-resolved Gradle runtime and detached Chaquopy artifacts in `logistics-open-source.json` |

The Android hook hashes artifacts, reads nested notices and follows parent POM licenses. `services/licenses/android.json` adds reviewed exact-version omissions, including Python Android target and bundled native libraries. Keep publisher SDK terms distinct. Qt and desktop rclone source unions may include unshipped components.

## Refresh and verification

Use the selected versions when refreshing from the root:

```sh
.venv/bin/python -m logistics_build.refresh_notices --qt-version 6.12.0 --webengine-version 6.140.0
.venv/bin/python -m logistics_build.refresh_notices --rclone-version 1.74.1
```

Keep source pins, catalogs and provenance aligned. Run `test_open_source.py`, `test_license_inventory.py`, `test_license_build.py` and `test_mobile_packaging.py` through their owning host suites. Inspect final APK, IPA and desktop metadata and native display before release.

## Unresolved publisher and provenance items

- **Dataview.** The source review identified a local compatibility implementation and retains the exact upstream MIT acknowledgement. Review bundled third-party examples independently. Disclose automatically executed note and library JavaScript to Apple with the [review demonstration](mobile-testflight.md#notes-library-data-view-disclosure-and-review-demonstration).
- **Onyx.** Six SDK POMs declare BSD-3 without the required copyright text. `onyxsdk-pennative:1.0.5` also lacks a license declaration. Preserve `notice_complete: false` and reviewed versions in `android.json`. Ask the publisher for the exact terms and copyright/NOTICE text for all seven binaries, including bundled native code. The demo's Apache-2.0 terms cover the demo. [SDK licensing inquiry](https://github.com/onyx-intl/OnyxAndroidDemo/issues/120)
- **Other gaps.** Qt Multimedia's FFmpeg record has an incomplete license file. Verify binary-specific VLC/VLCKit codec notices and the iOS Python provider's native notices. Preserve ownership evidence for artwork, historical aviation CSVs and the legacy PDF.
