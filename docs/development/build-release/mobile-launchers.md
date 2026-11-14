# Logistics mobile build and deployment commands

Use the [mobile handbook](mobile-handbook.md) for host setup and Briefcase builds. Start operator checks and releases in [Build Deployment Manager](../../user/build-manager.md). The legacy shortcuts and deployment window are retired. Direct commands below support diagnostics; full release gates run through reviewed manager plans.

## Android device helper

Authorize USB debugging or pair Wireless debugging first. Select the saved recipient in the manager. For low-level diagnostics from the root:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.android_deploy --device SERIAL
mobile_build/.venv/bin/python -m mobile_build.deployment.android_deploy --build-only
```

The helper recognizes `ANDROID_HOME`, `ANDROID_SDK_ROOT` and `BRIEFCASE_HOME`. It stages local Logistics/commonUtils, refreshes Briefcase requirements, builds the Go bridge and verifies the APK/target before in-place installation. An explicit `--skip-tests` skips Go bridge tests. The next version code exceeds installed codes and saved Firebase/local reservations. If the installed app uses the saved Beta key, the helper signs and verifies a matching deployment copy. Unknown signing identities stop the install. Allow up to 90 seconds for first launch; logs land in `mobile_build/logs/android-*.log`. See [wireless discovery](mobile-device-deployment.md#wireless-android-discovery-and-recovery).

## Firebase setup and counter compatibility

Select Firebase delivery for the signed APK and configured Friends group. Configure app and destination in `mobile_build/firebase-distribution.json`. The helper installs the official CLI in ignored `.tools/`, checks existing package identity and resolves the group alias. From the root:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.firebase_deploy --login
mobile_build/.venv/bin/python -m mobile_build.deployment.firebase_deploy --check
mobile_build/.venv/bin/python -m mobile_build.deployment.firebase_deploy --build-only
```

Use the project owner's Google account. The direct helper builds from current local files; `--build-only` retains the aligned, signed and verified APK under `mobile_build/build/firebase/<number>/`. Upload requires artifact/destination review. Keep the durable PKCS12 key, password, legacy `build.json` and manager-format counter in a secure backup of `mobile_build/.android-beta/`. Both counters and local debug reservations feed future allocation. Preview reserves nothing. Preserve the key for future updates. Avoid concurrent direct beta and device builds against the same generated project/payload.

## Prepare a native build

Complete [tooling readiness](../../user/build-manager.md#project-tooling-readiness-and-repair). Use the [platform recipes](mobile-handbook.md#run-in-an-iphone-simulator-and-open-xcode) and [prepared wheel cache](mobile-device-deployment.md). Source staging defaults to committed inputs; `--allow-dirty` supports development. Normal app artifacts precede the separate Briefcase test build. The [artwork installer](mobile-preparation.md#launcher-artwork) runs during native composition.

## Native navigation foundation checks

With the test-mode app on an owned virtual device, run from `mobile_build`:

```sh
python validation/navigation_tools.py --adb /path/to/android-sdk/platform-tools/adb --device emulator-5554
python validation/navigation_tools.py --ios --device SIMULATOR_UUID --output logs/navigation/apple-lifecycle
```

Android verifies keyboard insets, resize, Activity recreation and process restoration, then resets size/density. Apple checks scene rotation, backgrounding and restoration. The test fixture owns its synthetic draft. Use independent suites for picker permissions, folds, iPad window independence and physical Boox behavior.

## Open the app in Xcode

From `mobile_build` with the wheel cache exposed and a compatible Xcode selected:

```sh
python -m briefcase update iOS --no-input &&
python -m briefcase build iOS --no-input &&
python -m briefcase open iOS
```

Choose the normal app scheme and simulator. The build restores the normal launcher after a test-mode run. Reconfigure signing before a direct physical build.

## Build and deploy to a paired iPhone over Wi-Fi

Sign into Xcode, pair the phone or iPad by USB and trust the computer. Enable Developer Mode, restart as prompted and finish Xcode preparation. Put both devices on the same Wi-Fi and unplug USB. From the root:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools configure --team TEAM_ID --device DEVICE_UDID
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools status
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools deploy --device DEVICE_UDID
```

Use the existing team; the helper records its identity privately in `mobile_build/.device.json`. Status should show `localNetwork` or `wireless`. Use `--allow-wired` to permit USB. `build` prepares without installing. `deploy-all --allow-wired` uses the saved target list. First launch may require developer trust in Settings → General → VPN & Device Management; rerun `launch` afterward. See [identity checks and recovery](mobile-device-deployment.md).

## Host validation

From the repository root with the [development environments](../testing/testing.md#run-everyday-checks) prepared:

```sh
python3 dev.py test desktop 'test_mobile_*.py'
python3 dev.py test mobile
PYTHONPATH=Python:Python/tests .venv/bin/python -m mobile.smoke --target host
```

On Windows use `py` and set `$env:PYTHONPATH = "Python;Python/tests"` for the smoke command using `.venv/Scripts/python.exe`. The Toga dummy backend verifies host behavior. Use [platform checks](../testing/platform-checks.md) for native UI and embedded runtime evidence.

## Hosted builds and runtime checks

[Native builds](../../../.github/workflows/mobile-build.yml) test development APKs and simulator apps. [Runtime checks](../../../.github/workflows/mobile-runtime.yml) test pinned CPython on Android/iOS. Both have platform-selectable diagnostics and source-bound result verification; full releases require both platforms. For signed Apple distribution, see [TestFlight and Friends](mobile-testflight.md#automatic-distribution-to-friends).
