# Logistics mobile prototype

This independent Toga application targets Android and iOS. It opens imported text
and Markdown as app-private copies, edits them, saves their original encoding and
line endings, and checkpoints drafts for recovery. Its hub also opens a private EPUB/CBZ library
with chapter/page navigation, standalone AES/ZipCrypto CBZ password prompts,
bookmarks and saved progress, plus text LM chat
with private history and explicit server connections, and embedded read-only
rclone browsing/downloads using credential ZIPs. It does not launch the desktop
Qt application or install its dependency list.

See the [user guide](../Python/logisticsmobile/user_docs/README.md) and
[architecture and validation guide](../docs/developer/mobile-preparation.md).

## Prepare a native build

Use a separate Python 3.12 environment with `briefcase==0.4.5`. Toga backends are
pinned to 0.5.7 in `pyproject.toml`. Install Go 1.26.9 for the native rclone
bridge; Android uses NDK 27.2.12479018 (installed by the build helper if needed). From the repository root, after committing
source changes:

```sh
python Mobile/tools.py stage Mobile/payload
cd Mobile
python cloud_build.py licenses
briefcase create android --no-input
python cloud_build.py android
briefcase build android --no-input
# On a Mac with the iOS platform installed:
briefcase create iOS --no-input
python cloud_build.py ios
briefcase build iOS --no-input
```

Staging creates a new directory and refuses to replace an existing payload. Move
or remove your previous generated `Mobile/payload` before staging again. For local
development, `--allow-dirty` permits uncommitted mobile and tracked shared sources.
The release evidence verifier still rejects dirty payloads. Explicit local runs
use `python ui_tools.py run android --device <device> --local` (or `ios`), verify
the staged source fingerprint, and retain a separate `*-native-ui-local.json` report.

Briefcase needs the Android SDK/JDK or Xcode/iOS platform resources. A listed iOS
SDK alone may be insufficient: install the matching simulator runtime through
Xcode Settings → Components before trying a simulator run.

For native iPhone Duo display/bar adaptation, select an installed iOS 27.1 SDK
or newer before creating/building the iOS app:

```sh
export DEVELOPER_DIR="$(python Mobile/select_ios_sdk.py --path-only)"
```

Run this from the repository root. It selects a compatible installed Xcode;
it does not install one. The iOS native CI job uses GitHub's `xcode-27` image and
rejects an older SDK rather than claiming Duo adaptation. The declared iOS 15
deployment minimum is retained, with newer sidebar APIs guarded at runtime;
an iOS 15 device/runtime remains a separate compatibility check.

## Native navigation foundation checks

The native test-mode suite additionally exercises a three-destination native
container, Apple navigation/split controllers, Android bottom/rail presentation,
native selection callbacks, draft retention, focus and widget cleanup. This
fixture supplements the normal app's Home/Files/Documents/Settings navigation shell.

For live resize and lifecycle checks, build/install the test-mode app first and
run from `Mobile` with a booted validation device:

```sh
python navigation_tools.py --adb /path/to/android-sdk/platform-tools/adb --device emulator-5554
python navigation_tools.py --ios --device <simulator-uuid> --output logs/navigation/apple-lifecycle
```

These commands activate an isolated, synthetic draft under the test app's cache.
Android exercises keyboard insets, phone/tablet sizes, real activity recreation
and process restoration, and resets its size/density overrides afterward. Apple
exercises scene rotation, background/resume and process restoration. Reports and
screenshots go under `Mobile/logs/navigation`. They do not establish physical
BOOX E Ink/stylus behavior, an actual fold gesture, or independent app windows.

Only public, selected Python sources and licenses enter the payload. Private
INIs, Git metadata, ignored resources and the external emulation link are excluded.
Native builds contain the host, commonUtils and selected portable EPUB/comic
modules. Runtime testbeds also contain generated fixture tests. Briefcase test-mode
builds add the separate `native_tests/tests` entry point; normal app artifacts are
captured before test-mode rebuilds and contain no test entry point.

## Open the app in Xcode

After running native UI tests, restore the normal app launcher before using Xcode:

```sh
cd Mobile
briefcase update iOS --no-input
briefcase build iOS --no-input
briefcase open iOS
```

Choose an iPhone Simulator in Xcode and press Run. These commands omit `--test`,
so the app opens its hub. `ui_tools.py run ios ...` intentionally runs automated
checks and leaves the generated project in test mode; repeat the normal update
and build afterward. Generated Xcode settings are local build artifacts.

## Host validation

```sh
PYTHONPATH=Python:Python/tests python -m logisticsmobile.smoke --target host
PYTHONPATH=Python python -m unittest discover -s Python/tests -p 'test_mobile_*.py' -v
```

For the widget contract check, install `toga-dummy==0.5.7` in the separate
environment, then run:

```sh
PYTHONPATH=Python TOGA_BACKEND=toga_dummy python -m unittest discover -s Mobile/tests -v
```

These commands verify host behavior; they do not certify device interfaces.

## Hosted builds and runtime checks

[Native builds](../.github/workflows/mobile-build.yml) produce an Android debug APK
and an iOS Simulator app archive. [Runtime checks](../.github/workflows/mobile-runtime.yml)
build the pinned CPython 3.14.7 testbeds and execute 37 Logistics document/core
cases inside actual Android and iOS interpreters. Result verification requires
the expected runtime, clean source commits, every case and zero failures or skips.

Both workflows run for changes to their mobile source paths on `alpha`; they also
define manual Android/iOS/both controls. GitHub exposes manual controls after the
workflow is present on the default branch. Native builds have a 45-minute upper
bound; cold interpreter/testbed jobs have a 90-minute upper bound. Diagnostic
artifacts remain available for 14 days. New mobile pushes supersede older mobile
push runs. These workflows do not publish store releases or use signing secrets.

The Source release workflow calls both mobile workflows for Android and iOS.
Their native builds and runtime checks are mandatory alongside macOS, Windows
and Linux validation before a release can be packaged or published. A manual
Source release run validates and packages without publishing a release.

Native build jobs additionally run the actual Toga app in Briefcase test mode on
an Android emulator and iPhone Simulator. Fifteen required UI cases cover the hub,
preferences, documents, rendered Markdown, rendered EPUB chapters, bookmarks and
native comic image decoding, a loopback-only streamed LM conversation and
embedded rclone credential import/browsing/private copies, secure credentials,
and LocalCrypt reading, text/Markdown edits, comic/EPUB metadata edits (including
inner AES ZIP passwords), save-conflict preservation and locking, plus local folder operations and Save As
across Local/LocalCrypt boundaries. The file-management case also verifies shared
list/tile selection, thumbnails, file details, folder taps, Back across storage,
search/sort and a streamed 40 MiB comic metadata save. The comic-reader case also
imports and reads a 257 MiB ordinary archive and standalone AES/ZipCrypto comics,
including password retry, cancel/lock behavior and unchanged encrypted copies.
Source/backend checks reject missing or stale reports. Reports are emitted in
ordered base64 chunks to avoid native log-line truncation.
Each app run has a 15-minute bound within its build job. These automated cases do
not interact with real system document pickers.

Build success establishes packaging. Runtime core success establishes the tested
document/storage operations. Native picker interactions, touch/keyboard behavior,
real suspension and physical devices still need separate validation. Simulator
app archives are not installable iPhone releases.

Framework references: [Toga platforms](https://toga.beeware.org/en/stable/reference/platforms/),
[Briefcase configuration](https://briefcase.beeware.org/en/stable/reference/configuration/),
[Android build tutorial](https://tutorial.beeware.org/tutorial/tutorial-5/android/),
[iOS build tutorial](https://tutorial.beeware.org/tutorial/tutorial-5/iOS/).
