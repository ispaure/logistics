# Build and deployment manager

Open `mobile_build/deployment/deploy_ui.py` with the desktop environment, or use the existing
`mobile_build/deploy_test_devices.command` launcher. The window has a plan tab
and the existing device/tester tab. Passing a test never starts deployment.
Select an operation, platform, backend and source; inspect the ordered plan,
then run the reviewed plan. GitHub, deployment and upload effects require an
explicit confirmation. Existing tester buttons still ask for the final upload
decision after a verified build is ready.

## Implemented operations and extension points

The manager integrates the existing physical-device, TestFlight and Firebase
commands. Local TestFlight/Firebase preparation captures verified artifact
metadata and stops before upload. GitHub operations validate a published branch
or tag against the reviewed commit, record the dispatched run ID, and supervise
that exact run. A release operation pushes shared source before the application
and an unused channel tag, then waits for the existing gated release workflow.
An existing tag is never moved. These capabilities do not grant permission to
publish a project; the operator still chooses and confirms the operation.

Local macOS, Ubuntu/Fedora and Windows commands use the project-owned desktop
plans. Sequential iOS and accelerated local Android backends are implemented and
have complete local acceptance evidence. Windows is implemented; its complete declared plan requires a guest account
with normal-user symbolic-link capability, and missing capability remains a
reported failure. An unavailable
backend fails planning; the manager never silently substitutes hosted validation.
Hosted desktop selection supplies the requested platform input. Normal release
calls continue to require the complete desktop matrix.

## Reusable boundary

The external manager's `build_manager` package contains generic plan/result
contracts, subprocess execution, workspace locking, cancellation, output filtering,
profiles, monotonic local
reservations, the GitHub transport and optional Qt presentation. It imports no
Logistics application, feature tree, app identity or personal configuration.
`Scripts/build_project.py`, `Scripts/build_snapshots.py`,
`Scripts/validation_plans.py` and `mobile_build/deployment/manager_settings.py`
supply Logistics source layout, suites, provider policy and settings.

A project adapter supplies `description`, `operations`, `platforms`,
`interpreter`, `runner_directory`, `results_directory`, `backend_options(target)`
and `make_plan(operation, target, backend, **choices)`. Settings use
`settings_view()`, `save_settings(values)` and `verification_plan()`; an optional
`set_app_version(value)` supports an explicit tracked-source edit. The synthetic
second-project tests run a different root/name and harmless real command through
both the executor and Qt UI without cloud credentials.

The manager has been extracted into a separate repository. Logistics pins its
revision in `build-manager-dependency.json` and retains the adapters, functional
suites and workflows. Install it explicitly in each tooling environment; see
[external manager installation](#external-manager-installation-adapter-api-1).

## Plan, result and source contracts

`Plan` schema 1 records project, operation, source identity, backend, workspace,
effect and ordered phases. A `Phase` carries structured argv, cwd, timeout,
environment overrides, prior dependencies, required/cleanup flags and expected
artifact reports. Plans are trusted executable local configuration, like scripts;
profiles and incoming documents are never interpreted as plans automatically.
Secret environment values are inherited through the existing provider mechanisms;
putting a declared secret value into a serialized phase environment is rejected.
The CLI is `python -m build_manager PLAN.json --output NEW_DIRECTORY`;
side-effecting plans also require `--confirm`.

The executor writes an atomic `result.json`, per-phase redacted logs and captured
artifact reports with SHA-256. Results include exact source, plan hash, UTC times,
elapsed seconds, exit status and queued/running/passed/failed/cancelled states.
Failed dependencies skip their consumers; independent diagnostics and owned
cleanup can still run. Required skips and timeouts fail the result. Cancellation
stops current processes and prevents the next phase from starting. POSIX process
groups are terminated; Windows uses child-tree termination and requires its
backend's real guest acceptance before claiming equivalent cleanup.

Source snapshots contain local Git history and the exact shared pin. Working
development snapshots copy tracked/nonignored edits and deletions and record a
content fingerprint. Ignored credentials, device configuration and external
feature links are excluded. Cached snapshots must still match their recorded
content fingerprint. A dirty shared library must be committed first. Signed
tester preparation requires committed source; protected inputs are linked from
their existing locations only for that selected build, never copied into Git.

## Settings and identity

Settings use a category menu on the left and retained forms on the right, sharing
`commonUtils.ui.settings.navigation.SettingsNavigation` with Logistics settings.
Hover a field or its label for its purpose; timing integers have bounded stepper
controls in seconds. The main plan's optional build number also has a stepper,
with **Automatic** representing no override.

Settings show each effective value's origin: repository defaults, ignored local
profile, environment or one-run override. Save changes the local profile;
changing the app version explicitly edits tracked `pyproject.toml` and requires a
commit. A historical source selection reads its version from that selected commit,
not from the current checkout. Build numbers are separate from app version and release tags.

| Section | Supported fields |
| --- | --- |
| TestFlight | Guarded app/bundle ID; selected external group; enabled state; What to Test; locale; polling interval and processing timeout |
| Firebase | App ID (verified against the guarded package); tester group; release notes |
| Tools | Desktop/mobile interpreter, Xcode developer directory, Android SDK and JDK directories |
| Local targets | iPhone/Duo/iPad template selectors, disposable Android image/model, Linux/Fedora/Windows guest selectors, Linux distro scope/Fedora mode and shutdown preference; availability is validated before execution |
| Legacy reserved targets | `vm.shared_host` and `vm.shared_guest` are shown read-only for compatibility; `android.avd` remains editable to clear a legacy value, and must be empty. Local backends do not attach existing AVDs or mount shared folders |
| Authentication | Existing TestFlight credential JSON and `.p8` references, with Browse/Locate; GitHub repository, credential-helper strategy and token environment name; existing Firebase CLI account storage |
| Signing | Existing manual app and Inbox provisioning-profile file references; pinned team shown read-only |
| Versions | Read-only app version and next iOS/Android build previews; one-run explicit build override; intentional tracked app-version edit; explicit independent release tag |

The local profile is `mobile_build/.tools/build-manager/profile.json` (schema 1,
`values` mapping), overridable with `LOGISTICS_MANAGER_PROFILE`. Existing provider
JSON remains the tracked default. `LOGISTICS_TESTFLIGHT_GROUP`,
`LOGISTICS_FIREBASE_GROUP`, `ANDROID_HOME`, `JAVA_HOME` and `DEVELOPER_DIR` have
visible precedence. Existing `ASC_KEY_PATH`, `ASC_KEY_ID` and `ASC_ISSUER_ID`
override the protected authentication reference; secret values are never shown.
API authentication, signing and destination verification are separate checks.
Hosted workflows use their own repository secret/variable references; Mac-local
key paths are not synchronized, and stored secret values cannot be retrieved.

Connection verification performs read-only app/group/repository checks. It does
not upload, notify, install or dispatch workflows, and it does not claim workflow
write permission from repository read access. Missing configuration is reported.
Automatic build numbers are previewed without allocation and reserved under a
local lock at build start. Explicit values must increase and satisfy platform
limits. Other machines can reserve independently: local locking does not prove
global uniqueness, and provider verification remains authoritative.

Prepared reports capture actual verified embedded version/build, source,
signature identity and the selected destination at preparation. They are copied
into the run result; editing a profile later does not relabel those reports.
Rebuild for a changed identity, or use the existing explicit build-specific
provider retry/resume command after reviewing that immutable build.

## Validation and local outputs

Generic contracts are in the external manager checkout's `tests/`; Logistics
integration contracts are in `Python/tests/tooling` and `mobile_build/tests/tooling`.
The tests exercise
real harmless subprocesses and Qt-to-CLI execution, failure, timeout, cancellation,
workspace conflicts, source privacy, allocation and controlled provider transport.
They do not substitute for the local platform backends' native acceptance.
`python dev.py lint` covers Logistics-owned source. Desktop plans run the installed
manager's tests through `python -m build_manager.contracts`.

Profiles, counters and source workspaces stay under ignored
`mobile_build/.tools/build-manager/`; result plans/logs/reports stay under ignored
`test-results/build-manager/`. Keep keys and personal configuration out of source
and captured artifacts. Existing in-place deployment guards and final upload
confirmation remain in the owning deployment helpers.

## Local macOS acceptance

Select macOS and This Mac. Planning verifies the configured interpreter and records
its Python, OS, architecture and package versions before copying source. The
setup phase loads native Qt and provisions/verifies the pinned rclone executable;
full local runs require the genuine LocalCrypt fixtures rather than silently
skipping them. The remaining phases are the canonical shared/app regressions,
full historical compression parity, manager contracts and release-tooling tests.
Source-plan preparation and environment setup are timed separately from tests.

The GitHub option dispatches the macOS selector in the platform-check workflow.
Normal pushes, pull requests and release calls still default to the complete
matrix; selecting one platform does not change release prerequisites. A local
Apple Silicon run is labelled arm64 with its actual OS and toolchain, rather than
claiming equivalence to other hosted hardware. Use the existing locked desktop
environment (`python dev.py setup desktop`) and repair missing prerequisites
reported by the manager; it never falls back to a different interpreter/backend.

## Parallels Linux backend

The Linux selector accepts existing guest names or UUIDs in `vm.linux` (Ubuntu)
and `vm.fedora`. `vm.linux_scope` is `both` by default; explicit `ubuntu` or
`fedora` runs remain labelled partial Linux coverage. This permits rerunning a
blocked distribution without repeating the other guest's unchanged complete
suite. Full Linux acceptance still requires both distributions. Windows guest
execution is a separate backend and is not inferred from a Linux result.

The reusable `build_manager.parallels` transport discovers guests, starts only a
selected stopped guest, transports an explicit source allowlist over guest tools,
verifies its SHA-256, retrieves reports and removes only token-marked workspaces.
It does not add shared folders or execute against the live host tree. The adapter
includes local Git histories and the exact shared checkout for compression parity;
ignored keys/configuration/builds are excluded. Guest commands preserve literal
argument boundaries across Parallels' Linux shell parser. A harmless second-project
fixture verifies actual transfer, normal-user execution, retrieval and cancellation,
including an owned grandchild in a separate process group.

The guest needs working Parallels Tools, Python 3 with venv support, Git and the
native Qt/WebEngine libraries. Ubuntu additionally needed `libsnappy1v5` and
`libminizip1` beyond the standard headless Qt packages. The preflight reports missing
native libraries before launching the test phase. The runner prepares Python
3.12.2 and locked dependencies in its owned guest workspace, then runs the canonical
platform checks and release-tooling suite. First preparation downloads public
runtime/packages; local execution is not a promise of a fully air-gapped cold setup.
Focused filename patterns use the same locked preparation followed by the selected
contracts. Preparation-only success is explicitly not test-suite success.

Tests run under the existing normal guest account, with browser sandbox protections
retained. Results record actual distribution, aarch64/x86 architecture, original VM
state, transfer/setup/test times, exact source and retrieved phase reports. An ARM
VM result does not establish x86-64 hosted parity. Failed/skipped required phases
cannot become a pass. Cancellation stops only the recorded owned process tree;
completed evidence is retrieved before owned workspace removal. If retrieval or
cleanup cannot finish, the remaining workspace/error is reported for recovery.
`vm.shutdown_after_run` defaults to false; enabling it stops only a guest started
by that run, preserving a guest that was already running. VM creation, resets,
resource changes, disk passphrases and account sign-in are outside this runner.

A guest waiting at an encrypted-disk boot prompt remains unavailable until its
owner unlocks it directly. Missing required guest coverage keeps Linux acceptance
incomplete; installed guest tools or a passing Ubuntu run do not prove Fedora.

## Parallels Windows backend

Select an existing normal-user Windows test guest explicitly. The adapter uses
owned source copies and portable, hash-verified Git/uv archives from
`Scripts/build_manager_tools.json`; it never changes global PATH, login policy,
Developer Mode or signing settings. `vm.windows_prepared_reference` may point to
an ignored preparation report to reuse that guest's public tools/interpreter.
Preparation alone is not validation. The current catalog targets Windows ARM64
with Python 3.12.2 AMD64 under x64 emulation; results identify both architectures
and do not claim native ARM Python or equivalence to hosted x64 hardware.

The complete plan runs native Windows startup, shared/application regressions,
compression parity, generic manager contracts and release-tooling checks.
An explicit `shared:test_filename.py` focused pattern selects shared contracts;
ordinary filename patterns select application contracts. Source transfer retains
Git history and verifies its digest; reports retain actual process exit codes.
PowerShell receives structured data over stdin rather than interpolated shell
commands or an oversized command-line payload. Logs preserve UTF-8/CRLF content.
Windows phases use owned Job Objects assigned before their suspended child runs,
so timeout/cancellation also closes descendants after the parent exits. The UI
uses an owned cancellation marker instead of relying on console window messages.

The first real Windows ARM/emulated-Python full run passed native startup,
compression and manager contracts, but required symlink fixtures failed with
WinError 1314 under the selected normal user's current capability. The adapter
keeps these failures visible; it does not elevate tests or disable OS protection.
A separate timestamp fixture now uses a controlled clock, permission preservation
compares the actual supported initial mode, and Firebase's local advisory lock is
portable. Focused actual Windows corrections and literal Unicode/space argument,
orphan-child, lock, timeout and cancellation checks passed. Full Windows acceptance
remains blocked until all required fixtures can run under an approved environment.
Reports are retrieved before only the token-marked source/test workspaces are
removed; public portable tools may remain cached. Failed retrieval preserves the
owned path with a recovery error rather than deleting its evidence.

### Explicit Fedora container mode

`vm.fedora_mode=container-on-ubuntu` with an explicit
`vm.fedora_container_host` selects rootless Podman in that existing Ubuntu guest;
it is an alternative to the default separate Fedora guest, never an automatic
fallback. The normal guest account needs rootless Podman/user namespace support.
The Fedora 43 definition is `Python/tests/platform/fedora43.Containerfile`.
The adapter hashes the definition, prepares/reuses the matching labelled image,
records the actual image ID/architecture, then executes by that immutable ID.
It records Fedora's own OS release separately from the Ubuntu host kernel.
Cold image preparation uses public package downloads; normal cached tests run
locally, but cold setup is not claimed to be air-gapped.

The full real Fedora43 aarch64/Python3.12.2 container run passed the same shared,
application, compression and manager plan plus release-tooling tests. Together
with the existing complete Ubuntu run and its focused corrections this establishes
both required Linux distributions on this Mac's current ARM VM environment.
Container tests run as the normal UID with default Podman security and the browser
sandbox enabled; no privileged/unconfined flags, kernel protection changes or
root Qt fallback are used. Actual second-project container success and cancellation
also passed. Cleanup verifies the unique ownership label before removing that
run's container, retrieves evidence, and removes only the owned guest workspace.
Public image/package caches remain reusable. One transient Parallels transport
failure was retained before the isolated successful lifetime proof; failed
transports remain failures and are never converted to successful test evidence.

## Sequential local iOS validation

For Test/iOS select **This Mac — iOS Simulators**. Inspect the selected Xcode/SDK,
ordinary iPhone and required Duo runtime/model before launch; optional iPad is
last in the sequence and requires independent-window proof. A missing Duo is an
error, never a request to use another ordinary phone. Device names/UDIDs in local
settings identify templates only. Each operation creates new ownership-labelled
simulators and deletes only those UUIDs after collecting their separate reports;
existing simulator data, physical devices and TestFlight are separate operations.

The app is built in test mode once for the exact source/toolchain/configuration.
Reuse checks its embedded staged manifest, test entry point and complete bundle
content/permissions digest. Local dirty source requires an exact curated manifest;
the clean-source hosted verifier remains strict. Every selected device runs the
canonical 33 native cases and all 260 rotation audits; Duo and selected iPad retain
their additional native contracts. Reports include build, simulator startup,
per-section native timings and owned teardown. The UI distinguishes phase elapsed
time from total elapsed time and streams local case/section checkpoints.
Cancellation stops active work, prevents later devices from starting, and still
runs ownership-checked cleanup. Failed devices retain diagnostics and do not
prevent independent selected devices from collecting useful failure evidence.

Actual M3 Max acceptance completed all three devices in order in 1,259.9 seconds:
47.7 seconds build, iPhone 400.4, Duo 400.0 and iPad 411.6, with all strict cases,
rotations and selected independent windows passing. These execution timings use
prepared tools and exclude source-plan inspection/copy time. Matching warm bundle
verification reused the identical binary in 1.49 seconds, without another native
suite or installation. A cancelled diagnostic run also proved that remaining
devices stayed unstarted and its owned simulator was removed. Local validation
found a new replacement-confirmation fixture mismatch and a real review-display
race; the corrected native flows passed on all three families. Raw proof remains
in ignored result directories. No hosted job or distribution is implied.

## Local Android native and runtime validation

For Test/Android select **This Mac — Android Emulator** on Apple Silicon. Settings
select an explicit complete SDK, Java17 JDK, ARM64 system-image package and device
profile. The backend requires hardware acceleration and creates a disposable,
uniquely named AVD under its owned workspace; existing AVDs and physical devices
are never selected as substitutes. Readiness records actual ABI/API/build and
image revision. Commands validate the emulator serial against its ownership name
before device actions. Cleanup removes that AVD's synthetic state, retaining logs
and the completed lease, and preserves the user's main app and device data.

The displayed plan separates native APK build, pinned runtime preparation,
emulator readiness, native functional/UI/rotation verification, CPython runtime
verification and always-run cleanup. Native APK reuse requires the exact source,
SDK/JDK/configuration and verified test payload/hash. Normal application APKs and
mismatched payloads cannot be reused. The native suite retains all33cases and
260rotation audits. Its fullscreen geometry includes both system-bar and camera
cutout safe insets, with the original strict centering and two-pixel bounds.

The separate runtime uses CPython revision
`823f0323ee6ec1402088b73bce1a38473cac36dc` (3.14.7), archive-verified upstream source,
a Mac host build and `aarch64-linux-android` cross-build. Upstream supports the
macOS build and connected-emulator test path; the manager does not copy hosted
Linux/x86 software-rendering arguments. Runtime reports require every declared
58test, zero failures/errors/skips, actual Android identity and the exact staged
manifest. Explicit local fingerprints are labelled local evidence; default hosted
verification still requires clean source and rejects local-mode reports.

Prepare public SDK/image/NDK/Gradle/Python dependencies before disconnected use.
First preparation downloads them; local execution is not a claim of an air-gapped
cold installation. Source/build caches remain ignored. No signing credentials,
TestFlight/Firebase upload or physical installation follows a successful test.

Actual M3 Max acceptance used Google API36 ARM64 image revision7 with Pixel9
hardware profile and Hypervisor.Framework. The complete plan passed in1,034.25s:
native build40.4s, reused runtime-tools verification1.0s, readiness23.2s,
native950.2s, runtime18.8s and cleanup0.6s. All33native/260rotation audits and all58
runtime tests passed. The earlier CI profile measured32.7min native runtime on
x86 software rendering; source, ABI, API and hardware differ, so these observations
are not an isolated optimization or portable speedup claim. Matching warm APK
verification reused its identical hash in0.135s without another complete suite.
A focused real native-launch cancellation stopped after the first checkpoint,
skipped remaining work and removed only the owned emulator. The reusable focused
driver is `mobile_build/validation/local_manager_probe.py`; its output is explicitly
cancellation evidence, never full-suite acceptance.

## Reuse boundary after extraction

The external `build_manager` package owns serializable `Phase`/`Plan`
contracts, execution and locks, provider transports, owned simulator/container
lifetimes, profiles, number reservations and optional Qt presentation. It imports
no Logistics application, test catalog, release naming or account configuration.
Provider conventions remain provider-owned; a project supplies its repository,
workflow names, credential references, device models and image selections.

The Qt adapter contract supplies `description`, `platforms`, `operations`,
`interpreter`, `runner_directory`, `results_directory`, `backend_options` and
`make_plan`. Optional `run_options` maps boolean option names to label/default
entries; values are passed back to `make_plan` rather than interpreted by the UI.
Logistics owns the `include_ipad` option. Settings, connection verification and
tracked version editing remain adapter methods. `secret_environment` identifies
additional inherited secrets for presentation redaction; each executable plan
also declares its redaction names. The UI can open the actual result directory,
including immutable captured reports and phase logs.

`Scripts/build_project.py` owns Logistics suites, local/hosted selection, app
identity, release channels and distribution handoffs. `Scripts/build_snapshots.py`
owns source selection and the transfer allowlist shared by Linux and Windows.
Snapshots preserve internal symbolic links without dereferencing private external
content, reject links escaping the checkout and fingerprint executable bits.
Deleted files and file-to-directory changes are overlaid before copying children;
a per-snapshot lock protects concurrent preparation. Cached source is verified
again before reuse. A Git checkout with local history and the pinned shared
repository is required; a Gitless downloaded source ZIP cannot silently stand in
for that history-dependent workflow.

`Scripts/mobile_processes.py` owns native command teardown for both mobile
adapters; neither Android nor its runtime helper imports the iOS policy module.
Owned POSIX groups receive final termination even when their immediate parent
has exited. Simulator cleanup verifies the same UUID/name again if shutdown races
with cancellation; persistent shutdown failures remain failures. Linux command
data travels over stdin rather than consuming the Parallels guest command line.
Private profiles validate value types and use unique atomic temporary files;
invalid number history produces an actionable error instead of implicit coercion.
Plan preparation timing is recorded consistently for all backends.

Prepared Android runtime tests install their two pinned, SHA-256 verified public
wheels with `--no-index`; wheel download belongs to preparation. This removes
package-index access from that test phase. SDK/Gradle/dependency preparation can
still need network: this is not a claim that every cold backend setup is air-gapped.
The legacy mobile payload code fingerprint has its established narrower scope;
the manager additionally records the whole selected source snapshot and complete
native artifact digest. Those identities must not be presented as interchangeable.

Release source ZIPs include the manager installer, project adapter and pinned tool
metadata, while excluding Git metadata, private profiles, credentials, caches and evidence.
The install manifest records the pinned commonUtils commit. Release completion
requires downloading the public ZIP, matching its published SHA-256, checking the
embedded app/source/dependency identities and verifying every declared member hash.
Checking only that GitHub advertised a digest is insufficient.

The manager and its harmless second-project tests now live in the external
repository. Project test discovery, native suites, source policy and
release/distribution rules remain here. `Scripts.mobile_processes` delegates
owned process-group retirement to the pinned manager's `stop_process`, including
after parent exit, timeout or interruption. It keeps the preparation command and
failure policy local; the manager bounds the final wait after termination.
The full Windows plan requires normal-user file/directory symbolic-link creation. Missing capability
remains a failed test setup, and focused Windows adapter checks cannot replace
complete required acceptance.


## Plan preparation and result integrity

Plan inspection prepares source and prerequisites in a worker while the Qt event
loop remains responsive; only plain project data crosses that boundary. Project
adapter planning methods must not access Qt widgets. A selection changed during
preparation invalidates the returned plan. Existing tool and snapshot waits remain
bounded. Unreadable/malformed results, missing captured evidence and disagreement
between a passing report and a failing process exit are shown as verification
failures. Required cleanup failures take precedence over a cancellation status.
Published ZIP verification also checks its embedded release tag, in addition to
source/dependency identity and hashes.

## Automatic storage retention

The Logistics adapter runs retention before preparing a manager plan. Direct
TestFlight archive/export/upload/distribution commands and Firebase builds also
apply the same provider-build policy, including when called without the UI or
inside a source snapshot. Read-only TestFlight `plan` does not prune outputs.

- Provider histories keep the three highest-numbered build directories
  and every directory used within the last 24 hours.
- Manager source snapshots keep the three most recently used snapshots and every
  snapshot used within seven days. Snapshot reuse refreshes its age. Execution
  holds a snapshot resource lock; pruning skips a leased snapshot.
- A `.keep` file anywhere inside a tree pins that enclosing build or snapshot.
  Pin a prepared artifact before keeping its path for long-term upload/retry use.
- Shared SDKs, signing keys, profiles, monotonic counters, existing simulators,
  deployment workspaces and unclassified evidence are outside this sweep.

Run `python -m Scripts.build_retention` from the repository root for a JSON preview;
add `--apply` to remove expired owned outputs. Pruning respects active build locks,
skips symbolic links and reports filesystem errors. Old saved plans can refer to
expired snapshots: prepare a fresh plan before running them. Retention preserves
recent failures for diagnosis; it does not guarantee a fixed disk-size ceiling.
The numeric families deliberately exclude unclassified historical backup names.

For a one-off probe, use `Scripts.build_retention.scratch(root)` as a context
manager, or run a command in a disposable working directory:

```sh
python -m Scripts.build_retention --scratch /absolute/path/to/python /absolute/path/to/probe.py --output '{workspace}'
```

Scratch work stays under ignored `test-results/build-scratch/` and is removed on
normal exit or failure. Save required evidence outside that directory first.
A root `.keep` file retains a scratch directory deliberately; otherwise abandoned
marked scratch directories become eligible after one day (the newest is retained).
A force-killed command cannot run its finalizer, so the next retention pass handles
its expired workspace. This is a shared lifecycle for agent-created probes as well
as human-driven builds, not a system-wide cache cleaner.

## Reviewing and deleting local builds

Choose **Clean up builds…** in the manager. Filter by iOS/TestFlight,
Android/Firebase, source snapshots or disposable scratch; select individual rows
or choose **Delete all unprotected…** for the displayed category. The confirmation
includes the exact paths. This manual action can remove even the newest local
artifacts; automatic retention still keeps its normal recent-build allowance.

The list covers only the existing retention owners. Native test build caches
inside owned source snapshots are removed with those snapshots. SDKs, toolchains,
physical-device deployment workspaces, personal VM/simulator state, credentials,
signing inputs, build counters and unclassified evidence are not cleanup targets.
Published releases are unaffected. A `.keep` anywhere in a tree or an active build
lease protects it. Deletion checks ownership, links, pins and locks again after
confirmation, reports skipped entries and refreshes the list. Listing and deleting
run off the UI thread; cleanup is unavailable while this manager runs an operation.

The generic UI consumes optional `storage_inventory()` and
`delete_storage(selections)` adapter methods. Logistics defines owned roots in
`Scripts.build_retention`; reusable manual deletion and lease protection remain
in `build_manager.retention`. The settings navigation factory is optional for
other projects; field metadata supports section, label, description, kind and
integer minimum/maximum/suffix without importing Logistics into the generic UI.

## External manager installation (adapter API 1)

Generic execution, transports, profiles and retention mechanisms now belong to
`build-deployment-manager`. Logistics retains `Scripts/build_project.py`, snapshots,
suite declarations, distribution helpers and storage policy. No sibling checkout
is discovered automatically. Install a reviewed Git checkout explicitly in each
interpreter used for Logistics tooling:

```sh
.venv/bin/python -m Scripts.install_build_manager /path/to/build-deployment-manager
mobile_build/.venv/bin/python -m Scripts.install_build_manager /path/to/build-deployment-manager
```

The manager requires adapter API 1. Missing/incompatible installations stop with a
setup error. Generic contracts run via `python -m build_manager.contracts` from
the installed manager checkout; project contracts remain here. Existing plans
and result schema 1 remain readable; results are never rewritten. Counters, keys,
profiles, snapshots and retention policy keep their existing locations.

Hosted runners and newly provisioned guests also need an explicit installation
of the reviewed manager revision. The extraction is local until that revision
is made available to those hosts; this task does not push or dispatch it.
Local source archives carry the installer and integration, not a stale second
copy of the engine. Re-run the explicit install after recreating an environment.

Hosted setup reads `build-manager-dependency.json` and explicitly installs that
immutable revision using `Scripts/install_build_manager.py --from-pin DESTINATION`.
It refuses an existing destination rather than pulling or resetting it. The owner
must make both manager and commonUtils commits remotely available before hosted
setup can succeed. No publication of those commits was performed here.

## Registered workflows and fixed settings

The standalone manager registers the tracked `build-project.json` and invokes
`Scripts/manager_bridge.py` in Logistics' own interpreter after explicit trust.
Named TestFlight/Firebase workflows prepare a signed artifact and pause for exact
artifact/destination review before reusing the existing distribution helpers.
`Scripts/distribute_prepared.py` never rebuilds for upload. It records intent before
the provider request and refuses to repeat an interrupted attempt without
reconciliation. Passing tests never approves distribution automatically.

Shared GitHub account references can select an environment-name or the existing
Git credential helper; TestFlight can select an existing protected auth JSON.
Destinations, app identities and signing remain explicit project values. An explicit
missing environment reference does not fall back to another account. Firebase
continues to use its existing CLI authentication. No local credentials are copied
to hosted secrets. Each run retains effective values/origins and a private fixed
profile; later account/profile edits cannot redirect that plan's destination.

Native resource declarations bound mobile builds, SDK/cache mutation, signing and
device sessions. iOS devices depend on the prior device's cleanup even if a plan's
worker count increases. POSIX mobile helpers receive a bounded five-second cleanup
grace. The generic Android transport is portable, while Logistics' CPython Android
runtime compiler remains explicitly macOS ARM until its own toolchain is ported.
Native Linux/Windows acceptance and all existing VM holds remain separate.

App Store/Google Play publication are visible as Not implemented. Existing TestFlight
and Firebase functionality retain their own provider identity and review gates.

## Guided manager suites and tester acceptance

The descriptor now declares `portable.contracts` (tooling contracts under
`Python/tests/tooling`), `desktop.ui` (application/UI checks under
`Python/tests/application`), `android.native`, `android.runtime`, `ios.native`,
`ios.runtime` and `release.acceptance`. These map existing owners into contracts, UI, native
and acceptance groups without moving their fixtures or imports. Full Test retains
its canonical suite inventory. A named host suite intersects its filename pattern;
native and release suites reject focused patterns. Named selection on hosted/VM
backends is explicitly unsupported rather than silently broadened.

The isolated regression runner accepts `--junit PATH` alongside its JSON timing
report. It retains measured cases, failure messages, skips, subtest/fixture errors
and failed/crashed module gates. Native reports expose their canonical case IDs;
when the native runner supplies no per-case duration, the manager displays an
unknown duration rather than dividing total time or reporting an invented value.
Whole-command parity checks remain explicitly single integration gates.
Regression fixtures discard inherited manager profile and account-default inputs.
Their temporary settings cannot read or overwrite the operator profile used to
launch the plan; each fixture supplies its own settings and destinations.

Reviewed Firebase/TestFlight workflows now run full tooling contracts, desktop UI,
mobile-host contracts, the complete native inventory and runtime acceptance before signing/preparation and the separately approved upload.
The gate checks source/dependency IDs, case inventories, actual runtime platform,
required iPhone/Duo/iPad release families, and owned simulator cleanup. Standalone
iPad coverage remains optional; reviewed TestFlight delivery always requires it. Missing,
failed or skipped native/runtime coverage blocks the prepared delivery. The
local iOS backend builds pinned CPython 3.14.7 and runs the complete core inventory
in a separate owned disposable simulator. `ios.native` selects the native UI
families; `ios.runtime` selects only the interpreter preparation, core tests and
cleanup, requiring an iPhone fixture rather than the Duo/iPad inventory. Full Test
and reviewed TestFlight delivery include both. Generated runtime receipts take
precedence over the legacy `LOGISTICS_IOS_RUNTIME_EVIDENCE` fallback; host reports
cannot satisfy the gate.

`Scripts/ios_testbed.py` adapts only the generated upstream test app: it adds a
real window-scene delegate and configuration, and raises the fixture's deployment
minimum to iOS 15 for current Xcode SDKs. The pinned CPython source, interpreter
and XCTest/core test inventory are preserved. The same adapter runs in the hosted
iOS runtime workflow. Local execution retains raw Xcode output and normalized
system-log output, verifying the exact staged-source digest, native platform,
complete case count, zero skips and successful owned cleanup. The report records
toolchain, dependency/framework checksums and the clone adapter identity.
Existing Prepare-only operations continue to produce development
preparation without implying native release acceptance.

These changes use `build_manager.reporting` from the companion manager UI change.
Local editable installations can validate the integration now. The committed dependency
pin selects the reviewed manager implementation containing that module. Its manager
and commonUtils commits must be made available remotely before hosted or fresh
pinned setup can consume it; local pinning does not push, dispatch or upload. Changing the descriptor requires
renewed manager trust. Portable regression checks do not establish native mobile
or live provider acceptance.

## Local guest setup with unpublished manager pins

Set **tools.manager_checkout** to an explicitly reviewed local manager checkout
when its pinned commit is not yet available remotely. Linux and Windows guest
backends verify the selected commit is present in that checkout and its real commonUtils
submodule against the
project's declared manager pin. They transfer committed Git sources only into the
owned guest workspace; ignored/private checkout files are excluded. No sibling
checkout discovery, push or hosted dispatch is needed. Leaving the setting empty
retains explicit remote pin installation.

The Linux transport stages its own supervision helper outside project source.
Guest dependency synchronization reinstalls the exact staged manager afterward,
so the project lock cannot silently remove the external engine. Windows manager
sources are scoped to the operation and removed with collected test work; reusable
prepared interpreter/tools remain in their separately owned preparation workspace.
Native Windows results record both OS architecture and Python platform: x64 Python
on a Windows ARM guest is emulated x64 coverage, not a physical Windows x64 receipt.

Each platform check now runs through the manager's own process-tree supervisor,
retaining a streamed per-check log and result under the run's results directory.
Timeouts retire the owned descendants, including Windows interpreter redirectors,
instead of killing only the immediate process and waiting on inherited pipes.
Windows shared/app budgets allow 30 minutes each for the declared cold x64-on-ARM
run; the required check inventory is unchanged. Guest phases give cooperative
remote cancellation time to collect evidence and retire owned work.

A checkout may have advanced beyond the declared pin: transfer selects the exact
recorded commit from that explicit repository without resetting its branch or
including later edits. Guest installation still requires the transferred HEAD
and commonUtils revision to match the pin exactly.

## Dedicated guest prerequisites

Windows shared/application filesystem suites create real symbolic links. In the
manager's Test machines dialog, select Windows and explicitly approve **Allow
Windows filesystem tests…** for the dedicated guest. Its initialization policy
is retained outside the VM bundle and reapplied when that bundle is recreated.
A normal-user symlink probe establishes this capability; the complete platform
suite must still pass. Existing personal or held guests must not be substituted.

The Fedora desktop suite also needs the OS libraries declared by the project's
`Python/tests/platform/fedora43.Containerfile`, including NSS, NSPR and GTK3 for
Qt WebEngine. Provision those project prerequisites through the authorized
dedicated-guest setup channel; do not grant the normal test account passwordless
sudo or disable browser sandboxing. The manager's generic readiness check alone
does not establish project dependency readiness. Fedora 44 ARM64 is labelled as
such, independently of historical Fedora 43 container or Ubuntu receipts.

Parallels may return error 255 before establishing a guest session. Retain the
failed attempt and confirm its owned workspace state before retrying. Tests are
never automatically replayed after an ambiguous transport failure. Explicitly
idempotent Linux manager staging, plan writes, evidence reads and owned cleanup
retry known session-admission/lost-job-handle failures at most three times.
Windows owned cleanup retries only its known lost-job-handle error. Ownership is
checked on every attempt; source creation, test execution and publication are
never covered by this retry policy.

Linux plan files also travel as ASCII stdin payloads, rather than embedding
source/settings JSON in Parallels command arguments. The owned write checks the
workspace token, rejects destination symlinks and assigns the normal test account.
This avoids misleading session errors when a legitimate plan exceeds Parallels'
command-line limit.

## Dedicated Windows/Fedora acceptance — 2026-10-25

The complete declared platform plans were exercised in the new manager-owned
Windows 11 ARM64 and Fedora 44 ARM64 guests. CPython is 3.12.2 on both; Windows
runs the x64 interpreter under emulation. Qt is 6.12. Historical full failures
remain retained, with unchanged suite/package/dependency inputs checked before
reuse. At Logistics `14e9c13c` / commonUtils `b105857d`, all 117 corrected or affected
application cases across 12 isolated modules passed on each guest. Native shared,
compression, release and extracted Windows batch-launcher/CRLF checks passed.

Manager `798587b` passed 154 native contracts per guest (three explicit POSIX-only
skips on Windows). Its transport probes preserved actual exit 0 and exit 7 without
replaying work after a lost handle, including while the guest worker was running;
a request made before admission prevented the child from starting. Final normal
backend flows passed their environment gate, four focused source-transfer tests,
report collection and cleanup: Windows `12cc9598` in 68.02 seconds and Fedora
`14e9c13c` in 39.41 seconds. The final cleanup audit also removed collected transfer
ZIPs and added them to the ordinary per-operation cleanup list. Reusable prepared
tools remain cached, with host sharing disabled.

Earlier application failures were corrected through portable host fixtures,
asynchronous reader teardown, a private Markdown provider fixture and original
ZIP-name validation before Windows normalization. The Qt ownership fix prevents
heap corruption when closing the manager. The declared suite inventory was not
reduced. Full attempt records remain failed where they originally failed; final
acceptance combines unchanged full coverage with successful affected checks.
Per-case timing, source manifests, durable receipts and cleanup proofs remain in
the manager's ignored `test-results/logistics-native/`. Subsequent product edits
need their own validation. Android x64 and final integration after Testing and
Packaging 06 remain deferred; no push, hosted dispatch or release occurred.
