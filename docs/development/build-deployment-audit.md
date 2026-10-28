# Build and deployment ownership

The standalone Build Deployment Manager is the operator entry point for checks,
builds and delivery. Logistics supplies its project adapter; it does not keep a
second manager, deployment window or launcher sequencer. This is the current
ownership map, updated October 28, 2026, replacing the earlier mixed inventory
and historical keep-launcher recommendations.

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

Build adapters previously under `Scripts/` now live in the importable root
`logistics_build/` package. Descriptors, workflows, commands, tests, evidence
input scopes and documentation use that single owner. The old Python build paths
are removed; no forwarding scripts remain for them. Historical source snapshots
resolve their commands to the original scripts stored in that selected revision,
without copying those obsolete paths into current source. The user explicitly released
Python files from the old path-preservation rule. The existing machine-used
`.bat` filenames and contents remain in `Scripts/`; contributor inspection and
setup tools also remain there.

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

The former `mobile_processes.py` implementation and its project-local process
fixtures are removed. Native builders/runtime adapters import the manager's
supervisor; its process cleanup tests live in the manager. Guest dependency
verification/archive code likewise has one manager implementation. Existing
project tests still verify selected pins, scratch cleanup, payload/source
acceptance and transport handoff.

## Current operator paths

Use the standalone manager for Run checks, Build only and Prepare and deliver.
Build only uses the existing Android test APK or iOS simulator-app build and
stops before tests or delivery. Release/tester preparation retains its full
project gates, signing and committed-source requirements. There is no generic
desktop Build operation in Logistics.

The six former `mobile_build/deploy_*.command` launchers, `deploy_ui.py` and
`deploy_all.py` are retired. Low-level device/provider helpers remain callable
because manager plans and native validation need them; their presence does not
make them a second recommended operator workflow. The small interactive
`deployment_confirmation.py` protocol does not certify manager acceptance.

See [operator workflows](../user/build-manager.md),
[project adapter contracts](build-manager.md), [tooling owners](build-tooling.md)
and the [ecosystem assessment](ecosystem-audit.md) for validation scope. Generic
engine/view/provider behavior is documented in the manager's own wiki; shared
library behavior is documented in commonUtils.

## Validation boundary

Portable subprocess/Qt fixtures verify orchestration and ownership. Logistics
checks additionally cover migrated import/command paths, descriptors, snapshots,
release inclusion, evidence scopes, curated mobile source lists and app guards.
Cross-consumer acceptance records each actual checkout/interpreter and the shared
working baseline separately; it never silently replaces a pin or subtree.
Native builds, physical installation, Blender/emulator interaction, VM acceptance
and provider publication require their owning platform checks. No commit or push
is part of this cleanup.
