# Validating and delivering Logistics

Use the build manager to review validation, tester delivery and device installation.
For setup and saved settings, see the [build manager user guide](build-manager.md).
A plan captures source, settings and commands. A preset stores choices for making
a fresh plan; a retained run stores work already attempted and its evidence.

## Use the guided flow

Open the standalone manager and add or select a trusted Logistics checkout.
Adding it authorizes its adapter. If its interpreter is missing, repair the
Logistics environment using [contributor setup](../development/getting-started.md)
and the [manager integration guide](../development/build-manager.md).

Choose the intent before selecting destinations:

| Intent | What to select | Expected outcome |
| --- | --- | --- |
| Check a change | Run checks, platforms and execution hosts | Test evidence; no selected release destination |
| Compile an artifact | Build only and a supported mobile platform/host | Build output without tests, upload or installation |
| Release to testers or devices | Prepare and deliver, then explicit destinations/recipients | Required checks/builds followed by the plan's reviewed effects |

A GitHub execution host launches hosted work even when no release destination is
selected. Choose local hosts for a local-only check.

1. Choose **Run checks**, then select supported macOS, Linux, Windows, iOS
   and Android combinations and their execution hosts. Local hosts run local
   suites; a selected GitHub host declares a hosted dispatch in Review plan.
2. For delivery, choose **Prepare and deliver** and select destinations independently:
   GitHub source release, Firebase Android testers and/or TestFlight iOS testers.
   Firebase requires Android; TestFlight requires iOS. The GitHub source release
   requires all three desktop platforms before the existing full hosted gates.
3. Choose the source in **Source**. **Current files** follows
   snapshot policy: local validation, Debug builds, Firebase/TestFlight and Release
   device packages capture current Logistics and commonUtils files without
   committing or pushing either repository. Full mobile release checks bind
   tester and Release device packages to the exact source fingerprint.
   GitHub-hosted execution requires committed source; GitHub publication requires
   the current clean checkout at that exact commit and an explicit unused channel
   tag such as `v1.2.3-alpha.1`. Existing edits are never committed or discarded
   by planning. Use a committed revision for validation when that is your intent.
4. Check readiness and review plan. Inspect exact source, native hosts, required
   gates, recipient app/group identities, release tag and the dependency board.
5. Start only after reading the authorization scope. A fresh GUI Start authorizes
   selected Firebase/TestFlight uploads and GitHub actions after their gates pass;
   it is not a preparation-only button. Each destination waits for its declared platforms:
   Firebase waits for Android, TestFlight for iOS, and GitHub for the three desktop
   platforms. A failed unrelated platform does not block successful delivery branches.
   Native/runtime evidence and owned cleanup remain required; iOS delivery also
   requires the complete iPhone, Duo and iPad inventory. Linux delivery from the
   configured Mac VM backend requires both declared distributions.
6. Actions that still require separate approval, including device installs, pause
   for review of exact artifacts and destinations. CLI and older saved plans retain
   their declared approval requirements. Ready branches can overlap within declared
   resource limits. Resume reuses successful preparation only after checksum
   verification. Unknown external outcomes require reconciliation before retry.

The GitHub branch uses the existing publication policy: it publishes shared and
application source/channel/tag, waits for hosted release gates, and verifies the
source ZIP. This is a separate artifact from the locally prepared tester packages;
those packages are not silently attached to the GitHub release.

Physical-device installs are part of the Development delivery choices described
below. Planning reads saved recipient metadata and does not install anything;
execution has separate connection, preparation and per-device installation steps.

## Tester messages and development devices

Delivery configuration offers one per-run tester message for Firebase and
TestFlight. The adapter maps it to each service’s existing notes field. Leaving
it blank (including a remembered blank choice) preserves each service’s saved
default. Entering a nonempty message applies the same text to both selected tester
services. Recipient groups remain service-specific.
These overrides are captured for review and do not update saved settings.

Development-device delivery is under **Delivery → Development**.
Choose explicit Android devices or iPhone/iPad UDIDs from saved metadata, or enter
an already connected paired ID. Reload only reads `.tools/test-devices.json` and
`.device.json`; it performs no discovery, connection or device mutation. No target
is selected by default. The project captures IDs, labels and connection mappings
in a hash-bound preparation recipe. Per-device review names the actual recipient.

`logistics_build.manager_devices` builds from the same isolated captured source as the
validation branch, prepares an APK or zipped development-signed iOS app, then
requires manager approval of the exact retained report and package before each
installation. The iOS development profile must already cover all selected UDIDs;
preparation never registers devices or updates provisioning automatically.
Android preparation disables wireless discovery and device version queries.
Installation validates exact bytes and recipient identity, updates in place and
never uninstalls, clears storage, downgrades or re-signs on failure. Build/version
or signing conflicts stop the target with an error. Installing does not launch or
force-stop the app. Offline targets never cause another device to be substituted.

Before installation, a separate connection check retries the selected device
indefinitely at 30-second intervals. Android tries the captured transport, the selected hardware’s USB serial and
saved Wi-Fi fallback, then paired Wi-Fi services advertised for that same hardware
serial. It verifies the hardware ID before installation. iOS checks the selected
paired device. It never substitutes another
recipient or pairs a new device. The GUI shows Waiting to reconnect; Stop cancels
the wait. Offline recipients do not block other validation, builds, delivery
review or recipients. Continue the retained run to reuse tests and packages.
Identity/signature failures are explicit errors; an interrupted install is never
automatically resent without reconciliation. Connection checks do not install or
launch the app and do not replace the per-recipient artifact approval.

Each installation records an attempt before its first mutating command and a
receipt after confirmed success. Interrupted/uncertain outcomes require explicit
reconciliation before retry; other successful recipients remain recorded. Owned
build workspaces and the existing device deployment lock prevent competing writers.
Runtime credential/signing inputs remain protected references outside source.
Debug, tester-service and Release device runs may use captured current files
in both repositories. Full release test gates and exact snapshot fingerprints
still apply; GitHub-hosted execution retains its committed-source requirement. Device preparation and
local native validation currently require the configured Mac environment.

Portable tests use mocked ADB/Xcode commands and harmless process graphs.
Those fixtures verify planning and recovery contracts; they do not establish
native signing, provider delivery or physical-device acceptance. A real run needs
its own recorded outcomes and receipts.

## Mobile release preset without GitHub

**Full Testing, Release & Build (Mobile, excl. GitHub)** is a locally saved preset,
not a preset guaranteed to exist in every fresh registration. If available, inspect
its restored choices before preparing: iOS/Android checks, local execution hosts,
Current files and explicit tester/device destinations. It excludes GitHub source
publication and hosted gates. Device lists are saved choices, not live connectivity
checks; adjust recipients for your intended run.

Current files captures uncommitted Logistics and commonUtils bytes with an exact
source fingerprint. This does not create a Git commit or change Apple/Android
signing identity. Full required mobile release gates still apply. GitHub source
publication retains its clean committed-source requirement.

The preset was configured to run tests fresh. Reuse settings are still visible
choices: inspect them rather than assuming that all presets share this policy.
A preset contains no execution approval. Fresh GUI Start has the authorization
scope above; CLI `plan` lets you inspect before running.

## CLI: local Android validation and Boox deployment

Run the following commands from the **manager checkout**, using its `.venv`.
Paths such as `test-results/build-manager/boox-plan.json` below are relative to that
working directory; the registered project still points at Logistics. Replace
hardware IDs, plan/review identities and output paths with your own values.
These are real installation commands, not a harmless tutorial.

For repeat runs, save a project preset once in the manager and use:

```sh
.venv/bin/python -m build_manager.cli presets --project Logistics
.venv/bin/python -m build_manager.cli start --project Logistics --preset 'Boox Deployment (incl. Testing)'
```

The CLI and GUI share presets. `start` captures fresh source and writes results
under this project's result directory, then pauses before installation for the
ordinary `review`/`resume` steps below. To inspect before execution, use
`plan --project Logistics --preset 'Boox Deployment (incl. Testing)' --output PLAN.json`.
Presets store choices, never installation approvals.

Use the installed manager's `python -m build_manager.cli` interface. `list`
returns registration IDs; use the Logistics registration ID as `REGISTRATION_ID`
below. `inputs --project REGISTRATION_ID` returns saved hardware IDs.
Local execution uses this Mac's disposable Android emulator; it does not dispatch
hosted tests. Cold tool/dependency preparation can require downloads.

```sh
.venv/bin/python -m build_manager.cli journey --project REGISTRATION_ID \
  --goal deliver --platform android --destination android-devices \
  --execution 'android=This Mac — Android Emulator' --revision working-tree \
  --run-value 'devices.android=["HARDWARE_ID"]' \
  --run-value 'devices.android_connections={"HARDWARE_ID":"ADB_SERIAL"}' \
  --run-value devices.android_signing=beta \
  --run-value devices.android_variant=debug --output test-results/build-manager/boox-plan.json
.venv/bin/python -m build_manager.cli show-plan test-results/build-manager/boox-plan.json
.venv/bin/python -m build_manager.cli run test-results/build-manager/boox-plan.json \
  --output test-results/build-manager/boox-run --expect-identity PLAN_SHA256 --events
.venv/bin/python -m build_manager.cli review test-results/build-manager/boox-run
.venv/bin/python -m build_manager.cli resume test-results/build-manager/boox-run \
  --confirm --expect-identity PLAN_SHA256 --approval-identity STEP=REVIEW_SHA256
```

Use the plan identity returned by `journey`, then the exact pending step and review
identity returned by `review`. Each output run directory must be fresh. Read
`status RUN_DIRECTORY` for progress and `logs RUN_DIRECTORY --step STEP` for retained
diagnostics. Exit 3 means preparation succeeded and installation awaits review.
The existing deployment request can authorize continuation after inspecting the
exact package and recipient; running tests alone never authorizes installation.

The optional `devices.android_connections` JSON object selects a transport for
this run without changing saved metadata. For USB, the ADB serial is usually the
hardware ID. Only selected hardware IDs may appear in the mapping. A wireless
serial still requires matching `ro.serialno` before installation. USB/Wi-Fi fallback remains limited to the same verified hardware ID. No new
pairing, device substitution, downgrade, uninstall or data clearing occurs.
Validation includes required host contracts, native UI and Android runtime suites,
with owned emulator cleanup. Device installation updates the main app in place.
After Boox testing, verify its Logistics packages and remove temporary QA/probe
apps, preserving `io.github.ispaure.logisticsmobile` and its data.

Choose `devices.android_signing=beta` when updating an app signed with the existing
Logistics Beta key. Debug compilation remains separate from Release; the selected
key signs the package before review, without device discovery. The default
`debug` signing mode uses the ordinary Android Debug key. New prepared reports
retain the certificate; installation checks it against the installed app before
recording an attempt. A mismatch requires a new preparation, never an uninstall
or automatic signing fallback. Release packages retain their existing signature.

The complete local Android gate measured about 17 minutes on this Mac: roughly
7 minutes for host checks, 90 seconds for APK build/emulator startup, 8 minutes for
native UI/rotation and 25 seconds for runtime/cleanup. These are one measured run,
not a deadline guarantee. A preset shortens invocation but preserves all gates.

## Shared builds and device variants

The manager overview reads left to right under Source, Testing and Delivery.
Delivery includes build and export/signing cards as well as destinations. The
project descriptor declares package dependencies; the overview displays each
shared package once. Review and execution show the actual project phases.

Device delivery defaults to Debug. Choose Release in the device destination to
reuse the tester build: Android copies the exact signed Firebase Release APK;
iOS exports a separately provisioned device app from the same Release archive
used for TestFlight. An iOS Release device-only run omits the TestFlight export
and upload. Debug and Release remain separate builds, and simulator validation
remains distinct from physical-device packaging.

Release devices use captured source, full native/runtime release gates and
the existing tester build/signing configuration. iOS device exports use already
available signing assets and validate every selected UDID, including extension
profiles; they do not register devices or enable provisioning updates. All
installs still require review of exact bytes and recipients. Signing/version
conflicts stop the install without clearing data or changing identity.

Debug device packages, local validation, Firebase, TestFlight and Release device
packages can capture current files from both repositories. GitHub-hosted execution
and GitHub source publication require committed source. Latest commit excludes
local edits in both repositories without committing them; GitHub
publication additionally requires the current checkout to be clean and to match
the selected commit. Requirements appear in the overview before preparation.

Portable contracts cover sharing, stage dependencies, checksums and mocked
export/install commands. They do not establish successful native signing,
TestFlight processing, Firebase distribution or personal-device installation.
