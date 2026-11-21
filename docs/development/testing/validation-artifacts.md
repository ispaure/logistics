# Local validation artifacts

## Find an output

Write new checkout-local evidence under `tmp/test-results/<run-id>/` and use `tmp/` for other scratch. Use the run’s recorded artifact paths when inspecting results. When updating a producer, migrate its consumers and verify a failed run in both Project History and the CI artifacts.

| Output | Paths used by existing producers and receipts |
| --- | --- |
| Disposable scratch | `tmp/runs/scratch/` |
| Rebuildable probe compiler cache | `tmp/cache/compiler/` |
| Managed mobile device build workspaces | `tmp/build/mobile/` |
| Standalone widget and video API reports | `tmp/test-results/widgets/` and `tmp/test-results/media/` |
| Standalone mobile navigation reports | `tmp/test-results/navigation/`, one directory per run unless `--output` is supplied |
| Standalone host timing | `tmp/test-results/test-timings/` |
| Desktop platform checks | `tmp/test-results/desktop-<run-id>/` or the supplied `--results-dir`. Hosted desktop jobs use the GitHub run ID and attempt. |
| Hosted native mobile test evidence | `tmp/test-results/native-<run-id>-<attempt>/`. The device job artifact also carries Briefcase diagnostics. |
| Local Manager mobile test evidence | `tmp/test-results/emulator-<run-id>/` and `tmp/test-results/simulators-<run-id>/` |
| Manager history | `test-results/build-manager/` by default. With the Manager checkout-local layout selected, fresh runs use `tmp/test-results/build-manager/` and history includes both roots. |
| Mobile deployment diagnostics | `mobile_build/logs/` |

Use the path recorded by the producer for overrides and older runs. On Manager
versions that support checkout-local results, select the registered project
with `build-manager set-results-layout REGISTRATION_ID tmp` and reopen its
project tab. The setting preserves the trusted project descriptor and original
saved-run locations. New incoming mobile acceptance plans use the selected
results location. The Manager resumes older runs at their recorded paths.
Retention recognizes owned scratch, compiler caches and device workspaces at
both generations of paths. See [automatic storage retention](../build-release/build-manager.md#automatic-storage-retention).

## Find a completed test run

For direct tests, open the path printed after **Timing report**. To find an
earlier report, match the checkout and test selection and check `complete` and
`finished_at` in its JSON. The runner can update an in-progress report.

For managed tests, use **Project History** or run
`python -m build_manager.cli history --project Logistics` in the Manager
environment, substituting the registered name if it differs. Open the matching
run's `result.json` and check its source, backend, status and finish time. Each
retained artifact is listed with its kind and hash.

For a local Android or iOS native phase, open its original phase log or the
native result JSON to find the attempt's diagnostics directory. A retry gets
its own directory. Each directory holds the Briefcase native log and any
diagnostics the runner captured before disposing of the test device.

## Read Manager host timing

Managed Python regression phases retain the timing JSON and JUnit they produce
under the run's `artifacts/` directory. Find each file by its declared kind and
hash in `result.json`. A cache hit copies both reports into the current run and
records `reused: true` and the original run, phase, timestamps and elapsed time
under `reuse`. Read the timing JSON as a measurement of that original execution.
The cache hit's phase time is recorded as zero.

On failure, inspect the phase log and any retained JUnit or timing checkpoint.
The Manager retains freshly written timing JSON even if JUnit is missing or
invalid. JUnit supplies the authoritative case inventory. A signed hosted proof
records the original attested result and its scope.

For Manager CLI event capture, add `--events --event-format compact` to
`start`, `run` or `resume`. Compact streams send live case deltas and periodic
checkpoints. Consult the retained result and JUnit for final outcomes.

## Run an isolated probe

Run `python -m logistics_build.build_retention --scratch COMMAND ...`.
`{workspace}` expands to the disposable working directory. Use absolute script
paths. The command receives private `COMMONUTILS_STORAGE_ROOT`. Direct
`scratch()` callers must set it before app imports. Redirect mutable preferences
and credentials to fixtures and save needed evidence before cleanup.

## Historical evidence

Preserve older evidence in `test-results/` and `mobile_build/logs/` at its recorded location.
The local archive is `test-results/mobile-evidence/`. Releases and offline help
exclude evidence, including legacy wiki copies. Keep reusable drivers and
fixtures with their test owners.
