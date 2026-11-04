# Cross-platform archive checks

`.github/workflows/archive-platform-checks.yml` runs on macOS, Windows and an
official Fedora 43 container hosted on Ubuntu. Fedora is the only Linux test
distribution; Ubuntu is infrastructure for the container and static/mobile tooling. It checks the same committed
commonUtils submodule that Logistics uses. Jobs continue independently on failure.
Each job runs all commonUtils tests, all Logistics tests and a full historical
compression comparison, then uploads JSON summaries and logs for 14 days.

The direct runner bootstraps both the repository and its `Python/` source root
before importing the external manager. The manager imports the pinned shared
library in the runner process as well as in its child checks. An isolated
entry-point regression exercises the real manager without inherited PYTHONPATH.

From a normal recursive clone, use the project's Python 3.12.2 environment:

```sh
python Python/tests/run_platform_checks.py
```

Add `--install` to install the pinned project dependencies into that interpreter
first. Use a virtual environment. Python 3.12.2 is required by the current project;
Fedora's newer system Python is not the test interpreter. The script uses native
path separators and Qt's offscreen backend automatically. Its default report and
fixture directory is `test-results/`, which is ignored by Git. A second run should
use a new `--results-dir` or remove the previous disposable reports first.

The historical comparison requires the Git history for Logistics
`51b610ed3f0d55e94bd9b179621545fe867ccb38` and commonUtils
`d5c42ffd4306c010d9625b8a9bae57cdf097a567`. CI fetches the latter explicitly.
These are the cleaned-history equivalents of the original pre-password baseline;
its implementation is unchanged. Shallow clones may need to fetch those commits before running locally.
The comparison can also run by itself:

```sh
python Python/tests/compare_comic_zip_versions.py
```

It exports pristine baseline code into disposable folders and compares 24 complete
compression runs: four input layouts, two retention/animation policies, and three
versions (old plain, current plain, current AES-256). Extraction, sanitization,
staged outputs and final decrypted entries must match by exact names, sizes and
SHA-256 hashes. Logs use a frozen clock. The old helper's explicit AES extraction
must match plain extraction; the old comic compressor's unsupported encrypted run
must fail without changing its input. No existing library files are touched.

Comparisons happen within each OS and installed encoder environment. Byte equality
between different OS encoder builds is not required. These headless checks cover
archive placement and Qt logic, not desktop interaction, actual FUSE/rclone mounts,
network credentials or external RAR extractors. The Fedora container tests Fedora
userspace with an Ubuntu host kernel; a local Fedora run is still useful for the
real desktop and mounted-storage environment.

The first Windows run exposed a pre-existing archive flush bug: Windows rejects
`fsync` on the legacy compressor's read-only descriptor. Current archive creation
and comic rewrites flush a writable staging handle before restoring permissions.
For historical Windows parity only, the comparison harness changes the legacy
staged ZIP's flush-open mode from `rb` to `r+b` in memory; entry placement, content,
encoders and retention policy remain untouched. Each trace records this adjustment.
A separate completely pristine Windows baseline run must reproduce the flush
failure, preserve its input and produce the same staged result. Other operating
systems use the pristine baseline without this adjustment. The JSON comparison
records both outcomes so this boundary is visible rather than a skipped test.

Fixtures use the native long form of the OS temporary directory, because Qt
expands Windows 8.3 aliases. Permission-preservation tests compare against the
mode actually supported by the host filesystem rather than requiring POSIX bits
on Windows.

Fixtures close SQLite connections explicitly and use legal native filenames and
paths. Tests that execute a POSIX shell or require POSIX executable permission
bits run only on POSIX hosts; archive and password checks run on every platform.

## Stalled tests

The native UI fixture keeps bounded navigation and WebKit load-event traces.
On iOS, passive start/commit/failure/process-termination callbacks supplement
the application policy trace; toolkit-preapproved initial URLs can bypass the
application handler. Timeout snapshots include the pending preapproved URL,
estimated progress, attachment and ancestor visibility. Where available, optional
test-only WebKit process identifiers and responsiveness accompany the snapshot;
failure artifacts also retain host memory and relevant process summaries. The fixture inherits
Toga's policy and finish handlers and retains the normal render deadline.
The hosted iOS job keeps the latest two 12.5 MiB WebKit log segments throughout
the test, rather than stopping capture when the first segment fills. Manual
dispatch of **Native mobile prototype builds** offers `ios_object_diagnostics`
for disposable simulator apps: it enables Objective-C zombies and allocation
stack logging. A message sent to a deallocated object fails validation even if
the native fixture otherwise reports success. This mode diagnoses lifetime
failures; a passing diagnostic run alone does not resolve an intermittent crash.

Hosted prebuilt iOS acceptance has one bounded recovery for an evidenced simulator
startup failure. A failed private WebView must be attached and loading at 10%,
with neither a live nor provisional WebContent process. Its fresh native report
must match the prepared source, and the live process sample must show at least
one distinct Swift task worker per host CPU synchronously blocked in Screen Time
settings RPCs. This exhausts the cooperative executor also needed by WebKit's
ExtensionKit process launch. A disposable native probe reproduces the mechanism:
blocking every Swift worker prevents a new WebContent process from starting;
leaving one worker available permits the expected page to render.

Only the simulator recorded by the native gate's current ownership lease can
recover, after the first app process is proven stopped. The driver archives the
first failed report, sample and logs, records
admission before retry, then starts the complete native suite once more on that
already-booted simulator. Each attempt retains the original render deadline and
the same prepared application and native assertions. Recovery rejects native
faults, handler errors, stale evidence, source changes, ordinary DOM assertions
and nonzero WebContent process identifiers. A controller restart cannot admit a
second recovery for that simulator and prepared source. Both attempts and the
admission record remain under the job's ignored logs and uploaded diagnostics.
Local acceptance and ordinary application launches do not enable this recovery.
The hosted job's outer budget includes the possible additional 30-minute native
attempt; individual render and native-attempt deadlines remain unchanged.

Native transfer-review drivers acknowledge an action when its guarded native
handler starts. If comparison progress changes the revision before a click's
navigation message arrives, the driver retries the current rendered action within
the existing 30-second action deadline. Full and incomplete approval retain the
production revision checks. The held-comparison fixture has a 90-second failsafe
covering the separate 30-second render, action and retirement assertions; cleanup
releases it immediately when any assertion fails. Diagnostics record accepted
actions, click counts and revisions.

An acknowledgement received during the driver's polling delay stops further
clicks before its next JavaScript call. This prevents a delayed second approval
from presenting a real confirmation after a fixture's dialog mock has ended.
Fixture answers to real iOS dialogs wait for presentation, native dismissal
completion and overlay detachment before resolving the response future. A fixed
delay can otherwise leave UIKit's dimming view attached after the test proceeds.

The suite runner reports the active test and completed count every 60 seconds.
Native crashes also produce Python tracebacks. The outer platform runner allows
ten minutes for the shared suite and fifteen for Logistics and uploads its logs; macOS jobs also collect native Python
crash reports when available. To run the application suite with these diagnostics:

```sh
python3 dev.py test desktop
```

Qt tests use `QtTestCase` to stop workers and release new windows between tests.
Both suites run every test file in a fresh process so unrelated fixtures do
not share Qt application state. An assertion failure, abnormal exit or timeout
still fails validation; later files run to provide the remaining results. To run
the shared suite directly, use the project interpreter with
`Python/tests/run_regressions.py Python/commonUtils/tests --isolate-modules`
and `PYTHONPATH=Python`. Use [the validation guide](testing.md) for environment setup.

Both complete suites must pass; each file owns its GUI state in an isolated
process. See `Python/tests/run_platform_checks.py` for the current orchestration.

## Parallel native iOS validation

`.github/workflows/mobile-build.yml` builds one iOS Simulator application in
Briefcase test mode, then runs the complete native suite on iPhone, iPhone Duo and iPad
in separate matrix jobs. Each device restores the same generated project and
binary and runs with `ui_tools.py run ios --no-update`. The runner rejects a
missing binary, a production-mode app, dirty source or a different Logistics or
commonUtils commit before launch; the resulting report must still pass the full
native case and source checks. The Duo job additionally requires its rotation
matrix. Android builds and validates independently of the iOS jobs.

Native checkpoints stream on hosted runners as well as local runs. Linux CI
also records available host memory while the native child runs, so an abruptly
terminated runner does not leave the entire UI phase opaque. The Android build
disables persistent Gradle daemons before emulator validation; this avoids keeping
an idle build JVM alongside the emulator. These diagnostics do not relax native
case inventories or time budgets.

Every iOS validation run requires all three device families, including iPad
independent-window checks. An iPad failure blocks the run. Device jobs use
fresh simulators created through the build manager, matching the selected SDK
major and required hardware family (the 27.1 runtime is Duo-only; ordinary
phones/tablets use 27.0). Their saved ownership leases support
cleanup after success, failure or boot errors; diagnostics are captured before
the always-run cleanup step. Pre-existing simulators are left intact.
Device jobs use
separate runners and artifacts named
`logistics-native-ios-iphone`, `logistics-native-ios-duo` and
`logistics-native-ios-ipad`; their logs and reports cannot overwrite each other.
The shared project is retained as `logistics-ios-test-project`, and
`logistics-native-ios` contains the test-mode simulator ZIP and build diagnostics.

The final native gate checks every selected build and device job. Failed,
cancelled and required skipped jobs fail the gate; only unselected platforms may
be skipped. Device matrix jobs use `fail-fast: false` to retain other devices'
diagnostics after a failure. Source release packaging also requires the separate
desktop/platform and Android/iOS document-runtime workflows to succeed.

Native log verification also rejects exceptions ignored by ctypes callbacks.
A completed suite cannot pass while a native-to-Python callback reports a
cleanup or layout exception.

The hosted Android native job uses job-owned Go build and module caches. It
clears those disposable caches after native compilation, before unpacking the
emulator image, and records disk usage on either side. The APK and native
libraries remain available for testing and artifact collection.

Local scheduling validation uses `test_parallel_ios_workflow.py` and
`test_native_report.py` under `mobile_build/tests/`: actual workflow shell steps
run against disposable fixtures, covering archive reuse, executable permissions,
report isolation, device flags, source mismatch and all gate status combinations.
Validate workflow syntax and expressions with actionlint, recognizing the existing
`xcode-27` runner label. These checks do not establish hosted runner capacity,
native test success or elapsed-time savings. Hosted execution and timings remain
unverified until the later GitHub release validation checkpoint.
