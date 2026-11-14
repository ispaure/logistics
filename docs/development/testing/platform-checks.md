# Cross-platform archive checks

`.github/workflows/archive-platform-checks.yml` validates macOS, Windows and
Fedora userspace in a container hosted on Ubuntu. It runs shared and Logistics
suites plus historical compression parity, keeping reports for 14 days.
[test-environments.json](../../../test-environments.json) pins environments.

Run from a recursive clone with the project Python 3.12.2 environment.

```sh
python Python/tests/run_platform_checks.py
python Python/tests/compare_comic_zip_versions.py
```

The second command runs parity alone. For the platform runner, add `--install` to
provision pinned dependencies and rclone in the test environment. Use a fresh
`--results-dir` for repeats. To select the checkout interpreter explicitly, run
`.venv/bin/python Python/tests/run_platform_checks.py` on macOS/Linux or
`.venv/Scripts/python.exe Python/tests/run_platform_checks.py` on Windows.

Shallow clones may need Logistics `51b610ed3f0d55e94bd9b179621545fe867ccb38` and
commonUtils `d5c42ffd4306c010d9625b8a9bae57cdf097a567`. The 24 disposable runs compare
old plain, current plain and current AES-256 within each OS by path, size and
SHA-256. Unsupported legacy encrypted compression must preserve its input.
On Windows, the harness records the pristine baseline's read-only `fsync`
failure and uses `r+b` for the legacy flush in the parity run. It checks that the
pristine run preserves its input and yields the same staging result.

## Fedora environment preparation

`Python/tests/platform/fedora.Containerfile` defines the shared hosted/local
rootless-VM image. Run `fedora.sh` inside that image. Inspect
`test-results/fedora-setup.log` for interpreter, manager and dependency
deadlines. The 150-minute job includes preparation, the 90-minute platform
deadline, release-tooling checks and uploads. Both suites report even after failure.

## Stalled tests

Isolated files report progress every 60 seconds and time out after 300 seconds.
`build-tests.json` sets 1,800-second suite deadlines for shared and Logistics checks.
`logistics_build/validation_plans.py` raises the Logistics suite minimum to 2,700
seconds on Windows and 2,400 on macOS. Inspect logs, checkpoints and native crash reports.

```sh
python3 dev.py test desktop
PYTHONPATH=Python .venv/bin/python Python/tests/run_regressions.py Python/commonUtils/tests --isolate-modules
```

On native iOS stalls, inspect bounded WebKit traces and targeted process samples.
Manual `ios_object_diagnostics` enables zombie/allocation diagnostics on disposable
simulators. Hosted prebuilt iOS can retry once on its leased simulator after the
first process exits, with exact source and fresh evidence of an attached WebView
stuck at 10%, no live/provisional WebContent and Screen Time RPCs blocking at
least one distinct Swift worker per host CPU. The original report and sample are
retained. Each attempt uses the
same render deadline, binary and full suite. Ordinary assertions, source mismatches
and native faults fail the gate.

## Parallel native iOS validation

`.github/workflows/mobile-build.yml` builds one Briefcase test-mode app. Independent
iPhone, Duo and iPad jobs restore it and run `ui_tools.py run ios --no-update`.
iPhone/iPad use runtime 27.0 and Duo uses 27.1 with its required rotation matrix.
iPad must pass independent-window checks. Android runs independently. The native
attempt limits are 30 minutes per iOS device and 40 minutes on Android.

The gate requires exact source and complete reports from all selected jobs.
Failed, cancelled and required skipped jobs fail, as do unhandled native callback
errors even with passing cases. A complete stdout report takes precedence. If
stdout lacks a report, iOS needs a fresh cache result. A structured stdout failure
fails the gate. Capture device diagnostics
before always-run cleanup of leased simulators.

Check local workflow changes with `test_parallel_ios_workflow.py`,
`test_native_report.py` and actionlint with the `xcode-27` runner label.
Hosted native execution and capacity require a hosted run.

## Native suite timings

Summarize a report or `logistics-native-ui-timings.json`:

```sh
python -m mobile_build.validation.native_timing_report path/to/report.json
```

`LOGISTICS_NATIVE_TIMING` emits full events. Use `self_s` for exclusive time and
compare rotation request, settling, geometry and screenshot costs separately.
