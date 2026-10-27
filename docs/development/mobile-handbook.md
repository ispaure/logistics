# Build and release Logistics Mobile yourself

Start here if you have never developed for iOS or Android. This guide describes
this repository's existing tools; you can run them in macOS Terminal without an
AI assistant. The [technical mobile README](mobile-launchers.md) and
[TestFlight reference](mobile-testflight.md) explain the implementation in depth.

## Understand the pieces

You edit Python source. **Briefcase** turns it into an Apple or Android project.
**Xcode** compiles and signs the Apple app. **App Store Connect** is Apple's web
portal for uploaded builds and testers. **TestFlight** is the app testers use to
install beta versions; uploading is separate from Apple's processing and review.

| Location | What you do here |
| --- | --- |
| `Python/mobile/` | Edit the mobile application |
| `Python/features/`, `Python/services/` | Edit feature/service source; mobile staging selects supported modules |
| `Python/commonUtils/` | Shared library, maintained in its own Git repository/submodule |
| `mobile_build/` | Build helpers, project configuration, native bridge, tests and artwork |
| `mobile_build/payload/` | Generated copies of selected source; do not edit |
| `mobile_build/build/` | Generated Xcode/Android projects, built apps and release workspaces; do not use as source |
| `mobile_build/logs/` | Local diagnostic logs |

A source change does not automatically update an existing Xcode project. The
source must be staged, Briefcase updated, and the app rebuilt. The paired-iPhone
helper performs these steps for you. Generated folders are ignored by Git.
Keep release archives and their records if you need release history; they are
not included in a source checkout.

## Set up a Mac

1. Install Git, Python **3.12**, and Go **1.26.9**. This is the current repository
   toolchain; the desktop environment is separate. Official downloads:
   [Python](https://www.python.org/downloads/macos/) and [Go](https://go.dev/dl/).
2. Install Xcode, open it once, accept its license and let first-launch components
   finish installing. In **Xcode → Settings → Components**, install an iOS simulator
   runtime. Release validation pins the **27.1.x SDK series** (27.1 on the current runner),
   rather than automatically selecting a newer beta SDK;
   that is a project requirement, not a claim about Apple's upload minimum.
3. Clone the intended branch with its shared library. Commands below assume
   `~/GIT/logistics`; use your actual location if different:

   ```sh
   mkdir -p ~/GIT
   cd ~/GIT
   git clone --branch alpha --recurse-submodules https://github.com/ispaure/logistics.git
   cd logistics
   python3.12 -m venv mobile_build/.venv
   mobile_build/.venv/bin/python -m pip install briefcase==0.4.5 -r mobile_build/requirements-testflight.txt
   ```

   For an existing checkout, inspect `git status` before updating. Once your work
   is saved, `git pull --ff-only` updates the current branch and
   `git submodule update --init --recursive` checks out its pinned commonUtils.
   Save any commonUtils work before changing its checkout too. New mobile work
   currently lives on `alpha`; `main` may contain an earlier revision.
4. Open Terminal in the repository and prepare each new Terminal session:

   ```sh
   cd ~/GIT/logistics
   source mobile_build/.venv/bin/activate
   export PATH="$PWD/mobile_build/.tools/go/bin:$PATH"
   export DEVELOPER_DIR="$(python mobile_build/select_ios_sdk.py --path-only)"
   python --version
   go version
   python -m briefcase --version
   ```

   The optional `.tools/go` path supports this Mac's private Go installation;
   otherwise `go` must already be on PATH. Stop if tool selection reports an error.

## Run in an iPhone simulator and open Xcode

A simulator is a virtual phone on your Mac; it does not install onto your iPhone
or upload anything. From the repository root in the prepared Terminal:

```sh
python mobile_build/tools.py stage mobile_build/payload --allow-dirty
cd Mobile
python cloud_build.py licenses
python -m briefcase create iOS --no-input
python cloud_build.py ios
python -m briefcase build iOS --no-input
python -m briefcase open iOS
```

For subsequent builds, first move the old `mobile_build/payload` to a unique backup
location (for example `mobile_build/build/payload-before-edit-1`, creating `build` if
needed). Staging requires a new destination and will not overwrite one. Repeat
staging and licenses, then use **`update` instead of `create`**, followed by
`cloud_build.py ios`, `build` and `open`. `--allow-dirty` is for local development;
release staging requires committed sources. All `cloud_build.py` commands above
run from `mobile_build`, not from the repository root.

In Xcode:

1. Select the **Logistics Mobile** scheme in the toolbar.
2. Select an installed **iPhone Simulator** as the run destination beside it.
3. Choose **Product → Run** (or press **Command-R**). The app should show its normal
   Home screen. Use the square Stop button to end the debug session.
4. If a build fails, open the **Report navigator** (Command-9), select the failed
   build and read the first relevant error. Build logs are more useful than the
   final generic “build failed” message.

The generated project is
`mobile_build/build/logisticsmobile/ios/xcode/Logistics Mobile.xcodeproj`.
Use `briefcase open iOS` to open the correct project. Lasting changes belong in
source/configuration/build helpers, because project regeneration can replace
manual edits in Xcode. Automated native UI checks use a special test launcher;
a normal Briefcase update **and build** restores the application launcher.

## Run on your own iPhone

For the initial setup, sign into **Xcode → Settings → Apple Accounts**. Connect
with USB, accept trust prompts, and select the phone in **Window → Devices and
Simulators**. Enable Developer Mode on the iPhone when prompted. Apple explains
[Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)
and [running on a device](https://developer.apple.com/documentation/xcode/running-your-app-in-simulator-or-on-a-device).
For wireless use, pair first and keep the phone and Mac on the same Wi-Fi.

Use your **existing** Apple development team ID and the paired phone's identifier
(UDID) from Xcode. Replace the example values below; do not enter them literally:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools configure --team YOUR_TEAM_ID --device YOUR_IPHONE_UDID
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools status
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools build
```

These commands run from the repository root. `configure` saves local choices,
`status` checks them, and `build` creates a signed app without installing it.
To install and launch wirelessly, unlock the phone, unplug USB, then run:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools
```

For normal installation, select the device in the Build Deployment Manager. For an explicitly
wired diagnostic installation use `mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools deploy --allow-wired`.
After a first-launch trust prompt, trust the developer in the iPhone's
**Settings → General → VPN & Device Management**, then run
`mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools launch` to retry without rebuilding.

Keep the bundle ID **`io.github.ispaure.logisticsmobile`**, existing team and
Keychain identity. Signing errors need their underlying account/profile problem
resolved; uninstalling or choosing a new bundle ID is not a recovery step. The
helper installs in place. See [device deployment](mobile-device-deployment.md)
for checks and log locations. To run directly from Xcode, run `configure` again
after generated-project/test changes, then choose the paired phone and Command-R.

## Send a version to TestFlight

A successful local phone build does not send anything to testers. Distribution
requires Apple Developer Program membership, the existing app record in
[App Store Connect](https://appstoreconnect.apple.com/), distribution signing,
beta contact/testing details, and completed encryption questions. The tracked
configuration targets the external **Friends** group. External builds may need
Apple beta review; [Apple's overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)
explains that process.

1. Follow [one-time API setup](mobile-testflight.md#api-setup-and-distribution) to
   save an App Store Connect team API key reference on this Mac. Install the
   requirements from the Mac setup above. `python -m mobile_build.deployment.testflight_external check`
   verifies account/app/group access without uploading.
2. Make sure the intended source and commonUtils revision are committed and
   pushed. A local commit alone is not a GitHub backup. Review `git status` and
   `git -C Python/commonUtils status`; generated files and private keys stay out
   of commits. Do not use an unsigned rehearsal for an upload.
3. Check App Store Connect's TestFlight tab for the latest build number. Choose
   a new increasing number, at most nine digits, unused both there and under
   `mobile_build/build/testflight`. The number below is illustrative: replace it.
4. In the prepared Terminal at the repository root, use the **same number** for
   each step of this release:

   ```sh
   MOBILE_RELEASE_NUMBER=202610151
   python -m mobile_build.deployment.testflight_tools plan --build-number "$MOBILE_RELEASE_NUMBER"
   python -m mobile_build.deployment.testflight_tools archive --build-number "$MOBILE_RELEASE_NUMBER"
   python -m mobile_build.deployment.testflight_tools export --build-number "$MOBILE_RELEASE_NUMBER"
   ```

   `plan` previews identity and settings. `archive` compiles the release.
   `export` creates and checks its IPA, the installable distribution package.
   Review their output and retained files before proceeding. The configured
   `.device.json` must include the signing identity from a successful device
   build, or you must supply the existing explicit release identity as described
   in the [reference](mobile-testflight.md#local-commands).
5. When you intend to send it to Apple and the configured testers, run:

   ```sh
   TESTFLIGHT_UPLOAD=1 python -m mobile_build.deployment.testflight_tools upload --build-number "$MOBILE_RELEASE_NUMBER"
   ```

   The upload also attempts Friends assignment, beta-review submission when
   needed, and tester notifications. It does not publish an App Store release.
6. Open **App Store Connect → Logistics Mobile → TestFlight**. Check processing,
   encryption information, review status and Friends group membership. Upload
   success alone does not mean the build is ready for testers. Testers install
   Apple's TestFlight app and accept their invitation.

If upload succeeded but processing/distribution stopped, resolve the reported
issue, then resume the existing build with:

```sh
python -m mobile_build.deployment.testflight_tools distribute --build-number "$MOBILE_RELEASE_NUMBER"
```

This does not upload again. An invalid binary needs a fixed build and a new
number. If archiving failed after creating its workspace, preserve that directory
for diagnosis and choose another number for the next archive attempt.

Release records live under `mobile_build/build/testflight/<number>/`: `release.json`,
`Logistics.xcarchive`, `export/*.ipa`, `export-verified.json`, `upload-result.json`,
`external-distribution.json` and `logs/`. Keep them in a separate release backup.
A recorded group assignment does not establish that Apple has approved review.

The alternative hosted route is **GitHub → Actions → Logistics TestFlight
preparation → Run workflow**. It needs the `testflight` environment's signing
secrets and variables first; follow the [GitHub setup](mobile-testflight.md#github-configuration-after-approval).
Choose the intended branch and a new build number. Leave upload off for a
rehearsal. The hosted native-build and runtime workflows validate first. Their
availability does not prove your account's secrets or runner access is configured.

## Build and run Android

Android uses the same mobile Python source. For local builds install Android
Studio, its SDK/command-line tools and an emulator image; use Java **17** as in
this repository's native-build workflow. Open Android Studio's SDK Manager to
find the SDK location and its Device Manager to create/start a virtual phone.
Set `ANDROID_HOME` to that actual SDK directory (the usual Mac location is shown):

```sh
export ANDROID_HOME="$HOME/Library/Android/sdk"
```

Use the Python/Go environment above. Prepare a fresh payload from the repository
root as in the simulator steps, then from `mobile_build`:

```sh
python cloud_build.py licenses
python -m briefcase create android --no-input
python cloud_build.py android
python -m briefcase build android --no-input
python -m briefcase run android
```

The bridge helper requires the SDK environment variable and installs NDK
**27.2.12479018** with `sdkmanager` if absent; accept Android SDK licenses during
setup. On subsequent builds, restage source, use `update android` instead of
`create android`, rerun licenses and the bridge helper, then build/run.
Briefcase prompts for an emulator/device. A physical Android phone needs USB
debugging enabled and the computer authorized. See the
[BeeWare Android tutorial](https://tutorial.beeware.org/en/latest/tutorial/tutorial-5/android/)
for SDK/device setup.

The debug APK is
`mobile_build/build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk`.
The current repository has debug build/runtime automation; it does **not** provide
a Google Play upload/release-signing workflow. TestFlight only distributes Apple
apps. Play publication would need its own signing and store setup.

## What to back up and what can be rebuilt

GitHub preserves pushed source, not the whole working computer.

| Item | Recovery plan |
| --- | --- |
| Logistics commits and commonUtils commits | Push both repositories; commit the shared revision pointer in Logistics |
| `mobile_build/.device.json` | Private backup of team/device and signing/Keychain baseline; restore before rebuilding an existing app identity |
| `mobile_build/.testflight-auth.json` | Private backup of API key reference; reconfigure its absolute path on another Mac |
| `.p8` in `mobile_build/.testflight-keys/` or elsewhere | Encrypted private backup, never Git; a reference file alone does not preserve the key |
| Signing certificates/private keys in macOS Keychain | Use Xcode/Keychain export or Apple account recovery; these are outside the source checkout |
| GitHub environment secrets and Apple account access | Retain access/recovery information privately; repository cloning does not restore these |
| Release archives, IPA and release records | Separate backup if you need distribution history/debug symbols; do not treat all of `build` as expendable |
| `mobile_build/payload`, generated projects, `.venv`, `.tools`, `.briefcase` | Recreate with these instructions and the pinned tools |
| App documents and credentials on a device | Separate app-data/export backup; a Git checkout does not contain them |

The optional external feature link is maintained in its own repository and is
excluded from public mobile builds. It is not part of a Logistics clone.

## When something fails

| Symptom | Next step |
| --- | --- |
| `python3.12`, `go` or Briefcase missing | Check tool installation and activate `mobile_build/.venv` in this Terminal |
| No compatible SDK/runtime | Install the required Xcode/platform/runtime, then rerun the SDK selector |
| Payload already exists | Move the old generated payload aside; stage into a new directory |
| Edited source does not appear | Restage, update Briefcase, rerun the platform bridge helper and rebuild |
| App opens tests instead of Home | Normal `briefcase update iOS` and `build iOS`; reconfigure signing for direct device use |
| Signing/profile/team mismatch | Check saved identity, Xcode account, membership and profile; retain bundle ID and existing data |
| Wireless install fails | Check `mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools status`, initial pairing, same Wi-Fi and unlocked phone |
| TestFlight says processing/review pending | Check App Store Connect; use `distribute` after prerequisites are resolved |
| Apple rejects an uploaded binary | Read Apple's specific error; repair source/packaging and use a new build number |

Device logs: `mobile_build/logs/device-*.log`. Release logs:
`mobile_build/build/testflight/<number>/logs/`. Xcode: Report navigator. Source checks
and host tests are described in [docs/development/mobile-launchers.md](mobile-launchers.md#host-validation);
passing them does not replace simulator and physical-device testing.


## Android tester distribution helpers

Use Firebase delivery in the [Build Deployment Manager](../user/build-manager.md).
Its retained `firebase_deploy.py` helper uses
interactive Firebase CLI Google sign-in, verifies project access and the registered
Android package, and resolves the configured tester group by alias or display
name without assuming capitalization. Authentication/setup failures stop before
native build preparation. `--login` signs in and verifies setup without building;
`--check` verifies existing access. Firebase configuration lives in
`mobile_build/firebase-distribution.json`; private credentials are never stored there.

The builder reuses Android local-source staging and the rclone bridge helper.
Existing generated projects refresh their Python requirements as well as app
sources, so added dependencies are included in the next device or beta build.
It uses Gradle `assembleRelease` with a temporary init script for versionCode,
then SDK zipalign/apksigner and aapt for signature and package/version verification.
It does not rewrite debug signing or the generated project's default version.
The persistent PKCS12 key/password and reserved version counter live under ignored,
owner-only `mobile_build/.android-beta/`; back up this directory securely. A nonblocking
lock prevents concurrent beta runs. Device deployment and beta building share
the generated project/payload: do not run them concurrently in separate terminals.
Builds/logs are under `mobile_build/build/firebase/<number>/`. No device is installed
or uninstalled by the beta builder. Upload requires an explicit confirmation.
Firebase handles invitations and notifications; testers approve APK installation.

Use the standalone [Build Deployment Manager](../user/build-manager.md) to combine checks and delivery. The legacy sequential deployment launcher has been removed. Direct helper commands are setup/diagnostic paths.

## Android device helper

For a normal Android app, `mobile_build/.venv/bin/python -m mobile_build.deployment.android_deploy` stages current Logistics
and commonUtils sources and refreshes Briefcase before each build. It rebuilds
both bridge ABIs, resolves the SDK and cached JDK, then installs the debug APK with
`adb install -r` and launches the normal activity. The normal Briefcase build
restores its app entry point even if the generated project last ran native tests.
An unauthorized/missing device or failed upgrade stops the workflow; it never
uninstalls or clears app data. Multiple ready devices require a selection or
`--device SERIAL`. Use `--build-only` to stop after creating the APK. See
[the helper reference](mobile-launchers.md#android-device-helper)
for prerequisites and log locations.

## Duo rotation and fold verification

Release SDK selection stays in the 27.1.x series even when the runner also has
a newer beta. An intentional SDK-series upgrade requires updating the selector's
requested series and revalidating all three device families. Native test mode
records Python fault stacks through a real cache-file descriptor; failed-run
diagnostics retain a fresh fault log even when a native crash prevents the final
JSON report. Earlier devices' cached reports never stand in for that crash.

The iOS CI job keeps separate ordinary iPhone, iPad and Duo runs while reusing
the simulator build. `ui_tools.py ios-device` excludes Duo, `ios-ipad` selects
an iPad and `ios-duo` selects Duo using its simulator device-type identifier,
including renamed devices. The Duo run requires observed hinge capability and
portrait plus both landscape directions for every tested panel. It preserves
its report separately as `logs/duo-native-ui.json`. SDK preparation checks each runtime’s advertised device types. It downloads the
dedicated iOS 27.1 runtime when Duo support is missing, then creates a dedicated
Duo simulator if the runner has none. A newer generic runtime is not a substitute
for the Duo runtime; see [Apple’s Xcode release notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-27_2-release-notes).
Provisioning failures fail the lane rather than substituting an ordinary phone.
Cold-start horizontal-phone checks still require full tab-label geometry. For
UIKit’s vertical icon rail, the audit checks the mounted rail and ordered native
item titles; retained zero-sized horizontal labels are not the rendered controls.

Rotation evidence records actual scene dimensions, size classes, hinge status
and reserved divisions, alongside retained routes and logical reader/draft
state. It does not infer interface orientation from aspect ratio. Root surfaces
may draw beneath the Home indicator or keyboard; fixed foreground controls are
audited separately against the window safe area.

For a synthetic local audit without replacing the normal app, use an existing
Logistics Simulator build (selected with Xcode 27.1):

```sh
python -m mobile_build.validation.duo_pose_tools --app '/absolute/path/Logistics Mobile.app' \
  --device DUO_UDID --output mobile_build/logs/duo-outer-review
```

This prepares the curated source snapshot in a temporary directory, installs
`io.github.ispaure.logisticsduofoldqa`, runs toolbar/rotation checks, collects
screenshots and reports, and uninstalls that QA bundle even after a failed run.
It preserves the normal app and its data. Each output directory must be new.

For interior validation, first choose the real pose in Device Hub and add
`--pose-sweep`; the audit walks the panels at the observed geometry without
trying to command an unsupported inner interface orientation. Repeat for flat
and partially folded interior displays in tall and wide configurations. The
public simulator CLI and installed XCTest headers expose no fold-position
setter, so these pose changes remain an explicit local Device Hub check.
Apple recommends reserved-region/arrangement APIs for layout rather than hinge
angles; see [adaptive layouts](https://developer.apple.com/videos/play/tech-talks/111463/)
and [preparing and testing Duo](https://developer.apple.com/videos/play/tech-talks/111461/).

Add `--observe-folds --timeout 1800` to keep a retained comic open after the sweep.
Open, close, partially fold and rotate in Device Hub. The monitor checks the
same logical page and route, records actual geometry, and verifies that an
interior right-hand page matches the outer anchor. Its
`comic_fold_round_trip_tested` flag requires all six observed tall/wide exterior,
flat-interior and folded-interior states. `all_fold_poses_tested` remains false:
that comic-only monitor cannot establish every panel's complete pose matrix.
A green exterior CI run does not replace the interior sweeps or this continuity
check. Save the reports with source hashes before claiming native fold coverage.

Boox/browser proportion contracts have host coverage. Physical Boox validation
requires a connected device; after testing, remove temporary QA/probe packages
and verify the main `io.github.ispaure.logisticsmobile` package and its data are
preserved.
