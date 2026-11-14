# Testing Logistics

Run commands from the checkout root. Use `py` in place of `python3` on Windows.

- [Add and diagnose a test](adding-tests.md)
- [Mobile performance and profiling](mobile-performance.md)
- [Cross-platform archive checks](platform-checks.md)
- [Local validation artifacts](validation-artifacts.md)

## Set up a checkout

```sh
git clone --recurse-submodules https://github.com/ispaure/logistics.git
cd logistics
```

For missing submodules, preserve local edits and run `git submodule update --init --recursive`.
Follow the [first contribution](../setup/getting-started.md) to launch the app.
Desktop uses Python 3.12.2 and the PySide6 pin in [Python/pyproject.toml](../../../Python/pyproject.toml).
Its Qt wheels require macOS 14+, Windows 10/11 or Linux with glibc 2.34+ (x86-64) or 2.39+ (ARM64).
Use a separate environment to trial runtime upgrades. Refresh the desktop lock with `uv lock --project Python`.

## Run everyday checks

`python3 dev.py doctor` checks interpreters, dependencies, submodules and tools without modifying environments.
Setup needs uv and access to uncached packages. Both setup commands accept `--dry-run`.

```sh
python3 dev.py setup desktop
python3 dev.py setup mobile
python3 dev.py test desktop test_feature_registry.py
python3 dev.py test desktop 'test_git_*.py'
python3 dev.py test desktop test_documentation_layout.py
python3 dev.py test mobile test_editor_picker.py
python3 dev.py lint
```

Desktop and lint use root `.venv` with offscreen Qt for tests. Mobile host tests use
`mobile_build/.venv` and `TOGA_BACKEND=toga_dummy`. Mobile setup adds locked host tools including pip and
Briefcase, with no SDK required. Windows interpreters live under `Scripts/python.exe`.
Use `--python /path/to/python` to override and `--dry-run` to inspect. Native appearance,
gestures and OS lifecycle require the [mobile handbook](../build-release/mobile-handbook.md).

Equivalent desktop setup on macOS/Linux:

```sh
UV_PROJECT_ENVIRONMENT="$PWD/.venv" uv sync --project Python --locked --python 3.12.2
```

On Windows PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$PWD/.venv"
uv sync --project Python --locked --python 3.12.2
```

Omit the filename to run the selected suite. Quote globs. For duplicate filenames,
pass repeatable exact repository-relative POSIX paths:

```sh
python3 dev.py test desktop --exact-file Python/tests/tooling/test_regression_runner.py
python3 dev.py test mobile --exact-file mobile_build/tests/documents/test_editor_picker.py
```

Use either a filename/glob or exact files. Unmatched globs, duplicate paths,
paths outside the suite and empty selections fail.

### Parallel regressions and shared host budgets

Direct runs default to serial file-stage processes. Reviewed macOS offscreen files
in `Python/tests/parallel_regressions.py` accept 1, 2, 4 or 8 workers:

```sh
python3 dev.py test desktop 'test_git*.py' --workers 4
python3 dev.py test shared 'test_markdown*.py' --workers 4
```

The direct runner accepts `--isolate-modules --workers 4`. Unreviewed files,
stage transitions and the separate Toga replay stay serial. WebEngine, real media,
provider integration, native windows and Go bridge tests stay exclusive.
Audit fixture isolation and cancellation before adding files. JSON and JUnit retain
plan order. Cancellation gives concurrent children up to five seconds to retire
their supervised helpers before process-group cleanup.

Manager reservations coordinate participating processes across workflows. Defaults are
four slots per platform and half logical CPUs across the host, capped at eight.
Manager selects a tested pool within its reservation and the captured source's capabilities.
Direct pools require manual coordination. GitHub-hosted macOS uses up to two workers,
capped by CPU count. Windows and Fedora are serial.

### Execution stages and failure policy

Declare one default `TEST_STAGE = TestStage.REGRESSION` using
`commonUtils.testing.stages`. Override with `@stage(TestStage.SMOKE)` at class
or method level. Method overrides win. Embedded or non-Python sources use stage
comments (`#` or `//`). Keep ordered native journeys in one stage.

```sh
python3 dev.py test-structure
python3 dev.py test desktop --profile smoke --mode fast
python3 dev.py test mobile --profile daily
python3 dev.py test shared --profile full
python3 dev.py test bridge --profile smoke --mode fast
python3 dev.py test-owner document-services --profile daily
```

| Profile | Selected stages |
| --- | --- |
| `smoke` | `SMOKE`, deterministic startup and core contracts |
| `daily` | Smoke plus `REGRESSION`, ordinary behavior |
| `full` (default) | Daily plus `EXTENDED`, costly matrices, parity and soak checks |

`test-structure.json` declares classified roots. `dev.py test-structure --inventory`
lists source declarations. `dev.py test desktop --inventory` and
`python3 dev.py test bridge --profile smoke --inventory` apply selection without runtime
discovery. Direct runners accept repeated `--stage`. Each Python file-stage runs in a
fresh process, ordered by stage and path by default, with a 300-second per-file deadline.
Native acceptance keeps its complete ordered journeys.

Diagnostic mode continues independent work. Fast mode gates later stages on smoke,
stops on discovery failure and stops later owner environments after a failed one.
`--fail-fast` also stops at the first failure inside a file. Cleanup still runs.
JSON records unrun cases and JUnit marks them skipped with reasons.
`coverage_complete` describes execution of the selected scope. Check outcomes and exit status.

### Focused resource, Git and tooling checks

`test_local_crypt*.py` covers synthetic encrypted resources. A missing pinned rclone
skips optional CLI cases. Any nonempty `LOGISTICS_REQUIRE_LOCALCRYPT_TESTS` makes
that prerequisite mandatory. The platform runner's `--install` provisions pinned
rclone with archive and executable hash checks. Daily covers standard encrypted
rename/batching and empty/populated startup. Full adds alternate encryption modes,
exhaustive help sweeps and packaged Help navigation.

Use `test_git_ui*.py` for Git UI and `test_git_watchers.py` for notifications.
Run `python3 dev.py architecture` for live-tree boundaries, including deferred factories.

### Shared-library test matrix

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

### Test timing and maintenance

#### Shared native rotation inventory

`rotation_screens.py` owns IDs and setup under `mobile_build/native_tests/tests/logisticsmobile/`.
`rotation_checks.py` owns route, content and geometry checks. Two full cycles across
31 screens yield 310 observations. Reports separate registered screens and gaps
(`rotation_inventory`) from observations (`rotation_samples`). The catalog covers all
top-level destinations. Settings gaps are Features, Camera, Read aloud, Markdown,
EPUB, Books & Comics, Video, LM Chat and Reset. `exercise_rotation(panels=...)` limits setup
to selected IDs in inventory order. Empty or unknown selections fail.

```sh
python3 dev.py test mobile test_rotation_screen_inventory.py
python3 dev.py test mobile 'test_native_rotation*.py'
```

Run the maintained native scenario for rotation, rendering and safe-area acceptance.

#### Timing reports and fixtures

Python regression runs save per-environment JSON in `test-results/test-timings/`.
Direct runners accept `--report PATH`. File times include imports and fixture/process
overhead. Case times include case setup and cleanup. Reports checkpoint completed
work and reject missing or mismatched case evidence. `complete` describes runner
completion. Go bridge stage results appear on the console.

Use `python3 dev.py test <suite> [filename] --timings REPORT.json` to order one Python
leg using a previous report from the same root, interpreter, platform and backend.
Run shared legs separately when supplying history. Compare before/after IDs,
outcomes and file durations under matched conditions. Keep data-loss, encryption
and recovery coverage when reducing fixture cost. See [fixture selection](adding-tests.md).

### Desktop test folders

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

### Find the tests for your change

Run `python3 dev.py owners`, then `python3 dev.py test-owner books --dry-run` with
your owner ID. Remove `--dry-run` to run one deduplicated selection per environment.
`Scripts/ownership.json` owns these associations. An empty profile selection fails.
For image compression cancellation and encoder recovery, trace `compress_folders`
in `Python/features/images/actions.py`, then run:

```sh
python3 dev.py test-owner images --dry-run
python3 dev.py test desktop --exact-file Python/tests/images/test_image_folder_tool.py
```

Use `python3 dev.py test desktop` or `python3 dev.py test mobile` for complete host
suites, and `python3 dev.py test desktop test_mobile_packaging.py` after editing
an owner's `mobile_sources.json`. For a managed native or platform plan, see the
[validation walkthrough](../build-release/build-manager-journeys.md#trace-a-validation-plan).

## Correctness checks and test ownership

Lint checks correctness including untracked source. Review optional unused imports
and assignments with the owner before removing re-exports, registrations or lifetime handles.
Use the shared `QtTestCase`, its `temporary_directory()` and bounded `wait_until()`
to retire workers and windows before deleting storage. See the
[shared fixture guide](../../../Python/commonUtils/docs/development/reference/tests/tests.md).

## CI, release gates and advanced validation

Windows runs native Qt startup with the `windows` plugin before offscreen regressions.
Use physical hardware for mixed-DPI monitor crossings. See [platform checks](platform-checks.md)
for hosted deadlines and diagnostics. Manager runs fresh smoke before regression and extended
phases. Full mobile release plans also run architecture, toolchain, hygiene and lint on captured source.
[Source releases](../build-release/releasing.md) require all desktop platform and archive
checks, Android/iOS native acceptance and both embedded runtime gates. Hosted
[runtime checks](../build-release/mobile-launchers.md#hosted-builds-and-runtime-checks)
require the pinned interpreter, exact source, complete cases and zero failures/skips.
Publish commonUtils revisions before Logistics commits that reference them.

For an isolated order audit:

```sh
PYTHONPATH=Python:. .venv/bin/python Python/tests/run_regressions.py Python/tests --isolate-modules --order random --seed 7 --report test-results/order-audit.json
```

Use `--order reverse` for a reverse audit. Both reorder within stages and preserve
class fixtures. Use fresh execution with evidence reuse disabled and dependencies
fixed. Use private fixtures for subprocess APIs that resolve OS home independently.

## Updating mobile host dependencies

Edit `mobile_build/requirements-host.in`, then regenerate and commit the lock:

```sh
uv pip compile mobile_build/requirements-host.in --python-version 3.12 --universal --generate-hashes --output-file mobile_build/requirements-host.txt
python3 dev.py toolchain
```

Native dependencies stay in `mobile_build/pyproject.toml`. Prepare pinned Go and
the langdetect wheel via **Update project tooling…**, or
`python -m build_manager.cli tooling --project NAME --update --confirm`. See
[native prerequisites](../build-release/build-manager.md#project-owned-native-prerequisite-setup).

## Local disk usage and private files

Use [artifact locations](validation-artifacts.md#find-an-output) and
[retention](../build-release/build-manager.md#automatic-storage-retention).
Keep credentials, environments and generated output local. Run `python3 dev.py hygiene`
after staging specific paths. It checks the index for ignored files and recognizable secrets.

## Worked contribution: desktop LM attachments

Trace the `lm.chat` factory to `LMPage`, then to `ui/attachments.py:AttachmentController`.
For an attachment change, preserve `AttachmentHost` context, portable `project_tools.py`
containment/exclusions and the draft bound. Run `python3 dev.py test desktop test_lm_ui.py`
with localhost available. Expect selection/file attachments, exclusions, project reopening
and draft preservation to pass. See the [LM developer guide](../../features/lm/development/development.md).
Use `dev.py compatibility` for forwarded imports.

## Portable import matrix

Run `python dev.py test desktop test_portable_imports.py` and
`python dev.py test desktop test_architecture_contracts.py` after portable-owner
changes. Fresh children reject presentation imports even when caught.
Run `python dev.py test desktop test_document_architecture.py` for storage-boundary changes.
See the [portable owner policy](../architecture/architecture.md#portable-owner-policy).
The external SDK's own suite runs separately with `python -m build_manager.contracts`
using its owning interpreter.
