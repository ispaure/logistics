# Combined validation and delivery

Logistics now declares the manager's journey schema 1 in `build-project.json`.
The standalone manager uses `logistics_build.manager_journeys` through
`LogisticsProject.make_journey`. The isolated script
`logistics_build/manager_bridge.py` exposes the same `journey_plan` action.
The old dedicated deployment window is retired; project device/signing/provider
helpers remain adapter implementation details.

For the operator workflow, see [validating and delivering Logistics](../user/build-manager-journeys.md).

## Source, settings and resource integrity

Capture source identity, app version and effective settings once in an immutable
internal PlanningContext. Every platform/preparation branch consumes this context,
with unique step IDs, captured settings profiles and explicit dependencies. Snapshot
creation checks its identity against the capture before writing, and final source/
settings verification refuses changes made during preparation. Plans are combined
under this shared context, not by assuming independently captured sources match.

Existing workspace operation locks, snapshot holds, resource requirements and
project retention remain authoritative. Mobile validation branches run in sequence
so their disposable device lifecycles do not overlap. An always-run admission step
lets later platform validation proceed after an earlier platform fails, without making one platform’s success a validation prerequisite for the other.
The admission step uses a completion-only scheduling edge. Artifact review follows
only success-required dependencies, so an unrelated failure cannot veto delivery. Owned cleanup is scoped to its
branch so it cannot wait forever on delivery steps that depend on it.

Credentials remain protected references or inherited environment variables.
Profiles and plans never contain private-key/token contents. Changing a credential
file reference in Settings requires a location outside Git checkouts; existing
references are preserved while editing unrelated values, without copying or moving
credential files. Runtime executable paths are not credential files.

## Local manager dependency and verification

This integration needs the manager with journey schema 1 and explicit host
backend mappings. The current local project environment uses the existing editable
manager installation. Its published manager pin is not advanced to an unpublished
revision, and `build-manager-dependency.json` is preserved. For another environment,
install the reviewed local manager explicitly or advance the project pin only after
an authorized publication. Do not silently substitute a different checkout or pin.

Portable acceptance uses the real project adapter and JSON bridge, temporary
local repositories, mocked native/provider entry points and harmless subprocesses.
It covers shared capture, complete release gates, source changes, cleanup order,
partial failure, approval pause/resume, retained preparation, and overlapping
independent uploads. No native VM/device checks, signing/build acceptance, hosted
dispatch, uploads or publication were run for this integration. Prior native
acceptance does not certify the new combined journey. Native acceptance remains
separate, explicitly authorized work at exact source/artifact identities.

- [Build manager](build-manager.md)
- [Developer home](development.md)

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
