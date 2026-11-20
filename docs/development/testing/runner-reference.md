# Test runner reference

Use [Testing Logistics](testing.md) to choose and run the smallest useful check.
This page explains execution details for broader runs, fixture work and CI.
Commands run from the checkout root; substitute `py` for `python3` on Windows.

## Selection and environments

`dev.py test desktop` discovers `Python/tests/`; `dev.py test mobile` discovers
`mobile_build/tests/`. Both recurse through their test roots. Omit the filename
for the full selection, quote filename globs, or use repeatable
`--exact-file` repository-relative POSIX paths. A pattern and exact files cannot
be combined. Unknown paths, duplicate paths and empty selections fail.

Desktop uses root `.venv` and offscreen Qt. Mobile host tests use
`mobile_build/.venv` and `TOGA_BACKEND=toga_dummy`. Windows interpreters live under
`Scripts/python.exe`. `--python PATH` overrides the selected interpreter;
`--dry-run` prints the command and environment without executing tests.

## Stages, isolation and failure policy

Declare a file's default `TEST_STAGE = TestStage.REGRESSION` with
`commonUtils.testing.stages`; use `@stage(TestStage.SMOKE)` for class or method
overrides. Method overrides win. Embedded and non-Python sources use stage
comments. Keep ordered native journeys in one stage.

`test-structure.json` declares classified roots.
`python3 dev.py test-structure --inventory` lists source declarations.
`dev.py test desktop --inventory` and
`dev.py test bridge --profile smoke --inventory` select without runtime discovery.
Direct runners also accept repeated `--stage`.

Each Python file-stage runs in a fresh process, ordered by stage and path by
default, with a 300-second per-file deadline. Native acceptance preserves its
ordered journeys. The [profile table](testing.md#execution-stages-and-failure-policy)
explains smoke, daily and full selections.

Diagnostic mode continues independent work. Fast mode gates later stages on
smoke, stops on discovery failure and stops later owner environments after a
failed one. `--fail-fast` also stops at the first failure inside a file. Cleanup
still runs. JSON records unrun cases and JUnit marks them skipped with reasons.
`coverage_complete` describes execution of the selected scope; assess it together
with case outcomes and exit status.

## Parallel regressions and shared host budgets

Direct runs default to serial file-stage processes. Windows, Linux and macOS
can use 1, 2, 4 or 8 workers for the reviewed portable files in
`Python/tests/parallel_regressions.py`. macOS also runs the reviewed offscreen
Qt groups in parallel. Windows also admits reviewed commonUtils directory index
and browser files and Logistics Git and editor files.

```sh
python3 dev.py test shared --workers 4
# macOS host fixtures
python3 dev.py test mobile --workers 4
```

The direct runner accepts `--isolate-modules --workers 4`. With default ordering
in diagnostic mode, reviewed files run together within each stage, followed by
exclusive files in plan order. Fast mode, fail-fast, explicit ordering and
historical timing order retain their admission order. JSON and JUnit always
retain plan order. Audit fixture isolation and cancellation before adding files.
WebEngine, real media, provider integration, native windows, the shared Toga
replay and the Go bridge suite run exclusively. Cancellation gives a pooled
worker up to five seconds to retire supervised helpers before the runner cleans
up its Windows Job Object or POSIX process group.

Manager reservations coordinate participating processes across workflows. Defaults are
four slots per platform and half logical CPUs across the host, capped at eight.
Manager selects a tested pool within its reservation and the captured source's capabilities.
Direct pools require manual coordination. Hosted Windows, Fedora and macOS use
up to two workers, capped by available CPUs. Fedora pools the portable files.

On macOS, seven reviewed mobile-host files use workers with the dummy Toga
backend. They cover editor picking, notebook storage, Notes Library panels,
Android Back handling, reader opening and workspace navigation. Simulator and device tests retain their own gates.

## Shared-library test matrix

```sh
python3 dev.py test shared
python3 dev.py test shared test_streams.py
python3 dev.py test shared 'test_native*browser*.py' --dry-run
```

The full matrix runs commonUtils Qt/portable tests in `.venv` and replays selected
`tests/native/test_native*.py` in `mobile_build/.venv` with dummy Toga. Portable-only
selections need only desktop setup. `test_qt_mobile_host.py` stays in the Qt leg.
Use `--python PATH` for Qt and `--native-python PATH` for Toga. Required missing
toolkits fail. The replay overlaps Qt coverage.

Watcher tests need filesystem notifications. Loopback fixtures and Qt WebEngine need
host socket and process capabilities. Recheck permission-related failures with disposable
profiles and the required capabilities. Keep `PLAYWRIGHT_BROWSERS_PATH` consistent
between installation and testing because test caches are isolated. Full mobile release
plans require Node and Playwright before host tests. Configure the manager's Node,
Node modules and optional Chrome fields (or `LOGISTICS_NODE`, `NODE_PATH`,
`LOGISTICS_CHROME`). Leave Chrome empty for Playwright's installed Chromium.
The prepared plan captures these paths, and its prerequisite checks the existing
installation before running tests. Developer runs retain optional browser skips.

## Provider and feature prerequisites

`test_local_crypt*.py` covers synthetic encrypted resources. A missing pinned
rclone skips optional CLI cases. Any nonempty `LOGISTICS_REQUIRE_LOCALCRYPT_TESTS`
makes that prerequisite mandatory. The platform runner's `--install` provisions
pinned rclone with archive and executable hash checks. Daily covers standard
encrypted rename/batching and empty/populated startup; full adds alternate
encryption modes, exhaustive Help sweeps and packaged Help navigation.

Use `test_git_ui*.py` for Git UI and `test_git_watchers.py` for notifications.
LM attachment tests in `test_lm_ui.py` require localhost access; their behavior
and owner trace belong in the [LM developer guide](../../features/lm/development/development.md).
Check the feature guide for other prerequisites before treating a skip as
successful coverage.

## Timing reports and fixtures

Standalone Python regression runs save per-environment JSON in `tmp/test-results/test-timings/`.
The desktop platform runner puts these reports alongside the other evidence for its run.
Direct runners accept `--report PATH`. File times include imports and fixture/process
overhead. Case times include case setup and cleanup. Reports checkpoint completed
work and reject missing or mismatched case evidence. `complete` describes runner
completion. Go bridge stage results appear on the console.

Use `python3 dev.py test <suite> [filename] --timings REPORT.json` to order one Python
leg using a previous report from the same root, interpreter, platform and backend.
Run shared legs separately when supplying history. Compare before/after IDs,
outcomes and file durations under matched conditions. Keep data-loss, encryption
and recovery coverage when reducing fixture cost. See [fixture selection](adding-tests.md).

## Desktop test folders

`Python/tests/` discovers recursively. Group imports as `tests.<owner>`.

| Behavior | Folders |
| --- | --- |
| Host, documents and workspace | `application/`, `files/`, `readers/`, `editing/`, `notebooks/` |
| Providers, tools and external apps | `resources/`, `integrations/`, `version_control/`, `blender/`, `calibre/`, `ide/` |
| Conversion, archives and chat | `comics/`, `images/`, `archives/`, `chat/` |
| Build and policy | `tooling/` |

Some `test_mobile_*.py` contracts run here. Check [staging](../../../mobile_build/tools.py)
and [runtime smoke](../../../Python/mobile/smoke.py) before moving flat portable test modules or fixtures.
See the [shared test folder map](../../../Python/commonUtils/docs/development/reference/tests/tests.md)
for commonUtils.

## CI, release gates and advanced validation

Windows runs native Qt startup with the `windows` plugin before offscreen regressions.
Use physical hardware for mixed-DPI monitor crossings. See [platform checks](platform-checks.md)
for hosted deadlines and diagnostics. Manager runs fresh smoke before regression and extended
phases. Full mobile release plans also run architecture, toolchain, hygiene and lint on captured source.
[Source releases](../build-release/releasing.md) require all desktop platform and archive
checks, Android/iOS native acceptance and both embedded runtime gates. Each
managed mobile platform runs fresh smoke for its host suites before their
regression and extended stages. The platform's native and runtime gates still
depend on the complete host coverage. iOS and Android host receipts are scoped
to their respective platforms.
Hosted [runtime checks](../build-release/mobile-launchers.md#hosted-builds-and-runtime-checks)
require the pinned interpreter, exact source, complete cases and zero failures/skips.
Publish commonUtils revisions before Logistics commits that reference them.

For an isolated order audit:

Use a fresh run identifier for `RUN_ID`.

```sh
PYTHONPATH=Python:. .venv/bin/python Python/tests/run_regressions.py Python/tests --isolate-modules --order random --seed 7 --report tmp/test-results/RUN_ID/order-audit.json
```

Use `--order reverse` for a reverse audit. Both reorder within stages and preserve
class fixtures. Use fresh execution with evidence reuse disabled and dependencies
fixed. Use private fixtures for subprocess APIs that resolve OS home independently.

## Portable import matrix

Run `python dev.py test desktop test_portable_imports.py` and
`python dev.py test desktop test_architecture_contracts.py` after portable-owner
changes. Fresh children reject presentation imports even when caught.
Run `python dev.py test desktop test_document_architecture.py` for storage-boundary changes.
See the [portable owner policy](../architecture/extension-points.md#portable-owner-policy).
The external SDK's own suite runs separately with `python -m build_manager.contracts`
using its owning interpreter.
