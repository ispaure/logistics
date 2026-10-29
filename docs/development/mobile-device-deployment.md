# Local iPhone and iPad deployment

Mobile packaging installs binary distributions only. Before deploying or preparing
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

Use the standalone [Build Deployment Manager](../user/build-manager.md) for device delivery: choose Delivery → Dev devices, select iPhone / iPad and the saved recipients, then inspect and run the plan. The adapter uses `mobile_build/deployment/device_tools.py` for physical-device operations. The low-level setup commands below are developer diagnostics; normal builds and installs go through the manager.

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
The toolchain selector requires SDK 27.1 or newer and supplies `DEVELOPER_DIR`
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

## Local-only file-sharing verification, 2026-10-15

The signed development update was installed in place on the paired iPhone and
launched successfully. Its built plist contains both file-sharing keys. A device
inventory comparison found all 8,678 pre-existing files under the new private
Application Support root with matching sizes, including 8,617 encrypted files
totalling 48,372,039,025 bytes. This comparison checked metadata, not content
hashes. There were no ordinary `LocalFiles` files on this phone before migration;
nonempty Local migration remains covered by the focused host fixtures.

The device's shared Documents directory reported Apple's MobileBackup exclusion
attribute. A real House Arrest `VendDocuments` session over the existing wireless
tunnel wrote/read/deleted a temporary file, verified its bytes, and denied access
to private Application Support storage. The shared directory was empty again
after cleanup. A physical-device screenshot showed the normal Settings UI.
This validates the Documents-only service without claiming a manual Finder USB
interaction. Ignored evidence is retained in `mobile_build/logs/iphone-local-sharing-*`.

`deploy` verifies CoreDevice transport immediately before installation.
`localNetwork` (Xcode 27.1) and `wireless` are accepted; a wired deployment
requires explicit `--allow-wired`. Installation is an in-place CoreDevice app
update, followed by launch. There is no uninstall/reset/unpair operation or
fallback to a different signing identity. `launch` retries an already installed
app without rebuilding, useful after the first on-device profile trust step.
Errors stop the workflow and retain diagnostic logs. Local configuration,
profiles, certificates, payloads, environments, screenshots and device logs
are excluded from Git; no credentials are written by the helper.

Focused unit checks in `mobile_build/tests/tooling/test_device_tools.py` cover identity
rejection, normal-launcher restoration, physical-device selection and SDK
paths containing spaces. Actual build/install/launch evidence lives in ignored
`mobile_build/logs/device-*.log` and `device-deployment.json`; this workflow does not
claim the full mobile functional test suite passed on the physical device.

## Local verification, 2026-10-13

Xcode 27.1 / SDK 27.1 built and signed version 0.1.5 for an iPhone 15 Pro Max
running iOS 26.6.2. With USB unplugged, CoreDevice reported `localNetwork`;
installation and launch succeeded after the initial on-device developer trust
step. The persistent launcher also completed a subsequent build/install/launch.
The app process remained running and a device screenshot showed the normal
Logistics UI. All seven focused deployment/SDK unit checks passed, and the
bridge's Go tests passed during the workflow.

After the in-place update, all five existing document/preference files remained
listed by CoreDevice. iOS relocated the data-container path during installation;
path equality is not used as a data-preservation assertion. This check examined
file metadata, not document contents, and does not establish byte-for-byte
data equality. No uninstall, device reset or unpairing was performed.


## Packaged-startup regression (2026-10-15)

`recent_documents.py` must ship with the application: startup imports it before
creating the main window. Omitting it from `APP_MODULES` left the physical iPhone
showing a black screen even though signing, installation and process launch all
succeeded. Simulator probes that overlay the whole source package do not detect
an omitted allowlist entry.

`mobile_build/tools.py` now rejects app-relative imports absent from the allowlist before
creating a payload. Packaging tests remove the recent-documents entry to assert
that this check fails. `mobile_build/tests/tooling/test_packaged_startup.py` stages the actual
allowlist and starts Home in a separate process with only that payload on its
application import path, using empty and existing-document storage. This host test
uses Toga's dummy backend; a successful deploy must still be visually checked on
the physical device when diagnosing native startup problems.


The corrected signed build was installed in place over Wi-Fi on the existing
paired iPhone 15 Pro Max. A physical-device screenshot showed Home and the
existing unsaved document's Continue card. No app uninstall or data reset was
performed. The screenshot and deployment logs are retained locally as
`mobile_build/logs/iphone-startup-check.png` and `iphone-startup-fix-deploy.log`.

## Deployment terminology

When the owner requests **All mobile devices**, deploy in place to the configured
physical iOS devices and connected/paired Android devices. Tester distribution to
TestFlight and Firebase remains a separate action when requested. Preserve signing
identity and app data; do not uninstall to bypass deployment errors.

## Native appearance startup regression (2026-10-18)

The physical iPhone system log identified a startup failure while constructing
the editor's transparent Save button: `apple_color('transparent')` called
`UIColor.clearColor()` even though Rubicon exposes that getter as a color
property. The resulting `TypeError: 'ObjCInstance' object is not callable`
aborted startup before the main window existed, leaving a black screen.
The getter now uses property access. `test_appearance.py` covers painting an
iOS transparent control with a non-callable native color, alongside the
packaged-startup check. The dummy backend alone cannot exercise UIKit getters.

Python callback tracebacks may appear in the device's unified system log even
when `devicectl --console` shows only native Python initialization. Inspect the
system log when installation and process launch succeed without a usable UI.

The corrected signed build was installed in place on the paired iPhone over
Wi-Fi. A physical-device screenshot showed Workspaces and the destination bar;
the local evidence is `mobile_build/logs/iphone-startup-appearance-fixed.png`.
All 10 focused appearance and packaged-startup tests passed. No uninstall or
app-data reset was performed.

## Grouped workspace startup regression (2026-10-18)

The physical iPhone log exposed an `AttributeError` in `folder_hub_style.tree_anchor`:
on its UIKit version, Rubicon exposes `intrinsicContentSize` as a bound method.
Reading `.width` directly aborted startup while building saved nested workspace
groups, before installing the native navigation adapter. The partially built
window showed Toga's default star tab icons and an empty Workspaces page.
An empty test workspace did not exercise the failing group-heading measurement.

`tree_anchor` now resolves either a callable getter or a size property before
reading the width. The appearance regression test covers both bridge shapes and
the long-heading anchor limit. When investigating default stars together with
missing page content, inspect startup exceptions before changing tab artwork.

The fix was installed in place on the paired iPhone and iPad. Physical iPhone
screenshots confirmed the normal destination icons and the populated, saved
Cloud workspace hierarchy. Local evidence is retained at
`mobile_build/logs/iphone-workspace-startup-fixed-home.png`,
`iphone-workspaces-restored.png` and `iphone-workspace-startup-failure.log`.
All 44 appearance, workspace-hub and packaged-startup host checks passed.
No uninstall or app-data reset was performed; this does not certify every
feature workflow on the physical devices.

## Wireless Android discovery and recovery

The project deployment helpers use `mobile_build/deployment/wireless_adb.py`.
The old deployment window is retired; normal reviewed installs use the standalone
[manager workflow](../user/build-manager-journeys.md).
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
