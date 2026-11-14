# Build and deployment ownership

The standalone Build Deployment Manager is the operator entry point for checks,
builds and delivery. Logistics supplies its project adapter and owns application
build and release policy.

## Decide where new work belongs

| Concern | Owner | What a project supplies |
| --- | --- | --- |
| Scheduling, dependencies, concurrency, process trees and cancellation | Build manager | Structured commands, required gates, budgets and resource declarations |
| Registration, plan review, progress/results, presets and history | Build manager | Descriptor, optional fields, labels and project-specific settings schema |
| Artifact capture, hashes, continuation and unknown-effect handling | Build manager | Artifact paths, provider identity and explicit effect declarations |
| Guest/device transport, disposable machines and availability | Build manager | Selected targets, architecture, pins and acceptance/cleanup policy |
| CPython preparation, verified downloads and provider HTTP/CLI transport | Build manager | Runtime versions, payloads, signing/provisioning choices and destinations |
| Exact manager/dependency source packaging | `build_manager.dependency_sources` | Dependency revision and a caller-owned scratch workspace |
| Synchronous POSIX native-tool command supervision | `build_manager.native_commands` | Arguments, working directory, timeout and log destination |
| Cross-consumer test execution | Manager `consumer_acceptance`, using the ordinary executor | Explicit checkouts/interpreters, trusted test commands and storage location |
| Generic locks, pruning and active leases | Build manager | Which roots/outputs are disposable, retention periods and pinned exceptions |
| Portable file/resource/persistence/index/UI mechanisms | commonUtils | Domain policy and host adapters; shared APIs stay in that library's wiki |
| Source selection, suites, app compilation, package identity and release gates | Logistics `logistics_build/` and `mobile_build/` | These are the project implementation, not generic manager responsibilities |

A new project should declare its own source/build/test/release policy and call the
manager's mechanisms. Do not copy an executor, result viewer, transport, artifact
hasher, provider client or cache-pruning implementation into that project. A
candidate extraction needs an explicit reusable contract and consumer checks;
renaming a project-specific module does not make its policy generic.

## Logistics project tooling

| Project owner | Why it remains here |
| --- | --- |
| `build_project.py`, `manager_bridge.py`, `manager_journeys.py` | Declare Logistics operations, backend eligibility, captured inputs and release/tester gates |
| `manager_devices.py`, `manager_packages.py`, `distribute_prepared.py` | Guard the main package/signature/data, select saved recipients and consume exact prepared packages |
| `build_snapshots.py` | Public source layout, privacy exclusions and historical/working-tree selection |
| `build_retention.py` | The single Logistics retention/scratch policy; mechanisms come from the manager |
| `manager_suites.py`, `validation_plans.py`, `test_evidence.py`, `release_test_evidence.py` | App test inventory, source-bound reuse and hosted release evidence |
| `vm_backend.py`, `windows_backend.py`, `guest_results.py`, `guest_attempts.py` | Logistics guest suites, collected report validation and recovery applicability |
| `guest_manager.py` | Read the project dependency pin, select its scratch lifecycle and route project diagnostics; archive/verification mechanics delegate to the manager |
| `install_build_manager.py` | Bootstrap the external dependency before it can be imported; retain explicit project pin and environment selection |
| `android_backend.py`, `ios_backend.py`, runtime/payload/testbed adapters | Build this app's Briefcase project, stage its payload and verify its native/runtime case inventory |
| `mobile_build/deployment/` | App signing, provisioning, package/version/device compatibility, destination policy and attempt receipts |
| `mobile_build/build_support/`, `resources/`, `rclone_bridge/` | Application packaging/native implementation, not build-manager infrastructure |
| `mobile_build/validation/`, `tests/`, `native_tests/` | Project acceptance drivers and fixtures |

## Current operator paths

Use the standalone manager for Run checks, Build only and Prepare and deliver.
Build only produces an Android test APK or an iOS simulator app and stops
before tests or delivery. For iOS, `ios_simulator_workspace.py` owns the
standalone recipe when the captured runner supports it. Follow the
[workspace policy](build-manager.md#automatic-storage-retention) to find the
app and DerivedData under `tmp/build/mobile/ios/`. Older captured runners
build in their source snapshot. Release/tester preparation retains its full
project gates and signing requirements. Local tester and Release-device
preparation can use captured working-tree application and commonUtils sources;
GitHub publication requires committed source and a clean checkout. There is no generic
desktop Build operation in Logistics.

See [operator workflows](../user/build-manager.md),
[project adapter contracts](build-manager.md), [tooling owners](build-tooling.md)
for the application workflows and adapters. Generic
engine/view/provider behavior is documented in the manager's own wiki; shared
library behavior is documented in commonUtils.

## Validation boundary

Portable subprocess/Qt fixtures verify orchestration and ownership. Logistics
checks additionally cover migrated import/command paths, descriptors, snapshots,
release inclusion, evidence scopes, curated mobile source lists and app guards.
Cross-consumer acceptance records each actual checkout/interpreter and the shared
working baseline separately; it never silently replaces a pin or subtree.
Native builds, physical installation, Blender/emulator interaction, VM acceptance
and provider publication require their owning platform checks.

## Storage lifecycle

`build_retention.py` defines the project-owned directory families, cache budgets
and exact metadata checks. `storage_extras.py` owns explicit adoption records and
recovery of simulator leases. The manager supplies byte measurement, pruning,
locks, hold retirement and the shared cleanup UI. Cache groups use the enclosing
snapshot/device operation lock and preserve signed outputs and evidence.

Only declared compiler intermediates, Gradle local metadata and TestFlight derived
build data are independently disposable inside snapshots. Packages, archives,
source, reports and receipts remain under ordinary retention and workflow holds.
Known device build trees are disposable only after a prepared package exists at
the recipe's expected workspace path. Explicit `.keep` pins also protect caches.
The shared compiler-cache budget is 12 GiB, with a one-day age limit and one-hour
grace. Global metadata-owned Xcode caches retain their separate policy.

Temporary adoption stores an exact path/token marker and project registry record;
cleanup checks both and refuses active native writers. Simulator recovery requires
an existing project session lease or explicit UUID adoption and verifies the saved
UUID/name through the manager backend. Display names alone never authorize removal.
Personal simulators, SDKs, unclassified evidence and arbitrary temporary paths are
not swept. Keep portable fixture checks separate from native cleanup acceptance.
