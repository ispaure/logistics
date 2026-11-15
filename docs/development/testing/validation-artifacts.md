# Local validation artifacts

## Find an output

| Output | Default checkout-relative location |
| --- | --- |
| Disposable scratch | `tmp/runs/scratch/` |
| Rebuildable probe compiler cache | `tmp/cache/compiler/` |
| Managed mobile device build workspaces | `tmp/build/mobile/` |
| Standalone widget and video API reports | `tmp/test-results/widgets/` and `tmp/test-results/media/` |
| Manager history and host timing | `test-results/build-manager/` and `test-results/test-timings/` |
| Mobile deployment diagnostics | `mobile_build/logs/` |

Use the path recorded by the producer for overrides and older runs. Manager
history stays at its registered path so saved plans can replay and run
automatic maintenance with their trusted project descriptor. Retention still
recognizes owned scratch, compiler caches and device workspaces at both
generations of paths. See [automatic storage retention](../build-release/build-manager.md#automatic-storage-retention).

## Find a completed test run

For direct tests, open the path printed after **Timing report**. To find an
earlier report, match the checkout and test selection and check `complete` and
`finished_at` in its JSON. The runner can update an in-progress report.

For managed tests, use **Project History** or run
`python -m build_manager.cli history --project Logistics` in the Manager
environment, substituting the registered name if it differs. Open the matching
run's `result.json` and check its source, backend, status and finish time. Each
retained artifact is listed with its kind and hash.

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

Save raw evidence under ignored `test-results/` or `mobile_build/logs/`.
The local archive is `test-results/mobile-evidence/`. Releases and offline help
exclude evidence, including legacy wiki copies. Keep reusable drivers and
fixtures with their test owners.
