# Logistics mobile prototype

New to mobile development? Start with the [build and release handbook](mobile-handbook.md)
for Mac setup, Xcode, simulator/phone runs, TestFlight, Android and private backups.

This independent Toga application targets Android and iOS. It opens imported text
and Markdown as app-private copies, edits them, saves their original encoding and
line endings, and checkpoints drafts for recovery. Its hub also opens a private EPUB/CBZ library
with chapter/page navigation, standalone AES/ZipCrypto CBZ password prompts,
bookmarks and saved progress, plus text LM chat
with private history and explicit server connections, and embedded rclone
browsing/direct previews using credential ZIPs, plus directly configured SMB/Mac servers
with device-protected saved credentials. Managed Local/LocalCrypt folders support
repeatable Pull and reviewed Push with progress while ordinary documents remain
usable. Ordinary iPad windows have independent workspaces and exclusive writers. It does not launch the desktop
Qt application or install its dependency list.

See the [user guide](../user_mobile/user_mobile.md) and
[architecture and validation guide](mobile-preparation.md).

## Build Deployment Manager

Use the standalone [Build Deployment Manager](../user/build-manager.md) for builds, validation and delivery. Add or select Logistics, choose platforms and destinations, review the plan and run it. For local installs, choose Delivery → Dev devices and the saved Android or iPhone / iPad recipients. For tester distribution, choose Firebase or TestFlight; each upload requires review of the prepared artifact and destination.

The six legacy deployment `.command` shortcuts and their separate window and sequencer were retired. The following sections describe retained project helpers and low-level setup/diagnostics. Calling a helper directly does not establish the manager’s validation gates.

## Android device helper

Connect and authorize an Android device with USB debugging, or start an emulator,
then use Android test devices in the manager. Its retained helper stages the current local Logistics
and tracked commonUtils sources (including uncommitted edits), updates the normal
Briefcase project, rebuilds the native bridge and APK, installs in place and opens
the app. If several devices are connected it asks which one to update.

Briefcase provisions its Android SDK/JDK during setup; the helper also recognizes
`ANDROID_HOME` / `ANDROID_SDK_ROOT` and `BRIEFCASE_HOME`. Go and the mobile Python
environment are required as for iOS. The first Android build may download large
SDK/NDK dependencies. This is a local debug build, not Play Store distribution.
Before compiling, the helper reads the targets' installed version codes and
reserves a code above those builds and the saved Firebase/local build counters.
A Gradle override applies it and refreshes the version name from the current
manifest without rewriting tracked version settings. Firebase
also considers local deployment reservations when assigning its next build.
Before installation, APK certificate checks preserve the installed signing identity.
If the installed app uses the saved beta key, the helper signs a deployment copy
with that key and verifies the certificate again. Missing or unknown keys stop
before installation; the helper never replaces keys or uninstalls the app.
The first launch may take up to 90 seconds on slower devices; a startup timeout
is reported without undoing a successful installation.

Optional Terminal usage: `mobile_build/.venv/bin/python -m mobile_build.deployment.android_deploy --device SERIAL` or
`mobile_build/.venv/bin/python -m mobile_build.deployment.android_deploy --build-only`. Build/install logs are under
`mobile_build/logs/android-*.log`. It builds local sources; it does not pull from GitHub.
The helper remembers the configured local SDK/cache paths and attempts to
reconnect advertised wireless ADB devices using existing pairing keys. Pair once
through Android Wireless debugging. Wake the tablet and enable that setting if
the firmware switches it off; the app's **Settings → Developer settings…** opens
the native developer screen. Discovery cannot enable debugging on the tablet.
Several connected devices still require a selection.
New Logistics modules still need registration in the mobile source manifest.

## Firebase setup and counter compatibility

Use Firebase delivery in the manager to prepare and review a signed APK for
the configured Firebase App Distribution group. The retained Firebase helper
provides the following authentication and packaging mechanics. On first use it downloads the
official standalone Firebase CLI into ignored `.tools/`, opens Google sign-in,
and checks that the Firebase app has the existing Android package identity.
It resolves the configured **Friends** display name to its actual group alias.
Use the Google account that owns the Firebase project. The CLI stores sign-in
credentials in its own user configuration; never commit or share them.

For sign-in without building, run `mobile_build/.venv/bin/python -m mobile_build.deployment.firebase_deploy --login`.
`--check` verifies access and group configuration. Direct helper execution
stages current local sources (including uncommitted edits), builds a release APK,
assigns an increasing version code, aligns/signs/verifies it, then asks before
uploading and notifying testers. `--build-only` saves the signed APK without upload.
No connected Android device, Firebase SDK, Analytics SDK or Play account is needed.
The app ID and group are configured in `firebase-distribution.json`.

Back up ignored `mobile_build/.android-beta/` securely: it contains the persistent
signing key, its private password and build counter. Losing the key prevents
updates to previously distributed builds. Missing signing files stop deployment;
they are never silently replaced. APKs and logs live in `mobile_build/build/firebase/`.
Firebase CLI diagnostic logs stay in ignored `.tools/`.
Release-signed betas cannot update a debug-signed device installation in place;
this helper never uninstalls an app or deletes its data.

Firebase preview and reservation use the pinned manager's `build_manager.versions`
allocator. Logistics supplies the UTC date floor, Android version-code maximum,
Firebase output/history numbers and saved debug-deployment counter. The existing
`.android-beta/build.json` (`last_build`) and `build-counter.lock` stay compatible
with older deployers and the local Android installer. A manager-format
`.android-beta/build-manager-counter.json` retains reservations; successful
reservation atomically updates the original `build.json` before returning.
Both records contribute to the next number, so an older writer advancing
`build.json`, or an interrupted compatibility update, cannot make the new
allocator reuse a number. Preview writes neither record. Keep both records in
the private directory backup; do not reset them when pruning generated builds.

## TestFlight delivery

Select TestFlight in the manager. The adapter captures the selected source (including current edits), archives, exports and verifies the signed IPA, then pauses for upload review. Apple processing and beta review can delay tester availability. See [TestFlight setup and diagnostics](mobile-testflight.md).

## Prepare a native build

Launcher artwork is bundled under `resources/icons`: iOS light, dark and tinted
variants, plus Android light/night icons and an Android 13+ themed mask.
The existing `cloud_build.py ios` / `android` steps install these resources after
Briefcase creates or updates its project; local device and TestFlight builds use
the same step. See [icon maintenance](mobile-preparation.md#launcher-artwork).

Use a separate Python 3.12 environment with `briefcase==0.4.5`. Toga backends are
pinned to 0.5.7 in `pyproject.toml`. Install Go 1.26.9 for the native rclone
bridge; Android uses NDK 27.2.12479018 (installed by the build helper if needed). From the repository root, after committing
source changes:

```sh
python mobile_build/tools.py stage mobile_build/payload
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
or remove your previous generated `mobile_build/payload` before staging again. For local
development, `--allow-dirty` permits uncommitted mobile and tracked shared sources.
The release evidence verifier still rejects dirty payloads. Explicit local runs
use `python validation/ui_tools.py run android --device <device> --local` (or `ios`), verify
the staged source fingerprint, and retain a separate `*-native-ui-local.json` report.

Briefcase needs the Android SDK/JDK or Xcode/iOS platform resources. A listed iOS
SDK alone may be insufficient: install the matching simulator runtime through
Xcode Settings → Components before trying a simulator run.

For native iPhone Duo display/bar adaptation, select an installed iOS 27.1 SDK
or newer before creating/building the iOS app:

```sh
export DEVELOPER_DIR="$(python mobile_build/select_ios_sdk.py --path-only)"
```

Run this from the repository root. It selects a compatible installed Xcode;
it does not install one. The iOS native CI job uses GitHub's `xcode-27` image and
rejects an older SDK rather than claiming Duo adaptation. The declared iOS 15
deployment minimum is retained, with newer sidebar APIs guarded at runtime;
an iOS 15 device/runtime remains a separate compatibility check.

## Native navigation foundation checks

The native test-mode suite additionally exercises a four-destination native
container, Apple navigation/split controllers, Android bottom/rail presentation,
native selection callbacks, draft retention, focus and widget cleanup. This
fixture supplements the normal app's Home/Files/Documents/Settings navigation shell.

For live resize and lifecycle checks, build/install the test-mode app first and
run from `mobile_build` with a booted validation device:

```sh
python validation/navigation_tools.py --adb /path/to/android-sdk/platform-tools/adb --device emulator-5554
python validation/navigation_tools.py --ios --device <simulator-uuid> --output logs/navigation/apple-lifecycle
```

These commands activate an isolated, synthetic draft under the test app's cache.
Android exercises keyboard insets, phone/tablet sizes, real activity recreation
and process restoration, and resets its size/density overrides afterward. Apple
exercises scene rotation, background/resume and process restoration. Reports and
screenshots go under `mobile_build/logs/navigation`. They do not establish physical
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

## Build and deploy to a paired iPhone over Wi-Fi

The helper also supports paired iPads. To add one alongside your existing iPhone:

1. Connect the iPad to the Mac by USB, unlock it and accept **Trust This Computer**.
2. In Xcode, open **Device Hub** (or **Window → Devices and Simulators** on older
   versions), select the iPad and complete pairing.
3. On the iPad, enable **Settings → Privacy & Security → Developer Mode**, restart
   and confirm when prompted. Wait for Xcode's device preparation to finish.
4. Copy the iPad's Identifier/UDID from Xcode. For an initial USB deployment, run
   `mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools deploy --device YOUR_IPAD_UDID --allow-wired`.
5. For subsequent wireless deployments, put both devices on the same Wi-Fi,
   unplug USB and run `mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools deploy --device YOUR_IPAD_UDID`.

`--device` also works with `status`, `build` and `launch`, and accepts an exact
device name when unambiguous. It selects a target for that command without
replacing the saved iPhone default or signing team. Omitting it continues to use
the saved device. Builds provision and verify the selected iPhone or iPad before
installation. If configuring a Mac for the first time with several devices
connected, pass `--device` to `configure` explicitly.

For normal installation, select iPhone / iPad delivery and recipients in the manager. For low-level diagnostics, run the `device_tools` module from the repository root with an explicit subcommand. `deploy-all --allow-wired` uses the saved `device_ids` list (or original `device_id`) and permits USB. Personal UDIDs remain in ignored `.device.json`.

Explicit `deploy --device YOUR_UDID` selects one device; `deploy-all` uses the
saved list. Add `--allow-wired` to explicit commands to permit USB. The helper
also accepts `build`, `status` and `launch` (launch without rebuilding).

The helper uses `mobile_build/.venv` and an optional local Go installation at
`mobile_build/.tools/go`. To prepare another Mac:

```sh
python3.12 -m venv mobile_build/.venv
mobile_build/.venv/bin/python -m pip install briefcase==0.4.5
# Install Go 1.26.9 on PATH, or extract it into mobile_build/.tools/go.
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools configure --team YOUR_TEAM_ID --device YOUR_IPHONE_UDID
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools status
```

Use the Python 3.12 environment containing Briefcase 0.4.5, with Go 1.26.9
on `PATH`. The helper selects an installed Xcode with SDK 27.1 or newer,
independently of the Mac's default command-line Xcode selection. Sign in to
Xcode's Apple Accounts settings and obtain your existing development team ID
from Signing & Capabilities. Configure once from the repository root:

```sh
python -m mobile_build.deployment.device_tools configure --team YOUR_TEAM_ID --device YOUR_IPHONE_UDID
python -m mobile_build.deployment.device_tools status
python -m mobile_build.deployment.device_tools deploy
```

The device can be omitted during configuration if exactly one paired physical
iPhone is discoverable. Team and device choices are stored in ignored
`mobile_build/.device.json`; no account credentials are stored. To deploy wirelessly,
pair the iPhone in Xcode, enable Developer Mode, put both devices on the same
Wi-Fi, unlock the iPhone, and unplug USB. Check `status` for `localNetwork` or
`wireless` transport. Explicit `deploy` refuses a wired connection by default;
`deploy --allow-wired` permits an initial USB deployment if desired.
See Apple's [device pairing guide](https://help.apple.com/xcode/mac/current/en.lproj/devbc48d1bad.html).

Each `deploy` stages current local sources (including uncommitted mobile
changes), refreshes the Briefcase project and native licenses, rebuilds the
rclone bridge, restores the normal Logistics launcher, builds a signed arm64
iPhone app, refreshes and verifies its version/build metadata and signature/profile, installs it in place, and launches
it. `build` performs the same preparation and signed build without installing.
This is local development, not release evidence or TestFlight automation.

The bundle ID `io.github.ispaure.logisticsmobile`, saved team, application
identifier and Keychain groups are preserved. Once recorded, a changed signing
identity causes deployment to stop. The helper never uninstalls, resets or
unpairs the device; resolve any reported installation error and rerun.
Do not change the bundle ID or uninstall to work around a signing error.
Enrollment pending may leave Xcode showing a Personal Team. Review the saved
signing identity before switching to a newly available paid team.
Logs are in `mobile_build/logs/device-*.log`, the signed app in
`mobile_build/build/physical-device/Build/Products/Debug-iphoneos`, and successful
deployment details in `mobile_build/logs/device-deployment.json`.

For the first Personal Team launch, iOS may require trusting the developer in
Settings → General → VPN & Device Management. After trusting, run
`mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools launch`; a rebuild or uninstall is unnecessary.
If another launch error appears, inspect the device error instead of treating
every security error as a trust problem.

If building directly in Xcode after simulator test runs, run `configure` again
with the saved team/device first. Briefcase `update` alone does not restore
the `MainModule` launcher left by test mode. Configuration also reapplies the
saved team to regenerated Debug and Release configurations.

## Prepare a TestFlight release

The [TestFlight guide](mobile-testflight.md) covers local
archive/export/upload commands and the manual GitHub workflow. Release packaging
uses a separate workspace and preserves `io.github.ispaure.logisticsmobile` plus
the existing application signing identifier and effective Keychain groups.
Uploads default to off. Enrollment was confirmed approved on 2026-10-14. A retained
local record confirms build `202610145` uploaded and was assigned to Friends with
beta review submitted. This is historical evidence, not a live Apple review status;
check App Store Connect before releasing again. A new Mac still needs account,
signing and API setup, and each release needs committed sources and any required
encryption compliance answers.
The guide includes prepared beta description, testing instructions and review notes.
Future explicit uploads are configured to assign their processed build to the
external **Friends** group, submit beta review when needed and enable tester
notifications. This requires a one-time App Store Connect API key setup; follow
[external distribution configuration](mobile-testflight.md#automatic-distribution-to-friends).
If Apple processing or review prerequisites block distribution, the `distribute`
command retries the existing build without uploading it again.
Native iOS builds also embed the Python provider's OpenSSL privacy manifests for
the bundled SSL and hashing libraries. Release inspection checks those manifests
before export/upload to catch the missing-manifest issue Apple reported for the
first uploaded build.

## Host validation

Use the [shared environment setup and check commands](testing.md#run-everyday-checks)
for desktop and mobile host tests. From the repository root (`py` instead of
`python3` on Windows):

```sh
python3 dev.py test desktop 'test_mobile_*.py'
python3 dev.py test mobile
```

The first command runs desktop-side mobile contracts using root `.venv`; the
second runs widget/workflow contracts using `mobile_build/.venv` and the dummy Toga
backend. A filename or quoted glob selects a focused file or group. Each file
runs in a fresh process; failures and per-file timeouts fail the command.
These host checks do not certify device interfaces.

For the standalone host smoke, use the desktop environment directly:

```sh
# macOS / Linux
PYTHONPATH=Python:Python/tests .venv/bin/python -m mobile.smoke --target host
```

On Windows PowerShell, set `$env:PYTHONPATH = "Python;Python/tests"` and run
`.venv/Scripts/python.exe -m mobile.smoke --target host`.

## Hosted builds and runtime checks

[Native builds](../../.github/workflows/mobile-build.yml) produce an Android debug APK
and an iOS Simulator app archive. [Runtime checks](../../.github/workflows/mobile-runtime.yml)
build the pinned CPython 3.14.7 testbeds and execute 37 Logistics document/core
cases inside actual Android and iOS interpreters. Result verification requires
the expected runtime, clean source commits, every case and zero failures or skips.

Both workflows run for changes to their mobile source paths on `alpha`; they also
define manual Android/iOS/both controls. GitHub exposes manual controls after the
workflow is present on the default branch. Native builds have a 60-minute upper
bound; cold interpreter/testbed jobs have a 90-minute upper bound. Diagnostic
artifacts remain available for 14 days. New mobile pushes supersede older mobile
push runs. These workflows do not publish store releases or use signing secrets.

The Source release workflow calls both mobile workflows for Android and iOS.
Their native builds and runtime checks are mandatory alongside macOS, Windows
and Linux validation before a release can be packaged or published. A manual
Source release run validates and packages without publishing a release.

The native UI runner invokes Briefcase through its own Python interpreter
(`python -m briefcase`), so it uses that environment's pinned dependency instead
of a potentially stale or unrelated console script on PATH. Run the tool with
the prepared mobile host environment.

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
