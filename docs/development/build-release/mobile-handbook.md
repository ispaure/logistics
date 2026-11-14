# Build and release Logistics Mobile yourself

Use [Build Deployment Manager](../../user/build-manager-journeys.md) for routine validation, builds and delivery. Briefcase generates native projects from curated Python sources. Edit `Python/` and `mobile_build/` sources; restage and rebuild to update the generated project.

## Checkout and device ownership

Develop in the main `alpha` checkout. If `logistics.releaseWorktree` and `logistics.developmentWorktree` designate separate checkouts, reserve the former and leave physical deployment to its coordinator. Use each checkout's own environments and manager-owned workspaces. Use disposable manager devices for testing. See [retention](build-manager.md#automatic-storage-retention).

## Set up a Mac

Install Git, uv, Python 3.12 and Xcode. Open Xcode to finish component setup and install the configured simulator runtimes. For a new checkout:

```sh
git clone --branch alpha --recurse-submodules https://github.com/ispaure/logistics.git
cd logistics
python3 dev.py setup desktop
python3 dev.py setup mobile
```

Follow [project tooling readiness and repair](../../user/build-manager.md#project-tooling-readiness-and-repair) to install the pinned manager, Go and the language detector wheel. Briefcase 0.4.5 runs separately from desktop Qt. For each manual build shell, activate mobile Python and expose the selected tools:

```sh
source mobile_build/.venv/bin/activate
export PATH="$PWD/mobile_build/.tools/go/bin:$PATH"
export PIP_FIND_LINKS="$PWD/mobile_build/.tools/release-wheels"
```

On an existing checkout, preserve local app and commonUtils edits before pulling or updating the submodule.

## Run in an iPhone simulator and open Xcode

For ordinary builds choose **Build only → iOS** in the manager. For direct Xcode diagnostics from the repository root, select the compatible 27.1.x Xcode installation and build:

```sh
logistics_developer_dir="$(python mobile_build/select_ios_sdk.py --path-only)" &&
python mobile_build/tools.py stage mobile_build/payload --allow-dirty &&
(
  export DEVELOPER_DIR="$logistics_developer_dir"
  cd mobile_build &&
  python cloud_build.py licenses &&
  python -m briefcase create iOS --no-input &&
  python cloud_build.py ios &&
  python -m briefcase build iOS --no-input &&
  python -m briefcase open iOS
)
```

Choose **Logistics Mobile** and an installed iPhone Simulator, then Command-R. Expect Home; check the first error in Xcode's Report navigator on failure. Move the old payload aside before restaging, and use `update` in place of `create` for an existing project. A normal update and build restores Home after native test mode. Keep lasting Xcode settings in the recipe or tracked configuration.

## Run on your own iPhone

Pair in Xcode's Device Hub, enable Developer Mode and use the existing Apple development team. Select an explicit recipient in the manager. For commands and recovery, see [paired deployment](mobile-launchers.md#build-and-deploy-to-a-paired-iphone-over-wi-fi) and [device verification](mobile-device-deployment.md).

## Send a version to TestFlight

In the manager, select TestFlight, inspect the required validation and captured source, then review the verified IPA and destination before uploading. Use an increasing build number and check App Store Connect for processing and beta review. Follow [API setup](mobile-testflight.md#api-setup-and-distribution), [local recovery](mobile-testflight.md#local-commands) or [GitHub signing setup](mobile-testflight.md#github-configuration-after-approval).

## Build and run Android

Install Android SDK/command-line tools, a matching virtual device image and Java 17. Point `ANDROID_HOME` at the SDK. The bridge helper selects NDK 27.2.12479018; accept SDK licenses during setup. For manual diagnostics from the repository root:

```sh
python mobile_build/tools.py stage mobile_build/payload --allow-dirty &&
(
  cd mobile_build &&
  python cloud_build.py licenses &&
  python -m briefcase create android --no-input &&
  python cloud_build.py android &&
  python -m briefcase build android --no-input &&
  python -m briefcase run android
)
```

Use an owned virtual device with the required API/ABI. For rebuilds, move the old payload aside and change `create` to `update`. Expect the normal Home screen. The debug APK is under `mobile_build/build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/`. Use [Firebase setup](mobile-launchers.md#firebase-setup-and-counter-compatibility) for tester builds and the [Android device helper](mobile-launchers.md#android-device-helper) for authorized local installation.

## Back up signing and recovery inputs

Securely preserve `.device.json`, `.android-beta/`, `.testflight-auth.json` and its referenced `.p8`, plus Apple signing keys, private profiles and account recovery. Back up device files separately. Pin or export needed release archives, debug symbols and receipts before [retention](build-manager.md#automatic-storage-retention) retires them.

| Failure | Recovery |
| --- | --- |
| Missing tools/runtime | Check the mobile venv and install the configured SDK/runtime before reselecting Xcode. |
| Stale sources or test launcher | Restage, update requirements and sources, rerun native composition, then build. |
| Signing mismatch | Repair the account/profile while preserving bundle, team and Keychain identity. |
| Wireless device absent | Check paired transport, same Wi-Fi and development-service status. |
| Processing or review incomplete | Check the exact App Store Connect build and resume distribution from its receipt. |

## Duo rotation and fold verification

Hosted native checks reuse one build across ordinary iPhone, iPad and Duo. Keep the required Duo runtime and model; verify actual hinge capability and portrait/both landscapes. From the root with a verified simulator app and leased Duo:

```sh
python -m mobile_build.validation.duo_pose_tools --app '/absolute/path/Logistics Mobile.app' \
  --device DUO_UDID --output mobile_build/logs/duo-outer-review
```

The helper creates and removes `io.github.ispaure.logisticsduofoldqa` and saves diagnostics to a new output directory. Choose flat and partially folded interior poses in Device Hub, tall and wide, and use `--pose-sweep`. Use `--observe-folds --timeout 1800` to verify the retained comic route and logical page across all six observed states. That continuity result covers the comic only. See [platform checks](../testing/platform-checks.md#parallel-native-ios-validation).

For portable regressions run the [host validation commands](mobile-launchers.md#host-validation).

## Hosted Android graphics diagnostics

The native workflow transfers the verified test APK, Briefcase metadata and source manifest into a fresh validation job. It requires 12 GiB free before image install, uses `-gpu software` and runs with `--no-update`. Both jobs must succeed. A 120-second test-app startup watchdog records safe stack locations and layout/loop state before reporting failure. Review the owned emulator and test logs. For physical Boox checks, save evidence, remove temporary QA apps, and verify `io.github.ispaure.logisticsmobile` and its data remain.
