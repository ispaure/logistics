# Open-source notices and dependency coverage

Mobile exposes the offline viewer under **Settings → About → Open-source
licenses**; desktop uses **Settings → Open-source licenses**. Search includes
component names, license declarations and notice text. The viewer preserves
publisher text; an SPDX identifier alone is not treated as a complete license.
This is a notice inventory, not clearance of redistribution or source/relinking
obligations.

## Inventory owners

`Python/services/open_source.py` combines the following sources:

| Component | Notice source |
| --- | --- |
| Logistics, commonUtils, vendored rmscene and the desktop editor adaptation | Their retained upstream license files |
| Python runtime packages | The declared runtime requirement closure, including requested extras; wheel `RECORD`, `License-File` and conventional license metadata files |
| Qt/PySide bindings | Version-matched supplementary LGPL/GPL texts for wheels that omit full license files |
| Qt bundled libraries | Release-pinned source attributions from `qt-source-index.json` and `qt-source-notices.json` |
| Chromium/PDFium and related WebEngine components | `qtwebengine-source-notices.json`, checked against `qWebEngineVersion()` independently of the Qt/PySide version |
| Desktop rclone and dependencies | Its MIT notice and `rclone-dependency-notices.json`, collected from pinned source dependency graphs across desktop OS/architecture combinations, including cmount |
| Downloaded desktop VLC | All retained runtime notices, including extensionless files and nested directories with repeated basenames |
| Optional desktop mount integrations | The pinned macFUSE and WinFsp publisher license files |
| Native mobile Go engine | `mobile/native-licenses/manifest.json`, generated for both arm64 and amd64 under the target OS, including notices in used packages and their ancestors |
| Android AARs/JARs and Python support artifacts | The resolved variant inventory described below |

Qt and desktop rclone source collections are conservative unions. They can include
optional/platform-specific components absent from an individual binary and are
labelled accordingly. Do not present them as a measurement of the final binary.
Missing manifests, incomplete notices and Qt version mismatches are displayed.
Desktop-only source collections are excluded from mobile staging.

## Android resolved artifacts

`mobile_build/build_support/license_build.py` installs the Gradle variant hook
`android_licenses.gradle` from `cloud_build.configure_android_sources()`.
Each variant generates its `logistics-open-source.json` asset before asset merging.
It follows the selected runtime classpath, not just the direct declarations in
`pyproject.toml`. Publisher license metadata is inherited from resolved Maven
parents when the child has no declaration.

Chaquopy's packaged runtime/target/bootstrap dependencies live in detached
configurations, outside AGP's normal runtime graph. The hook includes those
configurations through the pinned Chaquopy plugin API. It records artifact hashes,
reads notices inside nested JAR/ZIP/IMY files and merges multiple artifacts of one
selected module/version. Notice generation does not compile or install an app.

`services/licenses/android.json` supplies reviewed, version-specific omissions.
For CPython Android target 3.12.12-0 this includes the PSF license and notices for
its pinned OpenSSL, libffi, bzip2, XZ and embedded libraries. The target wrapper's
Maven MIT declaration is not substituted for the interpreter/library licenses.
Google SDK/API/ML Kit terms are bundled as publisher terms, not labelled MIT.
`sources.json` and the generated source catalogs record upstream provenance.

## Refresh and verification

Run the following explicit refreshes from the repository root when upgrading pins:

```sh
.venv/bin/python -m logistics_build.refresh_notices --qt-version 6.12.0 --webengine-version 6.140.0
.venv/bin/python -m logistics_build.refresh_notices --rclone-version 1.74.1
```

Refreshes use managed scratch storage for downloaded source inventories and write
only the resulting notice resources. The Qt source index records release
submodule commits and attribution paths; regenerate that index when changing the
Qt release. WebEngine documentation is checked for the requested version before
collecting its license blocks. Keep source pins, catalogs and dependency tests
aligned. Store one-off reports and previews under ignored `test-results/`.

Host coverage includes `test_open_source.py`, `test_license_inventory.py`,
`test_license_build.py`, `test_mobile_packaging.py` and the Settings UI suites.
Before store distribution, inspect the final APK/IPA/desktop artifacts to ensure
metadata and generated assets survive packaging. A host inventory test does not
establish native device rendering or complete binary-specific licensing.

## Unresolved publisher and provenance items

### Notes Library Dataview compatibility — November 2, 2026

Source, history and mobile manifests were reviewed for the current
`features/notes_library/dataview*.py` implementation. No bundled Obsidian
Dataview plugin, SDK or copied upstream implementation was identified. The
reviewed runtime implements a small compatibility subset itself. This is a
source review, not proof of independent authorship of every line or user script.
The [upstream plugin's MIT license](https://github.com/blacksmithgu/obsidian-dataview/blob/master/LICENSE.txt)
permits commercial redistribution with its copyright and permission notice
retained when its code or substantial portions are included. Its complete,
commit-pinned MIT text is retained offline as **Dataview compatibility
acknowledgement** on every platform. This is a conservative acknowledgement, not
a claim that the upstream plugin is bundled. It does not relicense Logistics or
user scripts. Review any bundled third-party
example scripts separately, and describe compatibility without implying affiliation.

The publishing concern is execution: complete `dataviewjs` blocks run
automatically while reading, and `dv.view` executes JavaScript from library files
using `AsyncFunction`. `NotesLibrary` rejects remote-storage providers; downloaded
or synced local copies can nevertheless contain imported scripts. The worker has
no exposed general native/write API or page DOM; CSP blocks network requests,
and host reads enforce library containment and resource limits. Those boundaries
do not make the authored JavaScript declarative data.

Before an Apple submission, explicitly disclose and demonstrate this behavior
in review notes. Apple's current
[agreement, section 3.3.1(B)](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/),
permits downloaded interpreted code within the app's advertised purpose, without
bypassing OS security or creating another app storefront. Bounded personal-note
views have a plausible basis under that permission; JavaScript is not an
automatic rejection. [Apple guidelines 2.5.2 and 4.7](https://developer.apple.com/app-store/review/guidelines/)
make arbitrary feature-changing code and hosted software relevant review issues;
WebKit execution alone does not establish approval. Do not assume private note
scripts constitute a public plug-in marketplace. If Apple treats them under
4.7, assess its additional consent, native API and software-index requirements.
A declarative-only implementation would reduce this uncertainty. A trust switch
would improve user control but would not settle the policy classification.
[Google Play's policy](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en)
expressly distinguishes interpreted JavaScript from downloaded native executable
code, while still requiring runtime-loaded scripts to comply with its policies.

An initial desktop run during concurrent metadata edits passed nine tests and
failed four. The subsequent current-source Dataview rerun passed all fourteen,
including the Chromium test of the mobile preview's worker policy. The eleven
notice tests and the review-sample library discovery/read test also passed.
These host tests are not release validation; no native device or App Store
submission was tested in this review.
The [TestFlight guide](mobile-testflight.md#notes-library-data-view-disclosure-and-review-demonstration)
owns copy-ready review disclosure, the synthetic sample generator and exact
demonstration steps. Review information still needs to accompany the chosen
build in App Store Connect; writing the local guide does not submit it.

### Onyx SDK investigation — November 2, 2026

Six exact SDK versions declare BSD-3 in their publisher POMs; the seventh,
`onyxsdk-pennative`, has no license declaration. All seven AARs and their matching
official source JARs were inspected. Neither a license file nor a publisher
copyright header was found. The checked Javadoc and conventional `LICENSE`,
`LICENSE.txt` and `NOTICE` sidecars were not published at those artifact URLs.

| Exact artifact | Publisher POM declaration | Remaining gap |
| --- | --- | --- |
| [onyxsdk-base 1.8.9](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-base/1.8.9/onyxsdk-base-1.8.9.pom) | BSD-3 | Publisher copyright notice |
| [onyxsdk-baselite 1.1.2](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-baselite/1.1.2/onyxsdk-baselite-1.1.2.pom) | BSD-3 | Publisher copyright notice |
| [onyxsdk-device 1.3.6](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-device/1.3.6/onyxsdk-device-1.3.6.pom) | BSD-3 | Publisher copyright notice |
| [onyxsdk-geometry 1.1.7](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-geometry/1.1.7/onyxsdk-geometry-1.1.7.pom) | BSD-3 | Publisher copyright notice |
| [onyxsdk-pen 1.5.8](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-pen/1.5.8/onyxsdk-pen-1.5.8.pom) | BSD-3 | Publisher copyright notice |
| [onyxsdk-penbrush 1.1.2](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-penbrush/1.1.2/onyxsdk-penbrush-1.1.2.pom) | BSD-3 | Publisher copyright notice |
| [onyxsdk-pennative 1.0.5](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-pennative/1.0.5/onyxsdk-pennative-1.0.5.pom) | None | License applicability and copyright notice |

The [official demo repository](https://github.com/onyx-intl/OnyxAndroidDemo)
contains sample app sources and downloads the SDKs as external dependencies.
Its Apache-2.0 license was added on September 7, 2026; a
[September 10 update](https://github.com/onyx-intl/OnyxAndroidDemo/commit/ec512c79c0d39c1e294214d36580ce4c914bbea6)
identifies `ONYX INTERNATIONAL INC.` as that work's copyright owner. No statement
was found extending that demo license to these separately published SDK AARs.
It is therefore not substituted for their BSD-3/undeclared metadata, nor used to
invent SDK copyright years. The public
[SDK licensing inquiry #120](https://github.com/onyx-intl/OnyxAndroidDemo/issues/120)
remained open without a publisher clarification when checked.

The newer `onyxsdk-pennative` POMs for
[1.0.6](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-pennative/1.0.6/onyxsdk-pennative-1.0.6.pom)
and [1.1.0-alpha6](https://repo.boox.com/repository/maven-public/com/onyx/android/sdk/onyxsdk-pennative/1.1.0-alpha6/onyxsdk-pennative-1.1.0-alpha6.pom)
also omit a license declaration; an upgrade alone does not supply that missing
metadata. These newer binaries were not substituted or audited.

`services/licenses/android.json` records these version-specific findings.
`notice_complete: false` preserves their incomplete status even if an incidental
license file is collected. An unrelated reconstruction/fork's license is not a
license for the original BOOX binaries.

The focused publisher clarification needed is: confirm whether
`onyxsdk-pennative:1.0.5` is covered by BSD-3 (or specify its actual terms), and
provide the exact copyright/NOTICE text to reproduce for all seven SDK artifacts,
including any bundled native or third-party code. Preserve their declarations and
known provenance in the meantime; do not label these entries cleared.

The Qt Multimedia FFmpeg source attribution supplies a compound license declaration
without a complete associated license file; the viewer marks that source record
incomplete. Binary-specific VLC/VLCKit codec notices and the iOS Python provider's
native library notices still require review against the exact shipped artifacts.
Providing notice text does not by itself satisfy applicable source/relinking terms.

No third-party author is inferred for the app artwork, historical aviation CSVs
or legacy PDF. Preserve their ownership/permission evidence separately; a generic
credit cannot establish rights to material with undocumented provenance.
