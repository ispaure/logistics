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

## Simple deployment window

Double-click `Mobile/deploy_test_devices.command` for the small PySide window.
It uses the root `.venv` for PySide6 and `Mobile/.venv` for build tools. Existing
SDK, Go, signing, device and tester-group settings are reused.

- **Deploy test devices** checks availability first, builds Android once, updates
  each authorized Android device and deploys to the available saved physical
  iPhones/iPads in `.device.json`. Android and iOS run at the same time, with
  devices within each platform updated one at a time. Offline devices are skipped; failed updates
  are reported while remaining devices are attempted. Discovery failures make
  the operation report failure even if other available devices were updated.
  Choose **All available devices** or one named device in **Deploy to** before
  clicking. A single-device selection updates only that device. If it becomes
  unavailable, deployment stops before building and never falls back to another
  device. Refresh preserves the selected device. This selection affects only
  local installation; Firebase and TestFlight still use their configured groups.
- **Firebase → Friends** builds/signs with the current Firebase parameters.
- **TestFlight → Friends** archives/exports with the current TestFlight parameters;
  it retains the existing requirement for committed, clean release sources.
- **Refresh** reads device availability again. **Open logs** opens the isolated
  workspaces after test-device operations, or `Mobile/logs` after tester operations;
  distribution output also identifies its build-specific log directory.

Tester buttons ask once in the window after the build is prepared and verified,
before upload and notification. Declining keeps the prepared build on disk.
Firebase sign-in, if expired or missing, must first be completed using
`Mobile/deploy_android_firebase.command --login`; the window reports this rather
than waiting for a hidden terminal answer. Apple processing/review can delay
TestFlight availability. Button labels reflect the current Friends configuration;
the underlying distribution configuration remains authoritative.

Android devices are remembered automatically in ignored
`Mobile/.tools/test-devices.json`, using hardware serials to combine USB and
wireless connections to the same device. New authorized Android connections are
included automatically. iOS membership stays in `.device.json`. Connect the
Galaxy S8+ by USB, enable USB debugging and accept the computer authorization
prompt, then Refresh. Direct APK installation does not require the Play Store.
Older Android wireless ADB requires initial USB setup; modern TLS pairing
discovery does not provide that setup.

The window remains responsive while subprocesses build and deploy. Deployment
buttons are disabled during an operation, and a second launcher window is
prevented. Wait for completion before closing. Existing identity checks and
in-place installation remain in force; deployment never uninstalls the app or
clears its data. The S8+ is not considered validated until it has actually been
connected, installed and tested.

Test-device deployments use separate persistent workspaces under ignored
`Mobile/.deploy-workspaces/android/` and `Mobile/.deploy-workspaces/ios/`. Each
owns its staged payload, Briefcase project/cache, generated native libraries,
build products and logs. The first run creates new projects; later runs reuse
them. Canonical sources, SDK settings and the saved iOS signing/device identity
still come from `Mobile/`; credentials are not copied into these workspaces.
`logs/deployment.log` under each workspace captures that platform's full worker
output; the window prefixes progress with `[Android]` or `[iOS]`. A failed
platform does not cancel the other, and the batch waits for both before reporting
success or failure. A file lock prevents simultaneous batches from changing the
same workspace. The older standalone launchers retain their existing paths.

## Double-click Android deployment

Connect and authorize an Android device with USB debugging, or start an emulator,
then double-click `deploy_android.command`. It stages the current local Logistics
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

Optional Terminal usage: `Mobile/deploy_android.command --device SERIAL` or
`Mobile/deploy_android.command --build-only`. Build/install logs are under
`Mobile/logs/android-*.log`. It builds local sources; it does not pull from GitHub.
The launcher remembers the configured local SDK/cache paths and attempts to
reconnect advertised wireless ADB devices using existing pairing keys. Pair once
through Android Wireless debugging. Wake the tablet and enable that setting if
the firmware switches it off; the app's **Settings → Developer settings…** opens
the native developer screen. Discovery cannot enable debugging on the tablet.
Several connected devices still require a selection.
New Logistics modules still need registration in the mobile source manifest.

## Double-click Android Firebase distribution

Double-click `deploy_android_firebase.command` to send a signed Android APK to
the configured Firebase App Distribution group. On first use it downloads the
official standalone Firebase CLI into ignored `.tools/`, opens Google sign-in,
and checks that the Firebase app has the existing Android package identity.
It resolves the configured **Friends** display name to its actual group alias.
Use the Google account that owns the Firebase project. The CLI stores sign-in
credentials in its own user configuration; never commit or share them.

For sign-in without building, run `Mobile/deploy_android_firebase.command --login`.
`--check` verifies access and group configuration. After setup, double-clicking
stages current local sources (including uncommitted edits), builds a release APK,
assigns an increasing version code, aligns/signs/verifies it, then asks before
uploading and notifying testers. `--build-only` saves the signed APK without upload.
No connected Android device, Firebase SDK, Analytics SDK or Play account is needed.
The app ID and group are configured in `firebase-distribution.json`.

Back up ignored `Mobile/.android-beta/` securely: it contains the persistent
signing key, its private password and build counter. Losing the key prevents
updates to previously distributed builds. Missing signing files stop deployment;
they are never silently replaced. APKs and logs live in `Mobile/build/firebase/`.
Firebase CLI diagnostic logs stay in ignored `.tools/`.
Release-signed betas cannot update a debug-signed device installation in place;
this launcher never uninstalls an app or deletes its data.

## Double-click all deployments

`deploy_all.command` runs the saved iOS device installs, Android device install,
TestFlight distribution and Firebase distribution, in that order, sequentially.
Have your devices available. Each distribution keeps its upload confirmation.
After a failed step it asks whether to continue; the combined run still reports
failure. Canceling an upload leaves its prepared build on disk.

## Double-click TestFlight deployment

On the configured Mac, double-click `deploy_ios_testflight.command` beside
`deploy_ios.command`. It chooses a new build number, archives the committed
sources and exports/verifies the signed IPA. When prompted, type `y` and Return
to upload it and start the configured Friends distribution workflow. Press Return
to keep the prepared build without uploading. Apple processing and beta review
can delay tester availability. The launcher preserves the existing signing identity
and does not install anything on your iPhone. Commit source changes before running.

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

The native test-mode suite additionally exercises a four-destination native
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

## Build and deploy to a paired iPhone over Wi-Fi

The helper also supports paired iPads. To add one alongside your existing iPhone:

1. Connect the iPad to the Mac by USB, unlock it and accept **Trust This Computer**.
2. In Xcode, open **Device Hub** (or **Window → Devices and Simulators** on older
   versions), select the iPad and complete pairing.
3. On the iPad, enable **Settings → Privacy & Security → Developer Mode**, restart
   and confirm when prompted. Wait for Xcode's device preparation to finish.
4. Copy the iPad's Identifier/UDID from Xcode. For an initial USB deployment, run
   `Mobile/deploy_ios.command deploy --device YOUR_IPAD_UDID --allow-wired`.
5. For subsequent wireless deployments, put both devices on the same Wi-Fi,
   unplug USB and run `Mobile/deploy_ios.command deploy --device YOUR_IPAD_UDID`.

`--device` also works with `status`, `build` and `launch`, and accepts an exact
device name when unambiguous. It selects a target for that command without
replacing the saved iPhone default or signing team. Omitting it continues to use
the saved device. Builds provision and verify the selected iPhone or iPad before
installation. If configuring a Mac for the first time with several devices
connected, pass `--device` to `configure` explicitly.

On a configured Mac, double-click `Mobile/deploy_ios.command` in Finder, or run
it from any directory. With no arguments it runs `deploy-all --allow-wired`:
build, verify, install and launch on every UDID listed in the ignored
`Mobile/.device.json` `device_ids` array, using USB or Wi-Fi. Without that optional
array, it deploys only to the original `device_id`. Keep personal UDIDs in that
local configuration, not in the launcher. Each target runs the normal deployment;
a failed target is reported while the remaining targets are still attempted.
The batch exits unsuccessfully if any device fails. Successful per-device reports
are retained as `Mobile/logs/device-deployment-<UDID>.json`.

Explicit `deploy --device YOUR_UDID` selects one device; `deploy-all` uses the
saved list. Add `--allow-wired` to explicit commands to permit USB. The launcher
also accepts `build`, `status` and `launch` (launch without rebuilding).

The launcher uses `Mobile/.venv` and an optional local Go installation at
`Mobile/.tools/go`. To prepare another Mac:

```sh
python3.12 -m venv Mobile/.venv
Mobile/.venv/bin/python -m pip install briefcase==0.4.5
# Install Go 1.26.9 on PATH, or extract it into Mobile/.tools/go.
Mobile/deploy_ios.command configure --team YOUR_TEAM_ID --device YOUR_IPHONE_UDID
Mobile/deploy_ios.command
```

Use the Python 3.12 environment containing Briefcase 0.4.5, with Go 1.26.9
on `PATH`. The helper selects an installed Xcode with SDK 27.1 or newer,
independently of the Mac's default command-line Xcode selection. Sign in to
Xcode's Apple Accounts settings and obtain your existing development team ID
from Signing & Capabilities. Configure once from the repository root:

```sh
python Mobile/device_tools.py configure --team YOUR_TEAM_ID --device YOUR_IPHONE_UDID
python Mobile/device_tools.py status
python Mobile/device_tools.py deploy
```

The device can be omitted during configuration if exactly one paired physical
iPhone is discoverable. Team and device choices are stored in ignored
`Mobile/.device.json`; no account credentials are stored. To deploy wirelessly,
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
Logs are in `Mobile/logs/device-*.log`, the signed app in
`Mobile/build/physical-device/Build/Products/Debug-iphoneos`, and successful
deployment details in `Mobile/logs/device-deployment.json`.

For the first Personal Team launch, iOS may require trusting the developer in
Settings → General → VPN & Device Management. After trusting, run
`Mobile/deploy_ios.command launch`; a rebuild or uninstall is unnecessary.
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
second runs widget/workflow contracts using `Mobile/.venv` and the dummy Toga
backend. A filename or quoted glob selects a focused file or group. Each file
runs in a fresh process; failures and per-file timeouts fail the command.
These host checks do not certify device interfaces.

For the standalone host smoke, use the desktop environment directly:

```sh
# macOS / Linux
PYTHONPATH=Python:Python/tests .venv/bin/python -m logisticsmobile.smoke --target host
```

On Windows PowerShell, set `$env:PYTHONPATH = "Python;Python/tests"` and run
`.venv/Scripts/python.exe -m logisticsmobile.smoke --target host`.

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
