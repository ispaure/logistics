# Local validation artifacts

## Find an output

| Output | Default checkout-relative location |
| --- | --- |
| Scratch and compiler cache | `tmp/runs/scratch/` and `tmp/cache/compiler/` |
| Standalone widget and video API reports | `tmp/test-results/widgets/` and `tmp/test-results/media/` |
| Manager history and host timing | `test-results/build-manager/` and `test-results/test-timings/` |
| Mobile deployment diagnostics | `mobile_build/logs/` |

Use producer-reported paths for overrides and legacy receipts. See
[retention](../build-release/build-manager.md#automatic-storage-retention).

## Read Manager host timing

Successful managed Python regression phases retain timing JSON and JUnit under
the run's `artifacts/` directory. Find each file by its declared kind and hash
in `result.json`. A cache hit copies both reports into the current run and
records `reused: true` and the original run, phase, timestamps and elapsed time
under `reuse`. Read the timing JSON as a measurement of that original execution.
The cache hit's phase time is recorded as zero.

For failed assertions, Manager retains JUnit and the phase log. The pinned
Manager keeps the runner's timing checkpoint at the path passed to `--report`.
Save that checkpoint before the workspace expires when investigating a failure.
A signed hosted proof records the attested result separately and provides no
fresh local measurement.

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
