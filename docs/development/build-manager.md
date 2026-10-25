# Build and deployment manager

Open `mobile_build/deploy_ui.py` with the desktop environment, or use the existing
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

Local macOS commands use the same project-owned desktop plan as CI. Parallels,
sequential iOS and local Android are explicit backend extension points until
their implementation and real platform acceptance are complete. An unavailable
backend fails planning; the manager never silently substitutes hosted validation.
Hosted desktop selection supplies the requested platform input. Normal release
calls continue to require the complete desktop matrix.

## Reusable boundary

`build_manager/` contains generic plan/result contracts, subprocess execution,
workspace locking, cancellation, output filtering, profiles, monotonic local
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

Future extraction would package `build_manager` as a versioned dependency.
Logistics would retain the adapters, functional suites and workflows and pin that
dependency. No additional repository or submodule is introduced here.

## Plan, result and source contracts

`Plan` schema 1 records project, operation, source identity, backend, workspace,
effect and ordered phases. A `Phase` carries structured argv, cwd, timeout,
environment overrides, prior dependencies, required/cleanup flags and expected
artifact reports. Plans are trusted executable local configuration, like scripts;
profiles and incoming documents are never interpreted as plans automatically.
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

Settings show each effective value's origin: repository defaults, ignored local
profile, environment or one-run override. Save changes the local profile;
changing the app version explicitly edits tracked `pyproject.toml` and requires a
commit. Build numbers are separate from app version and release tags.

| Section | Supported fields |
| --- | --- |
| TestFlight | Guarded app/bundle ID; selected external group; enabled state; What to Test; locale; polling interval and processing timeout |
| Firebase | App ID (verified against the guarded package); tester group; release notes |
| Tools | Desktop/mobile interpreter, Xcode developer directory, Android SDK and JDK directories |
| Local targets | iPhone/Duo/iPad simulator IDs, AVD name, Linux/Fedora/Windows guest selectors, host/guest shared-folder mapping and shutdown preference; backends must validate availability before execution |
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

Generic contracts are in `build_manager/tests`; Logistics integration contracts
are in `Python/tests/tooling` and `mobile_build/tests/tooling`. The tests exercise
real harmless subprocesses and Qt-to-CLI execution, failure, timeout, cancellation,
workspace conflicts, source privacy, allocation and controlled provider transport.
They do not substitute for the local platform backends' native acceptance.
`python dev.py lint` covers the generic package, and desktop plans run its tests.

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
