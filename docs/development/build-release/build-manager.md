# Logistics build manager integration

Use the [operator guide](../../user/build-manager.md) for installation and plan review. Logistics pins the external SDK in `build-manager-dependency.json`. [Install the pin in each tooling environment](../../user/build-manager.md#external-manager-installation-adapter-api-1). Its `logistics_build/build_project.py` adapter owns app source, suites, backends, signing and release policy. The SDK owns execution, locks, transports, artifact verification and review UI. See [ownership](build-deployment-audit.md).

## Dedicated test-machine settings

The manager uses a private profile per checkout. First Save copies legacy local values into it. CLI tools honor `LOGISTICS_MANAGER_PROFILE`. Explicit machine selectors win. For empty Fedora/Windows selectors the bridge verifies the manager's ownership receipt and Parallels registration without starting the VM. Save records the detected UUID. Resolve missing/conflicting ownership in Setup → Test machines.

## Implemented operations and extension points

| Operation | Contract |
| --- | --- |
| Local checks | Selected backend required. Native app plans inspect pinned Briefcase, pip, Go and the verified langdetect wheel before build/test work. Interpreter-only plans require pip. Inspection reports repairs. |
| Build only | Android development APK or iOS simulator app without test or install phases. |
| Prepare and deliver | Source-bound validation, signed artifact and reviewed destination. Mobile branches may progress independently, with per-destination gates and all selected desktop checks retained. |
| GitHub validation | Verify published source, record accepted dispatch, then observe that exact run. Resume observation after transport failure. Reconcile ambiguous dispatch before another write. |
| GitHub release | Publish shared source before project source and a new immutable tag, or tag an exact already-published commit. Observe the gated workflow. |

The [journey adapter](build-manager-journeys.md) builds dependency graphs. The descriptor declares optional adapter actions. Generic SDK APIs belong in the manager wiki. Projects declare structured plans, backends and optional settings or verification actions through `build_manager.adapter_sdk`.

## Plan, result and source contracts

Schema 1 binds source, backend, workspace and effects to ordered phases with structured argv, cwd, timeouts, environment overrides, dependencies and cleanup flags. Treat plans as trusted executable configuration. Inherit provider secrets through protected references/environment. Run a reviewed plan with `python -m build_manager PLAN.json --output NEW_DIRECTORY`; effects also require `--confirm`.

The executor publishes atomic `result.json`, redacted logs and artifact hashes. Failed dependencies skip consumers. Required skips and timeouts fail the result. Independent diagnostics and owned cleanup can still run. Older saved plans retain their original commands and approval requirements.

`build_snapshots.py` captures either a committed revision with its commonUtils gitlink, or current files in both trees including nonignored additions, deletions and executable modes. Capture records both identities and rechecks content before reuse. Private settings, SDKs, external links and root `tmp/` outputs stay outside the capture. A root `tmp/` entry in the index or retained Git history blocks guest transfer. Local Debug and signed mobile preparation can capture edits. Signed preparation binds native/runtime proof to the exact capture. GitHub publication requires committed clean source. Staging embeds and verifies the capture fingerprint.

## Validation and local outputs

Integration contracts live in `Python/tests/tooling/` and `mobile_build/tests/tooling/`. Full scopes retain both owners' complete inventories as applicable. Qualify SDK changes separately with `python -m build_manager.contracts` in the SDK environment. See [platform checks](../testing/platform-checks.md) for native acceptance. Store plans and receipts under ignored `test-results/build-manager/`. Snapshots and counters use `mobile_build/.tools/build-manager/`. Keep signing material and personal settings private.

## Local macOS acceptance

Select macOS → This Mac. Use the locked desktop environment (`python dev.py setup desktop`). Preflight records Python, OS and architecture, loads Qt and verifies pinned rclone and genuine LocalCrypt fixtures. The plan runs shared/app checks, compression parity and release tooling. GitHub's macOS-only selector supports diagnosis. Release requires the complete desktop matrix.

## Parallels Linux backend

Select authorized Fedora by name or UUID in `vm.fedora`. Fedora is the Linux release gate. The guest needs Parallels Tools, Git, venv support and native Qt/WebEngine libraries from `Python/tests/platform/fedora.Containerfile`, including NSS, NSPR, GTK3 and Fedora 44's `minizip-ng-compat`. Provide these through dedicated guest setup and preserve the normal-user browser sandbox. Cold preparation can download public tools.

The manager transfers a hashed allowlist and runs under the selected normal account. Collect reports before token-checked cleanup. Resolve encrypted-disk boot prompts in the guest. `vm.shutdown_after_run` defaults off. When enabled, the adapter stops only a VM this run started from stopped and records the command outcome and observed state. Preserve a failed or ambiguous attempt and [reconcile owned guest work](build-manager-journeys.md#retried-guest-validation). Idempotent staging/reads and owned cleanup may retry known transport errors. Test execution needs a new reviewed attempt.

### Explicit Fedora container mode

Set `vm.fedora_mode=container-on-ubuntu` and `vm.fedora_container_host` to an authorized Ubuntu guest with normal-user rootless Podman. The adapter hashes the Containerfile, selects the configured Fedora image, runs by immutable image ID and removes the labelled run container. Fedora version and CPU architecture are evidence inputs.

## Parallels Windows backend

Select the dedicated Windows guest. **Test machines → Allow Windows filesystem tests…** enables the required normal-user symlink capability. WinError 1314 blocks full acceptance. Validate with the entire suite after the symlink probe. Current Windows ARM coverage uses x64 Python under emulation. The portable Git/uv catalog is `logistics_build/build_manager_tools.json`. An explicit `vm.windows_prepared_reference` can reuse verified tools. The backend collects logs before removing owned workspaces and records actual process exits. Use the [setup reconciliation command](build-manager-journeys.md#retried-guest-validation) for incomplete attempts.

## Local guest setup with unpublished manager pins

Set `tools.manager_checkout` to an explicitly reviewed local checkout containing the exact manager pin and its pinned commonUtils. Transfer selects committed objects without resetting the branch. Clear an obsolete selector to use published-pin installation. A verified owned tooling cache can restore missing objects locally from the installed exact SDK. Unrecognized or dirty caches require tooling repair. After dependency sync the guest reinstalls the transferred SDK. Hosted desktop setup likewise verifies and reinstalls the exact `LOGISTICS_MANAGER_CHECKOUT` after sync.

### Testing uncommitted manager changes locally

For local validation choose **Current local manager edits (tests only)** or pass `--run-value testing.manager_source=working-tree-local`. The base manager and shared pin must still match. Transfer verifies the exact public-tree fingerprint at capture, transfer and guest install. Use the results as local development evidence.

## Sequential local iOS validation

Choose **This Mac — iOS Simulators**. Install the configured SDK and iPhone/Duo runtimes; full delivery and multi-platform validation also require iPad independent-window proof. A standalone run may select iPad. The backend builds one test app per verified source/toolchain and runs separate disposable iPhone, Duo and optional iPad simulators in order. Each keeps its full inventory, rotations and family-specific checks. Cleanup deletes only the run's leased UUIDs. Retained bundle reuse verifies the staged manifest, test entry and full content/permissions digest.

## Local Android native and runtime validation

On Apple Silicon choose **This Mac — Android Emulator**. Configure the complete SDK, Java 17, explicit ARM64 image and model. The backend requires acceleration, verifies AVD ownership against its serial, records actual ABI/API and retires the disposable AVD. The APK verifier checks exact source, toolchain, test payload and hash. Runtime uses a separate pinned CPython 3.14.7 cross-build and staged manifest. Every declared runtime case must pass with zero skips. Prepare public SDK/NDK/image/compiler dependencies before disconnected work.

`test-environments.json` is the tracked source of runner labels, Python, iOS runtime families and Android API/model/ABI. Edit it in **Test environments (local and GitHub)**. Private machine paths and signing stay in the profile. Local ARM64 and hosted x86_64 Android results carry their actual identities. A changed toolchain invalidates affected evidence.

## Guided manager suites and tester acceptance

`build-tests.json` owns suite roots and predecessors. The descriptor declares selectables such as `portable.contracts`, `desktop.ui`, platform `.native`, `.runtime`, `.incoming` and `release.acceptance`. See [suite file responsibilities](../testing/adding-tests.md#decide-which-files-to-update). Host patterns intersect named host suites. Native/release suites reject focused patterns. Named selection is local. `python3 dev.py test-map` distinguishes discovered files, declared sources/drivers and registered case IDs.

Reviewed tester delivery requires tooling, desktop UI, mobile host, full native and actual runtime acceptance before signed preparation. Verify source and dependency IDs, platform, case inventory, device families and teardown. `ios.runtime` uses a separate disposable iPhone testbed without Duo/iPad UI checks. Runtime adapters delegate compiler/setup to the pinned SDK and retain Logistics pins and gate verification in `mobile_runtime_tools.json`. Incoming-file suites use the actual system menus and disposable sender/receiver apps. See [incoming files](mobile-preparation.md#incoming-files-and-inbox).

`python -m logistics_build.test_structure --check` validates the captured structure before tests. Declared smoke phases run fresh before broad regression. A verified exact-input host receipt can satisfy the later phase. See [execution stages](../testing/testing.md#execution-stages-and-failure-policy). A focused native diagnostic can use `mobile_build.validation.document_storage_tools` with `--probe native-suite`.

## Independent mobile validation and shared resources

Android and iOS branches share host mobile-build capacity (one by default) and serialize runtime work under `mobile-runtime.lock`. Native/device, workspace, keychain and provider resources remain scoped. Cleanup can run as soon as its branch is eligible. Prepare a fresh plan to pick up graph changes.

Debug development-device plans may select zero test platforms. Release-device preparation requires its target's acceptance. Explicit recipients still require package, signature, hardware and hash checks. Android `devices.android_connections` maps selected saved hardware IDs to explicit ADB serials for one run, preserving stored endpoints and hardware verification. Resolve uncertain installs through reviewed recovery.

## Automatic storage retention

`logistics_build/build_retention.py` defines project ownership. Plan preparation, TestFlight mutations and Firebase builds apply retention. A read-only TestFlight plan only inspects.

| Owned group | Automatic retention |
| --- | --- |
| Numbered provider builds | Three newest plus one day |
| Source snapshots | Three newest plus five days, 24 GiB soft budget |
| Device recipes | Three newest plus one day, 12 GiB per platform across both workspace roots |
| Compiler caches | 12 GiB shared budget, one day, one-hour grace |
| Metadata-identified Xcode DerivedData | Three newest plus one day, 12 GiB, one-hour access protection |
| Enrolled legacy build outputs | Three newest plus five days |

Budget pressure can retire oldest eligible entries after the grace period. Active leases and `.keep` pins win. Durable workflow holds protect their source/artifacts; independent compiler caches require a pin or active lock. Xcode ownership uses `info.plist` WorkspacePath and active process checks. Shared SDKs, signing keys, counters, main app/data, personal simulators and unclassified evidence stay protected.

New independent Android Debug and supported iOS Build recipes use `tmp/build/mobile/<platform>/`. Older and mixed-signing recipes can use `mobile_build/.tools/build-manager/workspaces/devices/`; old iOS runners can build in snapshots. Known compiler caches also use `tmp/cache/compiler/` and marked legacy roots. Keep artifact references with their actual workspace. Replan expired inputs.

From the repository root:

```sh
python -m logistics_build.build_retention
python -m logistics_build.build_retention --apply
```

Save recovery material first. Explicitly enroll reviewed disposable directories directly under `mobile_build/build/` with `--enroll-output old-disposable-probe`. Enrollment marks the path and starts a five-day window. Producers hold `build_manager.retention.lease(path)`. Temporary probes use `scratch(root)` or:

```sh
python -m logistics_build.build_retention --scratch /absolute/path/to/python /absolute/path/to/probe.py --output '{workspace}'
```

Copy needed evidence to ignored `test-results/` before exit. New marked scratch runs live in `tmp/runs/scratch/`; marked legacy runs keep their original paths. Use explicit path/token or UUID adoption for legacy probes and simulators.

### Project-owned native prerequisite setup

After `python3 dev.py setup desktop` and `python3 dev.py setup mobile`, choose **Project tooling → Update project tooling…** or run `python -m build_manager.cli tooling --project NAME --update --confirm`. On supported hosts this prepares verified Go 1.26.9 and the pure langdetect 1.0.9 wheel from `native_tooling.json`. Xcode/SDK, Java and signing have separate setup. Preserve an exact existing Go selection. Move conflicting Go or unverified legacy wheel contents aside under the guarded tooling lock before repair. Use [tooling readiness and repair](../../user/build-manager.md#project-tooling-readiness-and-repair) for environment recovery.

To preserve a legacy unverified wheel folder, run the guarded move from the root. On Windows change the child interpreter to `mobile_build/.venv/Scripts/python.exe`. Then rerun the tooling update.

```sh
python3 -m logistics_build.tooling_bootstrap sync --venv mobile_build/.venv -- \
  mobile_build/.venv/bin/python -c '
from pathlib import Path
from uuid import uuid4
from logistics_build.tooling_bootstrap import owned_path
root = Path.cwd().resolve()
source = root / "mobile_build/.tools/release-wheels"
target = root / "test-results" / ("native-wheels-preserved-" + uuid4().hex)
if not all(owned_path(root, path) for path in (source, target)) or not source.is_dir():
    raise SystemExit("Preserve the existing linked or missing path separately; no changes made.")
target.parent.mkdir(parents=True, exist_ok=True)
source.rename(target)
print("Preserved legacy wheels:", target)
'
```

## Hosted release evidence

Hosted reuse requires authenticated successful workflow families for the exact source, all mandatory jobs and at most 24 hours of age. Unavailable, stale or incomplete proof triggers fresh required checks. Packaging and publication still run. [Signed local coverage](build-tooling.md#signed-local-coverage-in-hosted-releases) is a separate input-bound mechanism.

### Reusing automatic hosted validation

With reuse enabled, one unambiguous branch-push run can satisfy matching validation. Verify repository/head repository, workflow contract, branch, commit, target coverage, creation time and exact attempt. Observe the immutable receipt. A matching failed run fails its gate; an ambiguous match needs review or explicit fresh dispatch. Cancelling an observer leaves an adopted shared run active.

## Retained source-publication recovery

New plans journal tag/write intent against the reviewed owner, repository, tag object, commit and gitlink. Resume an existing tag only with that exact receipt. Reconcile legacy or foreign attempts manually. Review the existing ZIP's digest and source/dependency manifests. Metadata repair changes reviewed title/body while preserving draft/prerelease state and assets.

Completion requires valid assets and exact-attempt `evidence`, `package` and `publish` success with terminal visible jobs. The reviewed workflow hash binds this witness. Default hosted validation stays on; a reviewed `testing.github_validation=off` run records its immutable bypass and publishes without hosted test credit.

One failed-jobs rerun is allowed for a proven artifact-service finalization failure with bounded logs and successful prior steps. Save intent before the POST. Reconcile ambiguous responses by GET for the exact attempt. Observation can resume from its receipt after cancellation or timeout.
