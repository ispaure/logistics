# Local iPhone and iPad deployment

Mobile packaging installs binary distributions only. Before direct Briefcase diagnostics, device deployment, or preparing
TestFlight/Firebase builds, build the pinned pure-Python language detector wheel
and expose it to the child package installers (run from the repository root):

```sh
mobile_build/.venv/bin/python -m pip wheel --wheel-dir mobile_build/.tools/release-wheels langdetect==1.0.9
export PIP_FIND_LINKS="$PWD/mobile_build/.tools/release-wheels"
```

The native build and TestFlight GitHub workflows prepare the same wheel in their
temporary directories. Generated wheels stay outside tracked source. The local
manager adapter selects `.tools/release-wheels`; use the same cache for standalone
helpers. An existing `.tools/python-wheels` cache also works when explicitly set
through `PIP_FIND_LINKS`, but the manager does not select that older name.

Use the standalone [Build Deployment Manager](../../user/build-manager.md) for device delivery: choose Delivery → Dev devices, select iPhone / iPad and the saved recipients, then inspect and run the plan. The adapter uses `mobile_build/deployment/device_tools.py` for physical-device operations. The low-level setup commands below are developer diagnostics; normal builds and installs go through the manager.

## Reuse a verified Release archive

A release-device delivery exports the already verified archive for the selected
team and recipients. The captured archive build number remains authoritative at
both preparation and installation; the older development counter in the project
configuration does not replace it. Version, plist capabilities, bundle identity,
recursive signatures and every selected device's provisioning membership still
have to match. The adapter retains that build number with the reviewed package.

## Deliver a saved verified build to new devices

In the manager, choose delivery from a saved run, select iOS devices, Android
devices or both, and explicitly select the saved recipients again. The CLI
prepares the same reviewable plan with `retained-delivery RUN --destination
ios-devices --run-value 'devices.ios=["SAVED-UDID"]' --output NEWPLAN.json`.
The selected platform's validation closure, required cleanup and retained Release
preparation must have passed. A failure on the other platform remains recorded
and does not block a separately verified device delivery. This does not establish
that the original combined release passed.

The adapter verifies both retained copies and original artifact hashes, archive
or APK identity, the captured source snapshot and saved signing policy. It uses
that snapshot even when the checkout has advanced, including a verified Current
Files capture; it never rebuilds missing or expired input automatically. Missing,
changed or unverifiable evidence gives an actionable rebuild error. Neither the
original plan/result nor the captured source is rewritten.

Each new delivery has immutable reviewed runner/verifier copies, fresh recipes,
recipients and receipts. Device helpers execute against the captured source's
application metadata, so a newer checkout version cannot silently replace an old
archive's version. Execution rechecks the original review digest, source and
artifact inputs before readiness, export/copy and installation. iOS provisioning
updates are a new explicit execution choice; they permit profile/capability
updates during export without registering devices or compiling an archive. Team,
identity, signature and recipient membership checks remain required. Android
recipients need a saved Beta certificate policy matching the retained Firebase
APK. An incompatible Debug recipient requires an explicit compatible build.

Device availability is shared by normal and retained delivery. **Try once (up to
90 seconds)** is the default and does not retry an unreachable recipient. **Wait
until reachable** retries that recipient without blocking unrelated recipients or
providers. An unreachable device remains not installed; it never produces a
passing delivery result. An uncertain installation requires the manager's
separate, explicitly reviewed retry, with fresh receipt paths and unchanged
source, prepared app and target identity.

## Recover a retained device app after a failed build process

A standalone Duo/iPhone development build can leave a complete signed app even
when Xcode fails to exit. Preserve the failed run and prepare a separate recovery
plan with `python -m logistics_build.device_recovery plan --run FAILED_RUN
--output RECOVERY_PLAN.json`, then inspect and execute that plan through the
manager CLI in a fresh output directory. This supports one selected iOS device
only, with no admitted installation from the failed run.

Recovery restages the captured source to compare its complete payload manifest,
checks the original recipe and signing configuration, and verifies provisioning
membership and recursive signatures using the existing identity. It packages the
retained app without compiling or re-signing it, then uses normal device readiness
and installation checks. Changed or unverifiable output stops recovery. The new
report retains the original failed plan/result identity; it establishes artifact
verification and installation, not a successful compilation or release acceptance.

## Physical development configuration

Routine validation uses the iOS simulator and Android emulator on the computer,
including tablet checks when navigation/layout changes. A paired iPhone can
receive an installation while locked when its development services are available.
Xcode can still refuse the build destination until the device is unlocked; follow
that actual diagnostic. Request an unlock only when development-service admission, physical
hardware behavior or an explicitly requested on-device launch/screenshot check
requires it; ordinary regression checks should not depend on the user unlocking
their phone.

Configuration pins the existing `io.github.ispaure.logisticsmobile` identity,
default paired physical iPhone/iPad UDID and Apple development team in ignored
`mobile_build/.device.json`. Simulator entries and ambiguous device selections are
rejected. Debug and Release target configurations receive automatic signing
with the selected team. An existing different team or bundle ID is rejected;
the helper does not resolve mismatches by changing identity or uninstalling.

`status`, `build`, `deploy` and `launch` accept `--device` to select another
paired physical iPhone or iPad by exact name, CoreDevice identifier or UDID.
For an explicitly requested deployment without tests, use `deploy --skip-tests`
(or `deploy-all --skip-tests`) to omit the otherwise embedded Go bridge tests.
This does not bypass compilation, provisioning or signature verification.
The selection is resolved to its UDID for that command; the saved default device
and shared signing identity remain pinned. `xcodebuild` uses the selected device
as its destination so automatic provisioning can register/include that device.
The profile's device membership and existing signing/Keychain checks still apply.
Pairing, Developer Mode and initial device preparation are completed in Xcode
and on the iPad before invoking the helper. A physical iPad installation and
launch succeeded over USB on 2026-10-15.

The no-argument launcher runs `deploy-all --allow-wired`. `deploy-all` reads an
optional `device_ids` array from the ignored configuration (falling back to
`device_id`) and invokes the normal verified deployment sequentially for each
unique UDID. Personal device identifiers remain local. Each target refreshes
sources and builds for its own provisioning destination. Failure on one device
does not prevent attempts on the others; any failure makes the batch exit
unsuccessfully. Existing single-target commands keep their saved default.
Successful installation/launch reports also persist under
`mobile_build/logs/device-deployment-<UDID>.json`, alongside the latest report.

Each build validates app-owned imports against `APP_MODULES`, then stages the
explicit public mobile source allowlist with local dirty sources allowed, refreshes the generated Briefcase application and native
license notices, rebuilds both native bridge variants, restores the plist's
`MainModule` to `mobile`, and runs a Debug arm64 device build.
Existing projects also refresh Briefcase requirements on every deployment;
source-only updates retain stale `app_packages` and can crash during startup
when newly imported dependencies such as `markdown_it` are absent. The deployment
regression test covers the requirement refresh for existing projects and the
initial creation path.
On 2026-10-17, the physical iPhone console confirmed a startup
`ModuleNotFoundError: No module named 'markdown_it'` in the stale bundle.
After refreshing requirements and installing in place over Wi-Fi, the app
remained running and a physical-device screenshot showed Workspaces with its
existing configured folders. All 11 deployment tests passed; the screenshot is
retained locally at `mobile_build/logs/iphone-startup-dependencies-fixed.png`.
The toolchain selector defaults to the 27.1.x iOS Simulator SDK series and supplies `DEVELOPER_DIR`
to child processes without changing the global `xcode-select` setting.
`cloud_build.ios_compiler` quotes the SDK path in Go's `CC` argument string so
installations such as `Xcode 27.1.app` compile correctly.

Briefcase 0.4.5 updates sources during `update`, but sets `MainModule` only
during its `build` operation. Direct `xcodebuild` after a simulator test run
therefore needs the explicit normal-launcher restoration. A successful native
compile alone is insufficient: the helper verifies the built plist, device
membership in the provisioning profile, signing team, application identifier,
and recursive code signature before installation. Application identifier and
Keychain groups are recorded in the local configuration and must match on
subsequent builds, including after clearing generated build directories.

Briefcase `update` also leaves extra plist settings from project creation in
place. `prepare_project` reapplies the canonical `[tool.briefcase.app.logisticsmobile.iOS.info]`
settings before building; `validate_app` rejects a signed build missing any of
those values. This includes the Local file-sharing keys. The focused deployment
tests cover refreshing an existing generated project, including repeated runs.

## Verify an in-place iOS update

`deploy` verifies CoreDevice transport before installation. It accepts
`localNetwork` and `wireless`. Wired deployment requires `--allow-wired`.
After installation, check that the app launches and existing files remain
available. Compare relative paths and sizes for inventory checks because iOS
can relocate the data-container path. Compare hashes when verifying byte equality.
Use `launch` to retry an already installed app after the first on-device trust step.

For file sharing, confirm the built plist contains both sharing keys. A House
Arrest `VendDocuments` check can write, read and delete a disposable file in
shared Documents and verify that private Application Support stays inaccessible.
Record that protocol check separately from a manual Finder interaction.

`mobile_build/tests/tooling/test_device_tools.py` covers identity rejection,
normal-launcher restoration, device selection and SDK paths containing spaces.
Save build, install and launch evidence in the
[local artifact locations](../testing/validation-artifacts.md#find-an-output).

## Diagnose startup after installation

A successful build, signature, install and process launch can still leave the
app without a usable window. Check the device's unified system log for Python
callback exceptions when `devicectl --console` shows only initialization.
An empty Workspaces page with default star tabs can indicate failure before the
navigation adapter installs. Check the startup traceback before changing icons.

Run the payload and appearance checks from the repository root:

```sh
python3 dev.py test desktop test_mobile_packaging.py
python3 dev.py test mobile test_packaged_startup.py
python3 dev.py test mobile --exact-file mobile_build/tests/workspace/test_appearance.py
```

`mobile_build/tools.py` validates imports against the mobile allowlist before
staging. The packaging test checks that omitting `recent_documents.py` is
rejected. Packaged startup runs with only the staged payload on its application
import path and checks both empty and existing-document storage.

Appearance fixtures cover UIKit bridge shapes for transparent color properties
and callable or property-based size getters used by workspace group headings.
For native diagnosis, verify the window and the affected controls on the
relevant iOS version. Include saved nested groups when the traceback involves
group headings.

## Deployment terminology

When the owner requests **All mobile devices**, deploy in place to the configured
physical iOS devices and connected/paired Android devices. Tester distribution to
TestFlight and Firebase remains a separate action when requested. Preserve signing
identity and app data; do not uninstall to bypass deployment errors.

## Wireless Android discovery and recovery

The project deployment helpers use `mobile_build/deployment/wireless_adb.py`.
The old deployment window is retired; normal reviewed installs use the standalone
[manager workflow](../../user/build-manager-journeys.md).
Discovery first checks ADB's TLS connect advertisements. On macOS, bounded
Bonjour browse/resolve snapshots supplement an empty or incomplete ADB list,
including renamed duplicate service instances after the tablet changes its port.
Unreachable endpoints are skipped; IPv4 is preferred over scoped link-local IPv6.
ADB still authenticates each connection using existing pairing keys. Pairing
advertisements never trigger automatic pairing.

A stale daemon can return “No route to host” even when the discovery process can
open the advertised TCP port. With no ready Android devices, discovery restarts
ADB once and reconnects reachable advertisements. It leaves a daemon serving a
ready device running. Explicit recovery of a daemon serving a ready device is a
separate diagnostic action, not automatic repair during installation. Repairs run outside deployments, briefly interrupt ADB
sessions, and never uninstall apps, clear storage or erase pairing keys.

Focused `test_wireless_adb.py` contracts cover partial Bonjour snapshots, changed
ports, duplicate advertisements, IPv4 ordering, stale-daemon recovery, preservation
of ready-device connections and exclusion of pairing services. Saved private
hardware IDs still deduplicate simultaneous USB and wireless transports.
ADB service and connection names containing spaces, such as renamed `(2)`
instances, remain valid discovery targets.

If USB hardware is visible but absent from the deployment list, another ADB
server can own its interface. Check the server used by other Android tools;
`ADB_SERVER_SOCKET=tcp:localhost:<port>` lets the deployment helpers use
that existing server. Restarting the default server cannot release an interface
owned by a different server.
