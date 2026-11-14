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
