# Testing Logistics

From the repository root, use [test selection](#find-the-tests-for-your-change) to choose the smallest suite that covers your change.

- [Add and diagnose a Logistics test](adding-tests.md)
- [Mobile performance and profiling](mobile-performance.md)
- [Cross-platform archive checks](platform-checks.md)
- [Local validation artifacts](validation-artifacts.md)

New contributors can use the shorter [first-contribution walkthrough](../setup/getting-started.md).
For a new test, follow [the worked test contribution](adding-tests.md), including
which manifests to edit and how cases reach manager results.
This page is the detailed command and validation reference. Run commands from the
repository root unless a section says otherwise.

- [Checkout and environment](#set-up-a-checkout)
- [Everyday checks](#run-everyday-checks) and [shared-library matrix](#shared-library-test-matrix)
- [Find tests for your change](#find-the-tests-for-your-change)
- [CI and release gates](#ci-release-gates-and-advanced-validation)
- [Dependency updates](#updating-mobile-host-dependencies) and [local/private files](#local-disk-usage-and-private-files)
- [Worked LM contribution](#worked-contribution-desktop-lm-attachments)

Choose tests by the behavior changed. A host/dummy-backend pass does not certify
native interactions, provider writes or physical-device installs.

## Set up a checkout

From a fresh clone:

```sh
git clone --recurse-submodules https://github.com/ispaure/logistics.git
cd logistics
```

For an existing checkout with missing shared files, use
`git submodule update --init --recursive` after preserving any submodule edits.
Read [AGENTS.md](../../../AGENTS.md) for repository conventions. Open the platform
launcher listed in the [root README](../../../README.md#get-started) to run the desktop
app. An editor can open the repository root; `Python/` is the application import
root, not a second checkout.

The existing launchers install `uv` when needed, select Python 3.12.2, and
synchronize [Python/pyproject.toml](../../../Python/pyproject.toml) and its
[lockfile](../../../Python/uv.lock) into the root `.venv`. Initial setup requires internet
access. [launch_config.ini](../../../launch_config.ini) controls launcher paths; the entry
point is `Python/launch.py`. Feature-specific software and credentials are covered
in [configuration](../../user/configuration.md).

The desktop manifest pins PySide6 6.12.0. Mobile uses its own Briefcase manifest
and Toga backends; it does not use desktop Qt. Regenerate `Python/uv.lock`
with `uv lock --project Python` after changing dependencies; CI exports it with
`--locked`. The published Qt wheels require macOS 14+, Linux glibc 2.34+ on
x86-64 or 2.39+ on ARM64, and Windows 10/11. Test runtime upgrades in a separate
environment before synchronizing the environment used by a running application.

## Run everyday checks

Run `python3 dev.py doctor` for read-only interpreter, package, submodule and
optional native-tool diagnostics. It does not read credential files or change an
environment. A nonzero status means a contributor prerequisite is missing.

The root [dev.py](../../../dev.py) selects the suite's environment, sets import paths
and headless backends, and delegates to the existing runners. It works from any
working directory when invoked by its path. The `setup` command installs declared host dependencies; test, lint and doctor
do not build or deploy an app. From the repository root, use `python3` on macOS/Linux or
`py` on Windows; this bootstrap Python only needs the standard library.

For repeatable setup, run `python3 dev.py setup desktop` or
`python3 dev.py setup mobile` (use `py` on Windows). Both accept `--dry-run`.
The desktop setup uses the existing uv lock and root `.venv`. Mobile setup creates
`mobile_build/.venv` if absent and installs the hash-locked host test requirements
additively, preserving any native build tools already present. This includes
Briefcase (native build orchestration) and pip (the interpreter runtime installer),
so a fresh seedless environment can invoke both without a later manual repair.
These are host tools and are never copied into the application payload. Setup
needs no native SDK; it needs uv and network access for uncached packages.
`doctor` reports missing mobile host tools with the mobile setup command. Project
tooling/manager readiness is separate from mobile host-tool, SDK and signing readiness.

The equivalent desktop command installs the pinned environment and developer tools with uv. These commands
explicitly target the root `.venv`, so activation is unnecessary. The desktop
launcher installs uv if needed.

```sh
# macOS / Linux
UV_PROJECT_ENVIRONMENT="$PWD/.venv" uv sync --project Python --locked --python 3.12.2
```

```powershell
# Windows PowerShell
$env:UV_PROJECT_ENVIRONMENT = "$PWD/.venv"
uv sync --project Python --locked --python 3.12.2
```

Then run the smallest relevant check:

```sh
python3 dev.py test desktop test_feature_registry.py
python3 dev.py test desktop 'test_git_*.py'
python3 dev.py test desktop test_documentation_layout.py
python3 dev.py lint
```

Replace `python3` with `py` on Windows. Quote wildcard patterns so the shell does
not expand them. Omit the filename/pattern to run the whole selected suite.
No matching files is an error. Each test file runs in a fresh process; failing
files or timeouts fail the command. The helper returns the check's exit status.

Desktop and mobile also accept repeated `--exact-file` arguments with declared,
repository-relative POSIX paths, useful when filenames repeat across folders:

```sh
python3 dev.py test desktop --exact-file Python/tests/tooling/test_regression_runner.py
python3 dev.py test mobile --exact-file mobile_build/tests/documents/test_editor_picker.py
```

Do not combine exact files with the positional filename/glob. Missing, duplicate,
escaping or wrong-suite paths fail before execution. `test-owner` resolves and
deduplicates its selected files once, filters them by profile and invokes one
runner per selected environment. Files with no selected stages are omitted; an
entirely empty owner selection is an error. Each file/stage still gets a fresh
child process. Use `--dry-run` to inspect the suite and exact paths.

Lint covers `dev.py`, `Python`, `mobile_build`, `Scripts`, `logistics_build` and `.github/scripts`, matching CI's scope.
The Ruff configuration retains its default environment/cache exclusions and
explicitly excludes mobile build, payload, log, deployment-workspace and downloaded
toolchain trees, plus the external feature link. New, untracked application and
test source is still checked; lint selection does not depend on the Git index.

For **mobile host tests**, set up the separate environment. Setup installs
the locked host tools, including Briefcase. Dummy-backend checks require no
native SDK:

```sh
# macOS / Linux; use py -3.12 and mobile_build/.venv/Scripts/python.exe on Windows
python3 dev.py setup mobile
python3 dev.py test mobile test_editor_picker.py
```

The helper uses root `.venv` for desktop/lint and `mobile_build/.venv` for mobile,
including Windows `Scripts/python.exe` paths. For a differently located environment,
append `--python /path/to/python`. Append `--dry-run` to inspect the command without
running it. Mobile tests use `TOGA_BACKEND=toga_dummy`; desktop tests use offscreen
Qt. These checks do not certify native appearance or interactions. See the
[mobile handbook](../build-release/mobile-handbook.md) when you need an actual device build.

### Parallel regressions and shared host budgets

Direct commands default to one isolated file-stage process at a time. For the
reviewed desktop groups on macOS, choose 1, 2, 4 or 8 workers:

```sh
python3 dev.py test desktop 'test_git*.py' --workers 4
python3 dev.py test shared 'test_markdown*.py' --workers 4
```

The direct `Python/tests/run_regressions.py` entry point also accepts
`--isolate-modules --workers 4`. The runner requires Qt's offscreen backend.
The shared developer command keeps its separate Toga replay serial.
Only the 85 explicitly listed files in `Python/tests/parallel_regressions.py`
can overlap: 19 Git, 17 notes/editor, and 49 shared browser/index/Markdown files.
Their fixture files, SQLite databases, preferences, Qt applications and default
storage are private to each process. New and unreviewed files remain exclusive:
they wait for active work to finish and retain the original serial child path.
Changes to an admitted file's resource use require another overlap and cleanup audit.
No stages overlap. Fast mode still gates later work on smoke; fail-fast stops
new admissions while already running files finish.

JSON and JUnit retain deterministic source-plan ordering, case outcomes and file
identity. Unstarted files include their statically classified cases; their runtime
discovery is not claimed. For concurrent children, SIGINT/SIGTERM first asks
the existing command supervisors to cancel and retire their detached helpers.
Up to five seconds is reserved for that cleanup, followed by the manager's
process-group cleanup. The 300-second file execution deadline is unchanged.
Child temporary storage is inside the parent's removable file scope. An already
running exclusive file keeps its original deadline and termination behavior.

This option is limited to reviewed macOS offscreen tests. Toga dummy/mobile host,
WebEngine, real media playback, encrypted-provider integration, native windows,
simulators, devices and Go bridge tests remain exclusive. With a Manager
that supplies test worker reservations, local host test phases share its
per-platform and computer-wide ceilings. App settings defaults to at most four per platform
and half the logical CPUs, capped at eight, across this computer. The audited
Logistics runner uses the largest tested pool (1/2/4/8) within its reservation.
Other host runners reserve one; native/device/build owners retain their existing
policies. Manager checks captured source capability before enabling pools, so older
snapshots keep their captured allowlist and older pinned managers retain serial
behavior. File filters and subtree selections only reserve a pool when they
include an admitted file. Audited phases allow
six seconds for supervised cancellation before outer process-group escalation.

Use Manager when several platform workflows run together: its resource slots
coordinate separate Manager processes too. Explicit direct `--workers` commands
are manual pools and do not acquire those reservations. The host budget limits
participating test processes, not all compiler/helper threads on the machine.
Do not infer full-platform or release coverage from this selected group.

`run_platform_checks.py` uses the same Manager reservations for its shared and
Logistics phases. The GitHub platform workflow explicitly configures at most two
workers on a GitHub-hosted macOS runner, capped by its reported CPU count. The
step is guarded by the documented
[`runner.environment` context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#runner-context);
self-hosted runners retain their existing Manager settings. Windows and Linux
file execution stays serial. This changes scheduling only: structure, smoke,
remaining regressions, native startup and compression parity keep their existing
gates and order. Hosted workflow execution still needs its normal CI run.

The implementation at `50c488f0`, based on Logistics `805ccc7c` and unchanged
commonUtils `cee7537`, matched all 152 Git cases plus 96 smoke cases, all 33
file-stage outcomes and all Git JUnit case/file identities. Including structure
preflight and both smoke gates, its quiet serial/two-worker pair took
**160.98 / 85.02 seconds**, saving **75.97 seconds (47.2%)**. Gate costs were
6.19 / 6.22 seconds; the one-time 6.09-second source/environment preparation was
measured separately. Sampled aggregate process-tree RSS rose from 252.7 to
385.9 MiB. Trial CPU was 148.23 / 120.88 seconds, including the measurement
driver and its process sampling; this is not a pure application CPU comparison.
RSS was sampled approximately every 100 ms and can count shared pages twice.

The earlier quiet prototype pair took 158.78 / 84.46 seconds, with a reverse
parallel repeat of 84.28 seconds. Three four-file repetitions had medians of
48.68 / 28.69 seconds. A serial repetition that overlapped compiler work is
excluded. These selected-slice measurements are separate from Brief 09's
12.31-second matched full-macOS improvement; they are not a measured full-suite
speedup.

The expanded experiment on a 16-core M3 Max with 64 GiB memory used the same
frozen Logistics/commonUtils source and Manager base `922d58d4`. All nine selected
runs matched 248 case outcomes, 33 file-stage outcomes and 152 JUnit identities.
Structure and both smoke gates are included; source/environment setup is excluded.

| Workers | Quiet single-phase wall time | Sampled aggregate RSS |
| --- | --- | --- |
| 2 | 95.03 s | 396.9 MiB |
| 4 | 50.45 s | 641.2 MiB |
| 8 | 35.33 s | 1110.9 MiB |

Two competing platform-host proxies, each running these macOS Qt tests, used the
same eight-slot host budget. Four plus four completed together in 52.72 seconds;
two eight-worker phases queued and took 73.86 seconds overall. The earlier 4+4
run passed in 53.21 seconds while Xcode/compiler activity was observed. These
proxies establish shared-host scheduling and case parity, not native Android/iOS
acceptance. Eight-worker individual repeats took 39.15 and 33.87 seconds.

Keep four as the default for mixed platform work and allow eight for an audited
single-platform workload. Stop at eight: the measured gains do not justify a
larger pool or dynamic nested scheduling yet. Whole-phase reservations deliberately
retain spare slots during exclusive files. Real cancellation fixtures cover eight
active file workers and their detached command helpers; admission fixtures cover
multiple Manager processes, stale settings, cancelled waits and idle capacity
changes. Unreviewed suites must pass their own resource and cleanup audit before
joining the allowlist.

The next expansion, based on Logistics `d53a015` and commonUtils `d905628`,
adds 66 reviewed files: 17 notes/editor, 16 shared browser, 18 shared index and
15 shared Markdown files. The measured slice retained all 67 candidate files,
including `browser/test_entry_browser.py`, which stays exclusive after its
filter-publication assertion failed during the first overlap attempt. Its cases
were retained in every comparison. WebEngine, real media and encrypted-provider
integration files were not admitted.

The serial baseline also exposed an inherited feature-toggle assertion that
incorrectly expected built-in browser action providers to disappear. The existing
test-only correction `4a37c98` was applied over `d905628` as `dbb002b` before all
accepted measurements. No production shared-library behavior changed.

Six accepted local runs preserved ordered JSON and JUnit identities and outcomes:
742 cases across the selected groups and both full desktop smoke gates, with
741 passes and the same one Windows-drive-only skip. Structure validation ran
before the smoke gates. Clone/environment preparation is excluded below.

| Workers | Passing runs | Elapsed time | Sampled aggregate peak RSS |
| --- | --- | --- | --- |
| 1 | 2 | 124.67–165.28 s | 455.9–515.0 MiB |
| 2 | 1 | 72.83 s | 636.1 MiB |
| 4 | 2 | 50.37–69.79 s | 831.5–835.0 MiB |
| 8 | 1 | 42.24 s | 1241.9 MiB |

The one/two/four-worker runs used real Manager host/platform admission. The
eight-worker alternative held all eight real host slots around an isolated
eight-worker settings profile; it did not change the contributor's shared
four/eight settings. These are selected-slice observations on shared local
hardware, not full-platform or hosted CI timings. Keep four for mixed platform
work, two for the initial hosted macOS rollout, and eight as the tested optional
ceiling. No extra scheduler or nested worker pool was added.

### Execution stages and failure policy

Every declared test source has one default from `commonUtils.testing.stages.TestStage`:

```python
from commonUtils.testing.stages import TestStage, stage

TEST_STAGE = TestStage.REGRESSION

@stage(TestStage.SMOKE)
class StartupTests(unittest.TestCase):
    ...
```

Use `SMOKE` for a small, deterministic startup/core-contract gate, `REGRESSION`
for ordinary behavioral coverage, and `EXTENDED` for expensive performance, soak,
parity or comprehensive native journeys. Stage describes execution scope, not bug
severity. A file default labels every case unless its class or method uses
`@stage(TestStage.MEMBER)`; method overrides take precedence. Keep tests independent;
ordering must never supply state needed by another test. Standalone embedded
runtimes and non-Python sources use `# TEST_STAGE = TestStage.SMOKE` or the language's
`//` comment form, avoiding a runtime dependency just for metadata. Whole native
journeys keep one stage; their existing ordered case inventory remains authoritative.

`test-structure.json` declares the owned test roots, including commonUtils, release
tooling, runtime drivers and bridge tests. `python3 dev.py test-structure` validates
all declarations without importing tests. Missing, duplicate or invalid labels,
escaping/linked sources and empty declared roots fail before execution. New files
matching the declared patterns are checked automatically. Add new test locations
to this manifest. `--inventory` prints the full source inventory as JSON; individual
runner inventories are also available with `dev.py test desktop --inventory`.
Static inventories describe locally declared/inherited methods; runtime discovery
still determines actual unittest IDs, including imported bases and generated cases.
Host `--inventory` applies the same filename/include and profile/stage selection
as execution without importing tests. Its `stage` is the module default; `stages`
lists the selected stages, and `cases` contains only selected classified methods.

```sh
python3 dev.py test desktop --profile smoke --mode fast
python3 dev.py test mobile --profile daily
python3 dev.py test shared --profile full
python3 dev.py test bridge --profile smoke --mode fast
python3 dev.py test-owner document-services --profile daily
```

Profiles are cumulative: `smoke` selects SMOKE, `daily` adds REGRESSION, `full`
adds EXTENDED. The default is full diagnostic coverage. Files run in fresh
processes, ordered by stage then path; methods use stage then unittest ID. A mixed
file can run once per selected stage, with fresh fixtures each time. The underlying
runner also accepts repeated `--stage` for an exact selection. Native acceptance
entry points retain their complete platform-specific journeys; choosing a host
profile does not narrow release acceptance or certify a device.

Diagnostic mode continues independent checks after failures. Fast mode completes
the selected smoke gate and leaves later stages unrun if smoke fails; discovery
failures also stop that fast run. `--fail-fast` additionally stops at the first
failure inside a file and prevents later files/groups from starting. Existing
cleanup still runs. Failures never count as successful coverage. JSON records the
selection, stage, mode, failures and unrun work; JUnit marks unrun work skipped with
its reason. `coverage_complete` means all work in the selected scope ran, even if
assertions failed; it does not mean a smoke profile covered the full suite.

For an owner spanning environments, this stage-first gate applies within each
environment. Fast mode stops later environments after a failed environment;
diagnostic mode continues them. Grouping does not create a persistent test process
or a preflight cache. A skipped setup fixture leaves its planned methods explicitly
`not_run`, never passed. `python3 dev.py test bridge --profile smoke --inventory`
uses the execution profile to list bridge sources without starting Go.

Pass `--timings path/to/previous.json` to read an existing report and order files
by successful duration within a stage. This is an input path, not a destination
for the new report. It requires the same root, interpreter, platform and Qt/Toga
backend environment; normal ordering is deterministic without timing history.
New reports are saved automatically under `test-results/test-timings/`. Bridge Go
tests run by stage with native Go fail-fast support; they currently report outcomes
and gated stages on the console rather than the Python JSON timing schema.

Use `python3 dev.py test <suite> [filename] --timings REPORT.json` only for a
single Python test leg, with an existing matching report. Shared selections that include
both Qt and Toga currently forward the same input path to both legs, whose roots,
interpreters and backends differ. Use default ordering for that combined command,
or run each owning isolated-runner command with its own matching report.

### Focused resource, Git and tooling checks

LocalCrypt workflows are split across `Python/tests/resources/test_local_crypt*.py`;
real transfer cases keep their transfer setup, while reader/editor fixtures copy
independent ciphertext into a published mapping. Cached fixture assets contain
only immutable synthetic bytes; credentials, providers and mutable repositories
remain independent per case. Git UI workflows use `test_git_ui*.py` with copied
repository templates; watcher tests live in `test_git_watchers.py`.

`Python/tests/local_crypt_fixture.py:require_pinned_rclone()` skips a missing pinned
binary for optional local coverage. Any nonempty `LOGISTICS_REQUIRE_LOCALCRYPT_TESTS`
makes that prerequisite failure an error, so required coverage cannot succeed via
a skip. The fixture never downloads software; the existing managed desktop
prerequisite setup provisions it. Notebook routing cases that do not use rclone
remain runnable without that binary.

The daily profile keeps the standard encrypted rename and batching modes. The
alternate encryption-mode matrices and exhaustive documentation-viewer sweeps use
`EXTENDED`; run `--profile full` to include them. Packaged startup keeps empty
and populated storage in daily coverage; its Help-navigation journey is extended. The small smoke subset of the
execution-policy tests checks stage gating, classification rejection and missing
evidence. Other runner scenarios remain regression coverage.

Run `python3 dev.py architecture` for the live-tree boundary gate. Architecture
unit tests exercise checker fixtures and policy declarations without repeating
that complete scan. Completed cases and fixture failures are saved incrementally, so an
isolated-file timeout retains earlier outcomes while marking coverage incomplete.

### Shared-library test matrix

Use the same entry point for commonUtils:

```sh
python3 dev.py test shared
python3 dev.py test shared test_streams.py
python3 dev.py test shared 'test_native*browser*.py' --dry-run
```

The full command runs the Qt/portable shared suite in `.venv`, then replays
`tests/native/test_native*.py` in `mobile_build/.venv` with Toga dummy. Each file
still runs in an isolated process with disposable storage. Native replay uses
the intersection of that native filename family and the requested filename/glob;
a portable-only selection needs no mobile environment. The Qt host-admission
fixture `test_qt_mobile_host.py` stays in the Qt leg. The two legs overlap and
their case counts are not distinct coverage to add together.

For custom environments, `--python PATH` selects the shared Qt interpreter and
`--native-python PATH` selects its native interpreter. Both selected interpreter
paths are checked before starting either leg. Missing PySide6, Toga or Toga dummy
fails its required leg before discovery, rather than silently accepting skipped
toolkit tests. Both legs run after a test failure; the command preserves the
first nonzero result. No environment is installed or modified by this command.
Use the existing desktop/mobile setup commands if either environment is absent.

Native filesystem notification access is required for real watcher tests.
Localhost fixture servers and Qt WebEngine also need the host's socket and
process capabilities. A restricted sandbox can cause permission failures or
watcher timeouts; recheck with those capabilities and disposable profiles before
classifying them as source regressions. Do not remove watcher assertions, extend
timeouts or turn unavailable required dependencies into successful skips.
Platform-specific Windows/case-sensitive-filesystem skips remain explicit, and
Toga dummy results do not certify device appearance or native interactions.

The regression runner isolates application storage and cache directories. When
using Playwright's downloaded browsers for DOM tests, set
`PLAYWRIGHT_BROWSERS_PATH` to the same explicit directory during browser installation
and test execution. The platform workflow sets this path during installation and
persists it through `GITHUB_ENV` so later fixture subprocesses can find browser
tooling after application caches are isolated.

Full local mobile release journeys require browser tooling before their host tests.
In the build manager's project settings, select **Node**, **Node modules** (the
existing `node_modules` directory containing Playwright), and optionally **Chrome**
(an existing Chromium-compatible executable). Leaving Chrome empty selects
Playwright's installed Chromium. Node can also be discovered on `PATH`.
`LOGISTICS_NODE`, `NODE_PATH` and `LOGISTICS_CHROME` remain supported environment
inputs to the same settings owner. These are machine-local settings; do not add
personal executable paths to tracked project configuration.

Preparation captures the selected tool paths, including the resolved Playwright
browser path, in the plan environment and identity. The release prerequisite
checks existing executable files and Node/Playwright metadata before host tests;
it never installs packages, downloads browsers or launches a browser. The DOM
cases themselves validate browser behavior. Missing tooling blocks a full mobile
release with setup guidance. Ordinary developer suites retain their optional
browser skips; saving these settings does not change their test policy.

The build manager's full local mobile validation runs the existing `dev.py`
architecture, toolchain, hygiene and lint commands before host suites and native
builds. These are the same source checks required by the hosted platform workflow;
unit tests for the checkers do not substitute for checking the selected source.
They run in the captured Git source checkout with the selected desktop Python.
A failed source check blocks dependent validation and packaging while owned cleanup
retains its normal completion behavior. Focused developer commands keep their
existing scope.

### Test timing and maintenance

#### Shared native rotation inventory

`mobile_build/native_tests/tests/logisticsmobile/rotation_screens.py` owns the
31 stable screen IDs, visible titles and explicit synthetic setup journeys.
`rotation_checks.py` owns route/content retention and native control/safe-area
assertions. A full default sweep visits each screen for two cycles of portrait →
landscape-left → portrait → landscape-right → portrait: 310 observations when all
steps execute successfully. Registration alone does not establish a native pass.

Test callers can pass an iterable of `panels` IDs to `exercise_rotation()`.
`select_screens()` rejects empty or unknown selections before setup; only the
selected setup groups run, and `visit_screens()` requires every selected screen
exactly once in inventory order. Setup remains explicit for readers, provider
sessions, nested folders, Notes Library and asynchronous help rendering.

Reports separate `rotation_samples` (executed observations) from
`rotation_inventory` (registered screens, selection and gaps). The latter compares
the inventory with `mobile.navigation.DESTINATION_ITEMS` and
`mobile.settings.categories.CATEGORIES`. The five top-level destinations are
registered. Settings gaps are **Features, Camera, Read aloud, Markdown, EPUB,
Books & Comics, LM Chat and Reset**. New catalog entries appear as gaps until a
scenario is added. Nested routes and format-specific screens outside those
catalogs still need an explicit coverage review; PDF, video, notebook and other
specialized probes keep their own fixtures and assertions.

Use `python3 dev.py test mobile test_rotation_screen_inventory.py` for inventory,
selection and synthetic journey contracts, plus
`python3 dev.py test mobile 'test_native_rotation*.py'` for rotation helper checks.
These host checks do not validate OS rotation, rendering, native gestures or
safe-area geometry. The [native platform workflow](../build-release/mobile-handbook.md) must run
the maintained scenarios on the affected platform for that acceptance.

#### Timing reports and fixtures

Generic host/native test mechanisms and defaults live in `commonUtils.testing`;
their API contracts belong to commonUtils' own testing guide. The Logistics
runner keeps its isolated-file timeout and progress interval in
`Python/tests/runner_settings.py`; shared helpers do not own runner policy. Suite
selection stays in [build-tests.json](../../../build-tests.json), with developer
routing through `dev.py`; these are different responsibilities.

Logistics mobile host fixtures live in `mobile_build/tests/support/`. `app.py`
provides `mobile_app()` for an explicit context and `create_app(case)` for a
unittest cleanup scope. Both restore the previous storage override, close the
window and drain constructor-allocated loops before deleting owned temporary files,
including startup failures. Nested contexts restore the enclosing app and default
loop. Cleanup failures retain owned roots under ignored `test-results/mobile-fixtures/`
and name the retained path in the error. These contexts require synchronous tests.
Pass an existing root only when its owner keeps it alive until app cleanup; that
owner must also retain it if draining fails.
Existing explicit app fixtures use `commonUtils.testing.event_loop.close_loop()`
before removing their root. A bare `loop.close()` leaves default-executor
filesystem workers alive. Inside a temporary-directory context, use `mobile_app()`
there too; a later unittest cleanup runs after that directory has already exited.
`mirror.py`, `readers.py`, `pdf.py`, `localcrypt.py` and `notebooks.py` own backend fakes and
document fixtures reused across test files. Import them directly rather than
importing another `test_*.py` module for these helpers.

Native scenario budgets shared by Logistics checks live in
`mobile_build/native_tests/tests/logisticsmobile/settings.py`; deliberate soak
durations and feature-specific readiness checks stay beside their scenario.
`rotation_checks.py` adds Logistics timing, route/content retention and safe-area
assertions around the shared native rotation mechanism. Repeated native startup
callbacks use `start_native_check` so activity recreation cannot duplicate a run.
Shared screenshot mechanics remain behind the Logistics timing wrapper.
Compact reader clearance is measured against the actual native title, including
its top and content gaps. Hardware, side-rail and fixed-control bounds remain
independent checks; other panels retain the standard navigation inset.

State the full viewport when testing adaptive layout. A patched width alone does
not specify portrait/landscape or whether the window is compact; the workspace
navigation fixture fixes its full window height while varying width. Keyboard
content-height changes remain separate observations. Preserve real content and
route assertions when extracting device mechanics; a helper acknowledging a
rotation does not establish that a reader finished reflowing.

Every host regression run through `dev.py test` or `dev.py test-owner` saves a
timestamped JSON report under ignored `test-results/test-timings/` and prints
the ten slowest tests and files. The runner also accepts `--report PATH` when
invoked directly. Desktop, mobile and shared matrix legs produce separate reports.
Grouped `test-owner` runs likewise produce one report per selected environment.
Direct `python -m unittest` invocations bypass this reporting.

Reports include UTC start/end timestamps, elapsed seconds, test IDs and outcomes,
suite selection, interpreter and host platform. Individual test durations include
`setUp`, the test body, `tearDown` and test cleanups. File durations include process
startup, imports/discovery, class/module fixtures and shutdown. The suite total
also includes runner overhead. Class/module fixture failures appear as synthetic
events with zero test duration; their time belongs to the file total. Failed
subtests mark their parent test as failed. Skips and expected failures remain
distinct from passes.

The parent checkpoints the report after each isolated file. Crashes and the
existing 300-second file timeout retain file elapsed time and exit status even
when the child cannot finish a test report. `complete` means the runner finished,
not that tests passed; inspect `exit_code` and outcomes as well. Valid completed
records can survive a malformed or incomplete child report. The parent validates
evidence against the launch/source context and the runtime-discovered case IDs
saved before execution, rather than treating static declarations as actual cases.
Missing, mismatched or unexplained omitted evidence fails that child even if its
process exits zero; diagnostic mode continues independent files. An interrupted
run retains completed files, but its active file may be absent.

Compare repeated runs with the same selection, interpreter and host before
treating a timing difference as a regression. Review slow files for repeated
setup, polling/sleeps and redundant expensive integration checks. Runtime alone
does not justify removing a test. Keep protection for data loss, encryption,
save/reopen and recovery paths; consolidate duplicate assertions only when the
behavior remains covered. Review critical workflows for real outcomes, failure
paths and platform checks even if their existing unit tests are fast. Timing
reports do not measure coverage or prove a test's value.

For a speedup, run the same focused selection before and after with the same
interpreter, backend and socket/process permissions. Compare whole-file durations
in `modules`, then check that every original test ID still ran with the same
outcome. Include any added coverage in the after result. A faster run caused by
errors or extra skips is not an improvement. Keep both reports in ignored evidence
storage and distinguish a focused comparison from a full-suite benchmark.

Prefer removing repeated fixture work before narrowing coverage. The developer
command and native-report tests stub repeated full-tree scans, with small real
preflight fixtures protecting acceptance and rejection. LM UI integration tests
use real local HTTP requests and Qt events with short server shutdown polling.
HTTP reads have a fixture timeout, and shutdown joins request workers as well as
the listener thread. Loopback server setup avoids reverse DNS.
Widget-only cases use a separate fixture that rejects HTTP starts. Inactivity
checks establish a partial reply, then use a heartbeat to verify the transport
rearms the short deadline; mobile send
checks hold the fixture stream until the next draft is entered. Deferred-save
checks wait for queued writes with a bounded deadline and retire them before
removing storage. Mobile chat app fixtures restore enclosing storage/app/loop
state even after setup failures and dispose their conversation menus. See
[fixture guidance](adding-tests.md).

Help-viewer tests build their expected page inventory once per unchanged wiki
scope while still opening every feature guide and exercising every folder's
Up/history navigation in real widgets. Git UI tests copy a configured empty repository into each case's private
directory. Refs, indexes, configuration and working files remain independent;
backend tests still exercise repository initialization directly. Dedicated checks
cover cross-wiki history and prove per-case Git mutations leave the template
unchanged. Managed Qt temporary directories drain owned work before deleting files.

## Make your first change

Follow the [contributor walkthrough](../setup/getting-started.md) for the full first-change
sequence. If your change adds or moves a mobile payload module, update its
`mobile_sources.json` and run `python3 dev.py test desktop test_mobile_packaging.py`.
Use [mobile validation](../build-release/mobile-handbook.md) for interaction on the affected platform.

## Testing

### Desktop test folders

`Python/tests/` groups regression contracts by subject. Filename selection through
`dev.py` and the isolated runner searches these folders recursively; keep that
selection when a guide does not need to name an individual test class.

| Folder | Responsibility |
| --- | --- |
| `application/` | Startup, feature registration, preferences and host shell |
| `files/` | Folder Hub, file browser, indexing and Bulk Rename |
| `readers/` | Books, PDF and shared document reading workflows |
| `editing/` | Text editing, notes and resource pickers |
| `resources/` | Credentials, encrypted storage, remote sessions and transfers |
| `integrations/` | External service and application adapters |
| `comics/` | Comic archives, compression, library and reading state |
| `images/` | Image conversion, color, staging and folder tools |
| `archives/` | Archive browsing, authentication and workspace presentation |
| `version_control/` | Git backend and UI workflows |
| `chat/` | LM conversations, generation, streaming and storage adapters |
| `ide/` | IDE layout, browser, navigation and search |
| `blender/` | Blender integration, library, metadata and operation UI |
| `calibre/` | Calibre library launch and transactional device exports |
| `notebooks/` | Notebook storage, drawing, import, export and recovery |
| `tooling/` | Build, documentation, architecture and runner contracts |

Some tests with `test_mobile_*.py` filenames run in the desktop host environment.
Look in the subject folder for cases such as mobile chat presentation, comic
batching and speech timing. The portable runtime testbed uses seven flat test
modules and two fixtures from the root of `Python/tests/`. See the explicit
list in [mobile staging](../../../mobile_build/tools.py) and its consumer in
[runtime smoke](../../../Python/mobile/smoke.py) before relocating those files.
Desktop cross-group imports name `tests.<owner>` explicitly. Shared contracts use
`commonUtils.tests.<owner>`, with the owner map in
[commonUtils](../../../Python/commonUtils/docs/development/reference/tests/tests.md).
The small package initializers enable recursive standard `unittest discover`
and contain no setup or runtime registration.

### Find the tests for your change

Choose by the behavior under test and the environment it needs. Run these
examples from the repository root with the corresponding [host setup](#run-everyday-checks).
On Windows, use `py` in place of `python3`.

| What you need | Command or guide |
| --- | --- |
| Find a feature's tests | `python3 dev.py owners`, then `python3 dev.py test-owner books --dry-run`. Replace `books` with the owner ID and remove `--dry-run` to run the selection. |
| Check one desktop or portable behavior | `python3 dev.py test desktop test_feature_registry.py` uses the root desktop environment. |
| Check one mobile host behavior | `python3 dev.py test mobile --exact-file mobile_build/tests/documents/test_editor_picker.py` uses the mobile environment and dummy Toga backend. |
| Check a commonUtils contract | `python3 dev.py test shared 'test_native*.py' --dry-run` previews the shared matrix. See [shared-library test setup](#shared-library-test-matrix). |
| Check native interaction, platform gates or a delivery plan | Use the [mobile handbook](../build-release/mobile-handbook.md), [platform checks](platform-checks.md) or [Build Manager plan walkthrough](../build-release/build-manager-journeys.md#trace-a-validation-plan). |

For a filename that occurs in multiple desktop or mobile directories, select a
repository-relative `--exact-file`. For a check that selects no cases, confirm
the suite and filename first, then check whether the selected
[execution profile](#execution-stages-and-failure-policy) includes the case's stage.

`Scripts/ownership.json` owns these source, guide, manifest and test associations;
update it when moving an owner or renaming tests. Archive, reading, chat, provider
and storage selections include their specialist workflow suites; overlapping
filename patterns execute each selected file once. Unknown suite names and
patterns matching no files are errors. Small integrations with no
specialist suite use registry checks as their starting group; that is not proof
of external application behavior. Review responsibility follows the source owner;
the map does not invent individual maintainer assignments.

| Owner | Start with |
| --- | --- |
| Feature infrastructure | `Python/tests/application/test_feature_registry.py`, `test_feature_preferences.py`, `test_settings_page.py` |
| Desktop shell/documents | `Python/tests/application/test_main_window_navigation.py`, `test_document_hosting.py`, `test_notes_library_hosting.py`, `test_reader_host_integration.py`, `Python/tests/application/test_document_workspace.py` |
| LM conversation lifecycle and presentation | `Python/tests/chat/test_lm_session.py`, `test_lm_ui.py`, `test_lm_appearance.py` |
| Git history, search, preview and job ownership | `Python/tests/version_control/test_git_ui*.py`, `test_git_watchers.py`, `test_git_preferences.py`, `test_git_repository_tabs.py`, `test_git_hunk_layout.py` |
| Blender presentation and operation lifecycle | `Python/tests/blender/test_blender_page.py`, `test_blender_settings.py`, `test_blender_library.py` |
| Bulk Rename widget and host | `Python/tests/files/test_bulk_rename_ui.py`, `Python/tests/files/test_bulk_rename_host.py` |
| Notebook storage and drawing | `Python/tests/notebooks/test_notebooks.py`, `mobile_build/tests/documents/test_notebook_storage.py`, `mobile_build/tests/documents/test_notebook_input_lifecycle.py` |
| Mobile Open/Save As and file management | `mobile_build/tests/documents/test_editor_picker.py`, `mobile_build/tests/storage/test_files_ui.py`, `mobile_build/tests/documents/test_private_sessions.py` |
| Mobile saved imports and window ownership | `mobile_build/tests/documents/test_saved_files.py`, `mobile_build/tests/workspace/test_window_owners.py`, `mobile_build/tests/workspace/test_workspace_ui.py` |
| Mobile source selection and import isolation | `Python/tests/test_mobile_packaging.py`, `test_mobile_portability.py`, `mobile_build/tests/tooling/test_packaged_startup.py` |

For a change to folder image compression, start with the
[Images developer guide](../../features/images/development/development.md#compression-regression-coverage)
and follow `compress_folders` in `Python/features/images/actions.py`. Inspect
the owner selection, then run the file that exercises cancellation and recovery
from encoder failure with synthetic images:

```sh
python3 dev.py test-owner images --dry-run
python3 dev.py test desktop --exact-file Python/tests/images/test_image_folder_tool.py
```

The [mobile owner map](../architecture/mobile-runtime.md) explains controller
and packaging boundaries. For focused runs, use `dev.py test desktop <filename>` or
`dev.py test mobile <filename>`. Filename selectors remain valid after grouping. Isolated mode also supports nested directories,
running each file from its own parent in a separate process. Duplicate filenames
in different directories cannot shadow each other. Each isolated child loads its
exact file, so packaged child directories cannot be rediscovered in the parent run. Empty test modules fail. The runner puts the selected suite first
on the import path so mobile and desktop files with the same test-module name
cannot shadow each other. Use the separate mobile environment
and [host validation commands](../build-release/mobile-launchers.md#host-validation) for Toga
widget tests. Loopback fixtures need permission to bind localhost; native file
watchers also need functioning OS notification access.

Run the complete desktop suite from the repository root with
`python3 dev.py test desktop` (`py dev.py test desktop` on Windows).
For the complete mobile host suite, use `python3 dev.py test mobile`.

For both repositories' suites and the historical comic compression comparison,
use the same project interpreter:

```sh
.venv/bin/python Python/tests/run_platform_checks.py
```

On Windows, use `.venv/Scripts/python.exe Python/tests/run_platform_checks.py`.
The runner configures the import path and headless Qt automatically. See
[cross-platform testing](platform-checks.md) for CI and platform details and
[feature conventions](../architecture/features.md) for extension points.

Tests cover application startup, contributions, local fixtures and simulated
failures. Desktop interaction, real remote transfers/mounts, external applications
and installed drivers require separate validation.

## Correctness checks and test ownership

Normal launchers synchronize runtime dependencies only. Use the environment setup
above to install developer tools, then run `python3 dev.py lint` (`py` on Windows).
The lint policy checks syntax/correctness (`E9`, `F63`, `F7`, `F82`) and reviewed
unused redefinitions (`F811`) without forcing a formatting rewrite. `F401` and
`F841` remain optional review aids: package/module re-exports, format-registration
imports, test mocks, native type imports and retained lifetime handles need owner
review before removal. An unused assignment may still evaluate a required operation;
removing its evaluation can change behavior. In particular, downloader sync names
are explicit same-name re-exports used by its UI, and the legacy aviation
`print_info` method's lack of output is preserved rather than silently fixed during
lint cleanup. Do not apply repository-wide unused-import/local autofixes. `commonUtils.tests.qt_test_case.QtTestCase` gives GUI tests ownership of
new windows: it requests worker shutdown, drains deferred deletion and deletes
windows before the next test. Use its `temporary_directory()` for GUI filesystem
fixtures so windows and watchers are destroyed before their directories are
removed, including on assertion failures. Register fixture-specific cleanup after
creating the directory. Use `wait_until()` for condition-based Qt waits with
operation-specific timeout messages. Tests must not depend on windows retained by
other tests. See the [shared test guide](../../../Python/commonUtils/docs/development/reference/tests/tests.md)
for lifecycle details.

## CI, release gates and advanced validation

The Windows platform runner starts with one native Qt startup smoke using the
`windows` platform plugin. It constructs the real public main window, applies
theme/font settings, runs its event loop and closes it under isolated preferences
and caches. Feature initialization hooks are excluded. Fatal startup exits report
the Windows exception code and Python faulthandler trace before running headless
regressions. Cleanup uses the shared Qt fixture lifecycle. Mixed-DPI monitor
crossings additionally need physical Windows hardware validation; synthetic
native-message tests cover the preservation policy on every CI host.
The startup smoke also checks the rendered application font against the shared
reference size. Shared styling tests measure text at 72, 96 and 120 font DPI and
verify that editor zoom persists the reference value. Launch-card tests exercise
the macOS conversion at maximum size and several window widths. Offscreen tests
alone use 96 DPI even on macOS, so native macOS font measurements remain relevant.
Native startup logs include Git history font, row and header metrics to distinguish
list density from screen scaling. Filesystem-refresh tests check that activity
settles without index writes; native watcher notification counts are not portable.

Platform checks also run on main pushes and launcher changes.

Release packaging stamps `.app-version.json` with the tag, packaged commit and
commit time, and includes its hash in the installed-file manifest. The desktop
launch label reads this managed file in ZIP installations and reads Git locally
in checkouts. Commit time identifies the source revision, rather than a variable
packaging timestamp. No release version file needs a manual edit.

The release workflow
calls those checks before packaging, so a tag cannot bypass failing application
regressions. Every release also calls the native mobile build and document runtime
workflows with both targets, using workflow files and source from the same release
commit. Packaging requires macOS, Windows and Linux desktop checks (including
Fedora and archive parity), Android and iOS native builds, and both mobile runtime
checks to succeed. Failed, cancelled or skipped prerequisites block packaging and
publication. A manual Source release run exercises these gates without publishing;
tag pushes publish only after they pass. Mobile gates cover the prototype and
portable core, not unported desktop features or physical-device interactions.
Standalone branch checks cannot cancel a release's mobile jobs, and tag runs
retain their validation.
Native app UI runs allow 30 minutes per iOS device, including Briefcase's cold
simulator startup and installation, and 40 minutes on Android. Hosted Android
software rendering has reached the dark-theme audit after all 32 core cases at
the former 25-minute deadline; the complete run also checks light appearance and
native Back. Each native build job has a 60-minute overall budget. The large 256 MiB
LocalCrypt seeding fixture allows four minutes for review revalidation and
transfer; smaller reviews retain their 30-second budget. Complete native case
reports and exact source identity are required before a gate can pass.
Unhandled handler, task and callback errors in the native run log also fail the
gate, even when every declared case passed. This applies to stdout and fresh
iOS simulator-cache reports, so a successful result cannot hide those errors.
The iOS host retains each fresh cache result as `ios-native-ui-cached.json` before
validation, along with its fresh `ios-native-ui-error.txt` traceback. These are
diagnostics, not passing evidence. Failure diagnostics target the device recorded
for the current run, so an iPad failure cannot be hidden behind an earlier iPhone
report or collected from the wrong simulator.
A complete native stdout report passes the same case and source validation before
any simulator-container lookup. This avoids failing a completed native suite when
CoreSimulator becomes unresponsive after app exit. Missing stdout reports still
require a fresh, complete cache result; a structured failed report cannot fall
back to a successful cache.
Native WebView probes retry only the transient `WKErrorDomain Code=5` evaluation
error during document replacement. A successful string result must contain the
expected replacement text and exclude retired private content; repeated errors,
other failures and non-string results still fail the bounded check.
An iOS WebView still waiting after 15 seconds signals the running test app's PID
and native loading state. The host verifies the process executable before taking
one bounded three-second thread sample for that PID. Sampling stays inside the
existing render deadline, never retries navigation, and cannot turn a stalled
view into passing evidence. Samples remain in ignored test logs.

New pushes and PR updates cancel superseded checks for the same branch/PR;
tag releases and manual runs retain their validation. Windows platform checks
collect browser screenshot diagnostics alongside their logs. The separate browser
diagnostic workflow remains available manually and does not repeat on every push.
Publish a commonUtils commit before pushing a Logistics commit that references it;
an unavailable submodule revision fails checkout before any test runs.

The platform runner isolates both shared and Logistics test modules in separate
processes to prevent native Qt state from leaking between suites. Each regression
process uses a private temporary directory index and shared storage root. During
discovery and execution, `Path.home()` and platform config/cache environment
variables point into disposable test storage, so default preferences and shared
workspaces do not use the contributor's live data. Helper subprocesses inherit
the private storage/config environment; tests spawning other processes must still
supply explicit private fixtures for APIs that resolve the OS home independently.
Both single-process and isolated-module modes clean their private storage.
The runner does not replace `HOME` or disable filesystem errors.

For an order-dependence audit, invoke the same regression runner with
`--order reverse`, or `--order random --seed 7`, and an explicit `--report` path
under ignored `test-results/`. For example:

```sh
PYTHONPATH=Python:. .venv/bin/python Python/tests/run_regressions.py Python/tests --isolate-modules --order random --seed 7 --report test-results/order-audit.json
```

These options reorder files, classes and methods within each execution stage.
Smoke and later stages keep their declared order, each file retains its isolated
process, and each class stays contiguous so class fixtures run once per stage.
The report records the order, seed, planned modules and actual case outcomes.
Random order requires an explicit seed and uses a private random generator;
it does not seed application code. Timing-based order cannot be combined with
an order audit. Replay with the same source, interpreter, dependencies and backend;
the seed reproduces the order, not thread scheduling, filesystem notifications or
external service responses. Reordered passes increase confidence but do not prove
that every possible ordering is independent. Test discovery imports still follow
the normal unittest discovery order.

An order audit needs fresh execution: disable verified-result reuse before
preparing a build-manager plan, and bind its final runner arguments before
computing evidence identities. A labelled reused result is useful prior evidence,
but it is not another execution. Keep editable external dependencies fixed too;
a captured Logistics snapshot does not freeze a separately edited manager
installation. Use the declared manager pin in disposable managed storage when
that checkout is changing concurrently.

Platform release checks with `--install` provision the platform’s pinned rclone
using archive and executable SHA-256 verification, then require the real synthetic
LocalCrypt regressions. They never access user remotes or credential packages.
Without that provisioning, local runs may skip crypt tests if rclone is absent.
Review tests keep their non-CLI cases active and explicitly skip only cases that
need the missing pinned executable. Report those skips separately from native
coverage; an installed-tool run still executes the complete review file.
Release provisioning uses the locked certifi CA bundle if `SSL_CERT_FILE` is not
already configured, including on macOS framework Python; TLS verification remains
enabled.

## Updating mobile host dependencies

Edit `mobile_build/requirements-host.in`, then regenerate its hash lock with
`uv pip compile mobile_build/requirements-host.in --python-version 3.12 --universal
--generate-hashes --output-file mobile_build/requirements-host.txt`. Commit both files.
Native app requirements remain in `mobile_build/pyproject.toml`; authentication tools
remain host-only. Do not copy a host virtual environment into a mobile payload.

## Local disk usage and private files

Virtual environments, `mobile_build/build/`, `mobile_build/payload/`, `mobile_build/logs/`,
`mobile_build/.tools/`, `mobile_build/.deploy-workspaces/` and checkout-root
`tmp/` are ignored generated output. Use the [artifact locations](validation-artifacts.md#find-an-output)
to find reports, scratch runs and probe compiler caches. For managed outputs,
preview [storage retention](../build-release/build-manager.md#automatic-storage-retention) before
cleanup and save any evidence you need to keep.
Keep credentials, `.env` files and signing keys local. Never put real secret values
in examples or fixtures. Release packaging also excludes conventional private
files and generated mobile output, even if accidentally tracked.

Run `python3 dev.py toolchain` after dependency updates. It compares mobile host
inputs and their lock, native/host Toga versions, shared desktop/mobile dependency
pins and CI Ruff pins against the existing application manifests. CI runs it too.
Python's application manifest and the native Briefcase manifest remain canonical;
the checker adds no second version registry.

Before committing, run `python3 dev.py hygiene` to check indexed paths against
ignore rules and inspect indexed text blobs for recognizable private keys and
GitHub/AWS token shapes. It prints only paths and categories, never matching
values. Stage specific reviewed paths first: the check reads the Git index, so it
does not certify unstaged/untracked content or arbitrary provider token formats.
Review every staged diff; never stage a virtual environment, native build output,
credentials or a local feature link.

## Worked contribution: desktop LM attachments

The attachment extraction is a complete example of the current ownership flow:

1. `Python/features/lm/__init__.py` registers the `lm.chat` page through
   `create_page`; it lazily imports `ui.page.LMPage`.
2. `ui/page.py` composes `AttachmentController` from `ui/attachments.py`.
   Menu callbacks keep their old page methods, which delegate to that owner.
3. The controller obtains registered project/buffer context through
   `AttachmentHost`. Portable `project_tools.py` owns file containment and IDE
   exclusions; the controller owns picking and publishing bounded composer text.
   Conversation records and checkpoints remain with `ConversationSession`.
4. `test_lm_ui.py` covers selection/file attachments, excluded paths, project
   choice across reopening and draft preservation. Run
   `python3 dev.py test desktop test_lm_ui.py`; its synthetic endpoint needs
   permission to bind localhost. Also run `python3 dev.py architecture` and lint.
5. This extraction is desktop-only, so it adds no mobile payload entry. A new
   mobile source instead needs its owner's `mobile_sources.json` and
   `test_mobile_packaging.py`, including any separately curated proof payload.
6. Update the LM developer guide for implementation and its user guide only when
   user-visible behavior changes. Review explicit paths, stage them, run hygiene,
   then commit. Do not stage runtime output or unrelated work.

Follow that sequence for a first change: identify a registration/callback, keep
policy with its owner, exercise behavior tests, check packaging and update the
owning guide. Use `dev.py compatibility` when an older path forwards to new code.

The architecture check includes module-qualified imports and literal
`module:attribute` references used by deferred factories. Portable-owner checks
also reject deferred commonUtils UI, PySide6 and Toga references. It inspects
syntax without importing features or optional toolkits; dynamically constructed
strings still require source review. Document editor packages additionally enforce the [shared storage boundary](../architecture/document-storage.md#enforced-architecture-contract), including scoped persistence exceptions.

Run `python dev.py test desktop test_document_architecture.py` when changing document
storage ownership or architecture enforcement. These syntax-only mutation tests also
run in CI without desktop/native toolkits.

## Portable import matrix

Run `python dev.py test desktop test_portable_imports.py` and
`python dev.py test desktop test_architecture_contracts.py` after changing portable
owners or their policy. The import matrix uses fresh child interpreters and isolated
XDG directories per owner, actively rejecting presentation imports even when the
application catches `ImportError`. Its probe regression demonstrates an indirect,
caught import is still a failure. The static CI job runs both checks without
installing a desktop toolkit. See the [portable owner policy](../architecture/architecture.md#portable-owner-policy)
for selection and limits; the document smoke suite additionally exercises real
format operations without desktop/image packages.

Desktop suite deadlines start with `build-tests.json`. The Windows platform plan
in `logistics_build/validation_plans.py` gives the full Logistics suite at least
2,100 seconds. A measured Windows run exhausted 1,800 seconds with four extended
modules remaining. Smoke budgets and other platform budgets stay unchanged; a
larger declared suite budget is never shortened. Logistics retains its
300-second per-file deadline. Full project discovery includes its build-manager
integration contracts, and shared, native, runtime and release-tooling checks
remain required.

The external SDK's complete generic self-test inventory is separate qualification:
run `python -m build_manager.contracts` with its owning interpreter. It is not
selected automatically by a Logistics platform or release plan. Existing prepared
runs keep their original gates and failure history; this policy applies to new
plans. See [validation ownership](../build-release/build-manager.md#validation-and-local-outputs).

Native build prerequisites are prepared separately by explicit **Update project tooling…**
(or `python -m build_manager.cli tooling --project NAME --update --confirm`) after
the owned mobile environment exists. This prepares pinned Go and the verified
pure langdetect wheel; `dev.py doctor` checks the selected native tools and wheel
receipt. [Native prerequisite ownership](../build-release/build-manager.md#project-owned-native-prerequisite-setup)
explains preservation, supported hosts and recovery.
