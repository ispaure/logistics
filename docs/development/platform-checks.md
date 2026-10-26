# Cross-platform archive checks

`.github/workflows/archive-platform-checks.yml` runs on macOS, Ubuntu and Windows,
plus an official Fedora 43 container hosted on Ubuntu. It checks the same committed
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

Every iOS validation run requires all three device families, including iPad
independent-window checks. An iPad failure blocks the run. Device jobs use
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

Local scheduling validation uses `test_parallel_ios_workflow.py` and
`test_native_report.py` under `mobile_build/tests/`: actual workflow shell steps
run against disposable fixtures, covering archive reuse, executable permissions,
report isolation, device flags, source mismatch and all gate status combinations.
Validate workflow syntax and expressions with actionlint, recognizing the existing
`xcode-27` runner label. These checks do not establish hosted runner capacity,
native test success or elapsed-time savings. Hosted execution and timings remain
unverified until the later GitHub release validation checkpoint.
