# Build and deployment ownership audit

Audit date: October 26, 2026. This is a source audit and migration recommendation,
not authorization to delete scripts or evidence. No builds, device operations,
uploads or cleanup were run.

## Main finding

The reusable manager extraction happened. Logistics has no tracked
`build_manager/` package; it imports the external package. Most remaining build
files are active project adapters, application packaging or acceptance tests.
Deleting them because their names contain build, deploy or manager would break
the extracted manager's Logistics integration.

There are useful further extractions, but no confirmed unused manager copy to
delete immediately. The strongest small consolidation is Firebase build-number
reservation. Larger candidates are guest environment preparation, provider
transport and CPython mobile runtime preparation. Keep project policy around
those mechanisms in Logistics.

`Scripts/AGENTS.md` protects **all existing script names and paths**, beyond the
Windows `.bat` files explicitly retained by the user. Move implementation behind
these entry points when appropriate; removing a path requires specific user
authorization. A missing repository caller would not establish absence of
external use.

## Scope and evidence

- Inventoried tracked root files, all 44 `Scripts/` files, mobile build subtrees,
  release scripts and workflow entry points. Application feature internals were
  not individually reviewed for dead code.
- Compared against the sibling `build-deployment-manager` checkout. At the initial
  inventory its HEAD matched Logistics' dependency pin,
  `ff40f092d9eb1d4a48c9b597af4625bd85d0a746`. That checkout also had uncommitted UI
  changes; none were changed by the audit. Subsequent authorized implementation
  and dependency updates are recorded below.
- Checked imports, module command strings, launchers, descriptor registration,
  test consumers and packaging requirements. All 33 Python scripts under
  `Scripts/` have tracked references. For example, `document_architecture.py`
  is also called through a relative import in `architecture.py`.
- Compared tracked Logistics Python file contents against tracked manager-package
  Python files larger than 100 bytes: no identical files. An additional AST
  comparison found no identical top-level function definitions of at least nine
  source lines between `Scripts/` or `mobile_build/deployment/` and manager modules.
  These checks do not rule out duplicated algorithms, renamed code or dead branches.
- This is static evidence of ownership and connections, not native acceptance or
  proof that every option is exercised. Ignored generated trees were excluded
  from the source inventory; private configuration contents were not audited.

The [manager integration guide](build-manager.md), [tooling owner map](build-tooling.md)
and [ecosystem audit](ecosystem-audit.md) describe the existing boundary.

## Scripts: keep, with selected mechanisms worth extracting

Every existing `Scripts/` file is covered below. “Extract” means retain the path
and project adapter while migrating a reusable mechanism after consumer tests.

| Files under `Scripts/` | Recommendation | Reason / boundary |
| --- | --- | --- |
| `StartDownloadVM.bat`, `StartTheDonVM.bat`, `SyncGOAT-PC_TotalSync_ToFromCloud.bat`, `kbp_goat-pc-2.bat`, `kbp_goat-pc-3.bat` | Keep unchanged | Required machine-specific commands; repository call counts cannot assess external use. |
| `AGENTS.md` | Keep | Defines the preserved entry-point contract. |
| `build_project.py`, `manager_bridge.py` | Keep | Project adapter and registered subprocess bridge. The adapter constructs Logistics plans, settings and release operations using external manager contracts. |
| `manager_journeys.py`, `manager_devices.py`, `manager_packages.py`, `distribute_prepared.py` | Keep | Capture Logistics workflow intent, select saved recipients, share its Release archive and consume exact reviewed artifacts. Generic scheduling/review already lives in the manager. |
| `manager_suites.py`, `validation_plans.py`, `local_desktop.py`, `platform_checks.py` | Keep | Own app suites, acceptance inventories and Qt/rclone prerequisites. `platform_checks.py` already delegates subprocess supervision to the manager. |
| `build_snapshots.py` | Keep | App/shared revision capture, private-input exclusions and source layout. Do not confuse source snapshots with manager execution workspaces. Generic Git/archive plumbing could be shared later if another consumer needs it. |
| `build_retention.py` | Keep | Declares Logistics roots, eligible outputs, retention periods and scratch policy; imports manager leases, pruning and safe deletion. Moving the entire module would move project storage policy into the engine. |
| `install_build_manager.py`, `guest_manager.py` | Keep entry points; consider extracting exact-pin transfer/install mechanics | Logistics owns its dependency descriptor and installation choice. Generic committed dependency packaging/staging could move behind an explicit descriptor-based API. Manager source must remain external. |
| `vm_backend.py`, `windows_backend.py` | Keep adapters; extract generic environment preparation | Project suite commands, Fedora selection and pinned runtime requirements belong here. Download verification, portable-tool extraction and environment bootstrap are mechanisms. Transport, process ownership and dedicated VM creation are already external. |
| `guest_results.py` | Keep now; possible small manager lifecycle API | Combines reusable collect-before-cleanup behavior with exact Logistics source/backend/report checks. Split callbacks from report validation only if a second adapter uses it. |
| `android_backend.py`, `ios_backend.py`, `mobile_payload.py` | Keep | App-specific Briefcase builds, curated payload staging, binary/source checks and native suite invocation. Emulator/simulator ownership already comes from the manager. |
| `mobile_runtime.py`, `ios_runtime.py`, `ios_testbed.py` | Keep callers; extract reusable runtime preparation in stages | Upstream CPython download/build/cache and testbed adaptation can be reused. Logistics payload, `mobile.smoke`, manifest verification and required cases remain project-owned. |
| `mobile_processes.py` | Keep small wrapper, or delegate through a public manager command helper | Only 19 lines; already uses manager `stop_process`. It is not a second executor. Migration value is consistency, not file-count reduction. |
| `build_manager_tools.json`, `mobile_runtime_tools.json` | Keep selected versions/requirements; possibly share a catalog | Separate version policy from download/cache mechanics. Do not substitute the manager's bootstrap interpreter for Logistics' test interpreter. |
| `architecture.py`, `architecture.json`, `document_architecture.py`, `ownership.py`, `ownership.json` | Keep | Logistics architecture and test-owner contracts used by contributor tooling/tests. These are not deployment leftovers. |
| `compatibility.py`, `compatibility.json`, `development.py`, `hygiene.py`, `toolchain.py` | Keep | Contributor checks, setup, import compatibility and dependency consistency. Any generic utility extraction still needs project manifests/policy. |
| `release_naming.py`, `release_verification.py` | Keep | Logistics release channels, naming and public ZIP verification. |

## Mobile build tree and repository entry points

`mobile_build/` contains 557 tracked files. Of these, 215 are under `tests/`, 156
under `native_tests/`, 67 under `resources/` and 55 under `rclone_bridge/`.
Those 493 files are application tests, assets and native runtime implementation;
the directory name considerably overstates the amount of reusable build tooling.

| Files / owner | Recommendation | Reason |
| --- | --- | --- |
| `mobile_build/tools.py` | Keep | Curates the app payload and verifies its source manifest/runtime reports. |
| `mobile_build/cloud_build.py`, `build_support/`, `select_ios_sdk.py` | Keep app composition; selectively generalize only proven reusable helpers | Configures Logistics bridge compilation, Android sources/appearance, iOS scenes, incoming files, artwork and privacy. The filename `cloud_build.py` does not make this generic orchestration. |
| `mobile_build/rclone_bridge/`, `resources/`, `privacy/`, `native_tests/`, `tests/` | Keep | App implementation, package resources and regression/native acceptance. Generic manager tests already live in the manager. |
| `deployment/manager_settings.py`, `settings_help.py`, `deployment_paths.py` | Keep | Logistics settings schema/defaults, help, canonical configuration and generated-workspace layout; generic persistence is delegated externally. |
| `deployment/android_deploy.py`, `device_tools.py`, `test_devices.py`, `wireless_adb.py` | Keep now; extract generic device/ADB operations where useful | Active physical installation/discovery paths. Package identity, signing choices, saved recipients and preservation of main app data remain app policy. |
| `deployment/firebase_deploy.py`, `testflight_deploy.py`, `testflight_tools.py`, `testflight_external.py`, `testflight_signing.py` | Keep policy; extract transport and reusable packaging primitives | These implement actual builds, signing/export, provider checks and delivery. External `providers.py` declares capabilities/contracts; it does not replace these implementations. |
| `deployment/deploy_ui.py`, `deploy_all.py`, `deployment_confirmation.py` | Active overlap: consolidate after feature parity | The deployment window embeds the manager panel and also maintains its own device selection, QProcess output and upload prompts. `deploy_all.py` separately sequences launchers. Both have live `.command` callers. |
| All six `mobile_build/deploy_*.command` launchers | Keep stable entry points | Direct operator commands. Redirect to a consolidated implementation only after preserving their arguments, interpreter selection and confirmation behavior. |
| `mobile_build/validation/` | Keep reusable drivers; review experiments individually | Device/report acceptance is app-specific. `local_manager_probe.py` has no other tracked caller but is a runnable cancellation/lifecycle acceptance driver, not an unused engine copy. Lack of references is insufficient to delete it. |
| `mobile_build/qt_proof/` | Historical experiment; optional retirement review | Five tracked proof files, still documented through the Qt proof guides. Decide whether reproducing the PySide iOS proof remains useful before deleting code and updating its guides. It is not a manager migration target. |
| Mobile manifests, locked host requirements, distribution JSON and README | Keep | Define application packaging, tooling dependencies and destination policy. Credentials remain in ignored protected files. |
| Root `build-project.json`, `build-tests.json`, `build-manager-dependency.json` | Keep | Adapter registration, declared case/suite inventory and external dependency pin. |
| Root `dev.py`, application launchers and `launch_config.ini` | Keep | Contributor and application entry points, independent of the manager GUI. |
| Root `PackageSnapshot.command` | Keep; possible shared snapshot mechanism later | Interactive current-source sharing ZIP, distinct from committed release ZIPs and manager execution snapshots. Different inclusion/privacy contracts prevent blind deduplication. |
| `.github/workflows/`, `.github/scripts/` | Keep project workflows/policy | They invoke app validation, packaging and delivery. `package_release.py` explicitly requires several retained Scripts paths in published source packages. Update those contracts with any future extraction. |
| `Python/`, `docs/` and repository metadata | Keep ownership structure | App/runtime code and docs stay here. `Python/commonUtils` is a real external submodule, not a copied manager; ignored optional feature links are separate repositories. This audit does not establish individual feature files as unused. |

## Prioritized consolidation work

The Firebase allocation step below is now implemented: preview and reservation
delegate to the pinned manager. A manager-format reservation record sits beside
the preserved legacy counter, which is atomically updated under the existing
Firebase lock. See [Firebase counter compatibility](mobile-launchers.md#double-click-android-firebase-distribution)
for storage and recovery behavior. Focused portable checks cover history,
overrides, limits, lock exclusion and interrupted compatibility writes; no native
build, device operation or provider upload was required for this change.

Guest-tool preparation has also moved to `build_manager.guest_tools`: standalone
Linux bootstrap and Windows portable uv/Git/interpreter installation programs
accept project-supplied settings. Existing Logistics backend paths, receipts and
catalog remain here. Portable checks cover caller pins, bootstrap failure,
parameter validation and preparation receipts; this extraction does not claim a
new native Windows/Fedora run. Further sharing with first-boot installation is
optional; initial-machine and project-test environments remain separate stages.

Legacy deployment UI and sequencing now delegate to the manager's
`deployment_commands` and `deployment_commands_ui` modules. Logistics retains a
small policy adapter/window shell, the original upload marker and all launcher
paths. Reusable controls cover streaming, explicit confirmation, selection
retention and busy state; the sequencer preserves inherited terminal input and
failure-after-continuation. Device discovery/build/signing and per-platform
deployment policy stay here. Portable subprocess and native macOS Qt checks use
harmless fixtures; they do not claim a new device installation or provider upload.

1. **Use the existing allocator for Firebase.** `firebase_deploy.reserve_build`,
   `next_build` and `_reserve_build` repeat monotonic reservation logic already
   available in `build_manager.versions`. TestFlight already consumes that API.
   Preserve Android's UTC date floor, maximum version code, debug deployment
   history and protected `last_build` counter. The manager currently stores
   `schema`/`last`, so this needs an explicit compatible counter migration or
   reusable record adapter, not a one-line replacement. Check concurrent
   reservations and interrupted/missing-counter recovery before switching.
2. **Share guest tool preparation.** `windows_backend.PREPARE` downloads/verifies
   MinGit/uv and constructs an isolated interpreter; `vm_backend.BOOTSTRAP`
   creates bootstrap/test environments. The manager's `vm_bootstrap` also
   downloads/verifies MinGit, including the same pinned ARM64 archive. These are
   distinct active provisioning stages, not interchangeable implementations:
   initial machine setup uses a different Python from Logistics' test runtime.
   Introduce reusable tool provisioning with project-supplied pins/requirements;
   retain guest ownership, normal-user execution, exact-pin manager installation,
   evidence collection and cleanup contracts. Require native Windows/Fedora
   checks as well as portable transport tests.
3. **Consolidate the deployment UI and sequencing.** Migrate its device and
   distribution actions into manager workflows after checking refresh/repair,
   debug and Release installs, unavailable saved devices, output streaming and
   explicit upload prompts. Keep the launcher routes. A successful native test
   run must still be distinct from direct development preparation or delivery.
4. **Extract provider clients around declared effects.** App Store Connect JWT,
   HTTP requests/polling and Firebase CLI transport are reusable. Keep bundle IDs,
   groups, signing expectations and release eligibility here. The manager's
   `PreparedEffect`/`ProviderContract` are a starting boundary, not evidence that
   working Firebase/TestFlight clients have already moved. Verify no accidental
   upload replay after ambiguous transport outcomes.
5. **Extract CPython runtime preparation if another project needs it.** Move
   archive verification, compiler setup and prepared-cache identity behind a
   parameterized API. Keep source/test payload assembly and acceptance here.
   Preserve native platform, complete cases, exact manifest and owned cleanup
   checks. Portable tests alone do not certify this migration.

Avoid moving tiny wrappers solely to reduce Logistics' file count. Prefer an
explicit reusable contract and a second consumer/fixture before enlarging the
manager API. Release/source snapshot policies remain distinct even if they
eventually share low-level archive traversal.

## What can be removed now?

No tracked build/deployment source file was proven safe to delete in this audit.
The optional Qt proof and standalone probes warrant purpose-specific review;
active launchers and adapters do not belong in a bulk deletion pass.

Ignored `mobile_build/build/`, `payload/`, `.tools/`, `.deploy-workspaces/`,
virtual environments and test reports can visually resemble old source copies.
The initial filesystem inventory encountered historical `release-source-*` and
payload copies inside ignored builds; those are generated outputs, not tracked
duplicates. Their presence says nothing about whether current source is dead.

Use the existing retention preview for eligible owned output. Legacy disposable
build folders need explicit review/enrollment and saved evidence before pruning.
Never blanket-delete `.tools`, signing assets, build counters, prepared toolchains
or unclassified evidence. No storage deletion or enrollment was performed here.

## Migration completion criteria

Keep old entry points callable, update package requirements and CI together,
publish/pin the manager API before relying on it in fresh environments, and test
the adapter against that exact pin. Validate affected source/artifact identity,
cancellation, concurrency, secret-reference handling and cleanup. Preserve
existing standalone CLI confirmation behavior and installed main app/data.
Only classify the former implementation as removable after every caller uses
the new mechanism and the relevant native/provider contracts have been checked.
