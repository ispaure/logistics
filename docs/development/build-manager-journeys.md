# Combined validation and delivery

Logistics declares the manager's journey schema 1 in `build-project.json`.
The standalone manager uses `logistics_build.manager_journeys` through
`LogisticsProject.make_journey`. The isolated script
`logistics_build/manager_bridge.py` exposes the same `journey_plan` action.

For the operator workflow, see [validating and delivering Logistics](../user/build-manager-journeys.md).

## Trace a validation plan

1. From the Logistics checkout root, check that both environments have the
   manager revision declared in `build-manager-dependency.json`:

   ```sh
   python3 logistics_build/tooling_bootstrap.py status
   ```

   Use `py` on Windows. If the result reports `needs_update`, follow
   [project tooling readiness and repair](../user/build-manager.md#project-tooling-readiness-and-repair).
   Run this check even after `dev.py doctor` passes.
2. In the standalone manager, select the trusted Logistics checkout. Choose
   **Run checks**, a supported platform and a local execution host.
   Select **Next: review plan** and inspect the source, host, phases and
   prerequisites. Stop at review for this walkthrough. **Start validation**
   executes the reviewed plan.
3. In the checkout, follow `build-project.json` to
   `logistics_build/build_project.py:LogisticsProject.make_journey` and
   `logistics_build/manager_journeys.py`. Follow the plan's test groups into
   [suite discovery](#shared-tests-and-suite-discovery). Logistics declares
   project inputs and gates. Build Manager reviews and executes the plan.
4. To exercise the adapter with synthetic source and settings, use the root
   desktop environment with the pinned manager installed:

   ```sh
   python3 dev.py test desktop --exact-file Python/tests/tooling/test_manager_journeys.py
   ```

   This runs the portable journey contracts with fixture plans and mocked
   native and provider commands. Use `py` on Windows. For missing manager
   imports, see [local manager dependency and verification](#local-manager-dependency-and-verification).

## Source, settings and resource integrity

Capture source identity, app version and effective settings once in an immutable
internal PlanningContext. Every platform/preparation branch consumes this context,
with unique step IDs, captured settings profiles and explicit dependencies. Snapshot
creation checks its identity against the capture before writing, and final source/
settings verification refuses changes made during preparation. Plans are combined
under this shared context, not by assuming independently captured sources match.

Workspace locks, snapshot holds and declared resource limits still apply.
Independent Android and iOS branches can overlap. Each branch keeps its
own cleanup and result dependencies, so failure in one branch does not
block unrelated artifact review or delivery.

For Android device delivery, a new independent Debug plan that captures its own
source and prepares its own package uses `tmp/build/mobile/android/`. Plans
with a shared build, a retained source snapshot or mixed signing use the
existing device-workspace path. Mixed Debug/Beta plans retain a workspace per
signing group and lock every group's workspace throughout execution. See
[storage retention](build-manager.md#automatic-storage-retention) for both roots.

Credentials remain protected references or inherited environment variables.
Profiles and plans never contain private-key/token contents. Changing a credential
file reference in Settings requires a location outside Git checkouts; existing
references are preserved while editing unrelated values, without copying or moving
credential files. Runtime executable paths are not credential files.

## Local manager dependency and verification

Use the revision in `build-manager-dependency.json` unless explicitly testing a
local manager checkout. See [manager installation](../user/build-manager.md#external-manager-installation-adapter-api-1)
for the pinned installation and local override.

Portable acceptance uses the real project adapter and JSON bridge, temporary
local repositories, mocked native/provider entry points and harmless subprocesses.
It covers shared capture, complete release gates, source changes, cleanup order,
partial failure, approval pause/resume, retained preparation, and overlapping
independent uploads. Use the [platform checks](platform-checks.md) for native
validation, and verify the source and artifact identities used for delivery.

## Shared tests and suite discovery

The project-owned `build-tests.json` is resolved by the headless manager
`build_manager.test_manifest` API against the selected source snapshot.
Desktop validation and full mobile host gates run the pinned
`Python/commonUtils/tests` suite first; project tests depend on its success.
Mobile tooling, desktop UI and mobile host tests may run together after that
shared gate, before native acceptance. A shared failure blocks those consumers.
Focused advanced suites intentionally run only their requested scope and cannot
stand in for complete release acceptance. CI/local desktop checks consume the
same desktop inventory. Native/runtime acceptance remains project-owned.

Suites use stable IDs, `test_*.py` files (existing isolated runner also supports
`test*.py`), explicit `after` prerequisites and named interpreter environments.
Dependency suites must name an in-checkout Git submodule owner at its pinned
commit; no sibling checkout or dependency installation is inferred.
The manager wiki’s test-manifest contract documents the complete schema.
New checkouts must contain this manifest in the source revision selected for a
run; old revisions that predate it must use their matching adapter version.

## Retried guest validation

Windows and Linux guest backends retain each execution under a distinct attempt
directory and atomically publish its latest result at the plan's declared result
path. Previous reports and logs remain intact. A completed matching source/backend
record with confirmed guest cleanup may be retried. Running, uncleaned, mismatched
or unrecognized work requires reconciliation first; retry never deletes it.
The retry wrapper holds the result-directory lock and each backend retains its
normal VM operation lock, ownership checks and tool-cache policy.

Focused guest diagnostics accept `manager:test_ui.py` (or another test filename
pattern) through the existing Test pattern field. Both guest backends run those
contracts from the exact installed, project-pinned manager checkout. `shared:`
and ordinary Logistics patterns keep their existing routing. A diagnostic pass
does not replace the complete platform release gate.

For a retained-run source review, `python -m logistics_build.continuation_inputs --root .
--previous <exact-commit> --current <exact-commit>` compares committed Git object
inventories, including file modes and submodule pins. It reports application
input equality separately from the manager pin and the explicitly enumerated
guest orchestration paths. Unknown scripts and native harness changes invalidate
that equality. This read-only assessment cannot import results, authorize reuse,
change a plan or pass a release gate. Original outcomes, cleanup, artifacts,
platform/toolchain identity and execution-engine changes still need verification.

For an executable source prerequisite, add `--require-current-equivalent`. This
requires the exact current HEAD, a clean checkout (including untracked files),
and equal application/native inputs. It exits unsuccessfully on a mismatch.
The returned identity can be bound with `--expect-identity` on subsequent checks.
This verifies source applicability only: changed desktop fixtures still require
fresh validation, and the receipt never authorizes source reuse by itself.

Add `--native-output <retained-run> --native-plan-identity <SHA>` to verify the
complete original iPhone/Duo/iPad and Android native/runtime inventories, selected
simulator identities, cleanup and acceptance outcomes, and matching current build
toolchains. Original source must match the explicitly selected previous commit.
The review identity binds those records and the current source applicability.
Binary availability is reported separately: an absent QA APK cannot be deployed.
This prerequisite still needs the generic original-check/log/artifact verifier,
engine review and current desktop coverage before release continuation. It never
changes original outcomes or triggers installations, builds or uploads.

If Windows setup fails before tests start and leaves an incomplete attempt,
`python -m logistics_build.guest_attempts reconcile-windows-setup --directory <result-root>
--manager-checkout <exact-pinned-manager>` can reconcile it without signing in.
The command verifies the manager pin and recorded VM ownership, then performs a
fixed read-only query of that attempt's exact guest namespace. Only a confirmed
absent namespace permits a fresh attempt. An existing namespace, changed source,
changed preparation record or foreign receipt remains blocked. The reconciliation
is appended beside the preparation record; original failure reports and timings
are preserved. This command neither runs tests as SYSTEM nor deletes guest files.


Completed manager-only guest diagnostics can be reviewed with
`python -m logistics_build.guest_results --directory <completed-attempt> --source-plan
<original-plan> --backend <declared-backend> --manager-commit <exact-pin>`.
The verifier requires the complete `test*.py` manager discovery command, every
required step passed, a clean exact manager/shared checkout, matching captured
source and backend, intact collected logs/results, and confirmed guest cleanup.
For legacy Linux reports missing a backend field, it verifies that identity from
the independently bound guest plan. It returns a review identity;
`--expect-identity <reviewed-identity>` rejects changed evidence, and `--output`
saves a new receipt. Neither operation changes the original failed wrapper or
claims a fresh execution or an application-platform pass. This local review
receipt is not the authenticated local-to-GitHub evidence handoff.

Application-input comparisons also enumerate changed desktop fixtures. Such
changes require fresh validation of those fixtures before retained desktop
coverage can be accepted; they do not automatically invalidate unchanged native
application inputs. The source comparison alone still authorizes no reuse.

TestFlight delivery streams upload and Apple-processing progress into the manager
phase log. A completed distribution receipt includes the provider-confirmed build
and external-group assignment, including any pending Apple beta-review state.
Upload completion alone cannot satisfy the external tester destination; a missing
or mismatched assignment remains an uncertain recorded attempt requiring
reconciliation before another upload.
