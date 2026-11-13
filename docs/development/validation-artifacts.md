# Local validation artifacts

## Find an output

Paths are relative to the checkout. Use the path reported by the producing tool
when it supports an output override.

| Output | Where to look |
| --- | --- |
| Managed scratch workspace | New runs use `tmp/runs/scratch/`. Saved receipts can still reference marked runs under `test-results/build-scratch/`. |
| Probe compiler cache | New caches use `tmp/cache/compiler/`. Marked legacy caches remain under `mobile_build/.tools/build-manager/compiler-caches/`. |
| Standalone widget or video API validator report | New widget reports default to `tmp/test-results/widgets/`. The video API check writes `tmp/test-results/media/<platform>-api-compile.json`. Earlier reports may be under `test-results/widgets/` or `test-results/media/`. |
| Build Manager run history for Logistics | `test-results/build-manager/` |
| Standalone platform checks or regression timings | [Platform checks](platform-checks.md) default to `test-results/`. The regression runner writes timing reports to `test-results/test-timings/` by default. |
| Mobile deployment and diagnostic logs | `mobile_build/logs/` |

Keep screenshots, recordings and other manually saved evidence under ignored
`test-results/` or the owning tool's ignored `mobile_build/logs/` directory.
These outputs stay out of source releases and mobile offline help. For the
root `tmp/` exclusion, see [release packaging](releasing.md).

## Run an isolated probe

Run one-off commands through `python -m logistics_build.build_retention --scratch
COMMAND ...`. Arguments containing `{workspace}` expand to the disposable
directory under `tmp/runs/scratch/`. The command runs there, so use absolute
paths for scripts or inputs in your checkout. It receives its own
`COMMONUTILS_STORAGE_ROOT`, so automatic document history
and shared caches cannot write into the user's normal cache. This overrides an
inherited storage root. Save evidence outside the workspace before it exits.
Python callers of `scratch()` must set `COMMONUTILS_STORAGE_ROOT` inside their
workspace before importing application or shared UI modules. Probes must also
redirect any feature preferences or credentials they modify to private fixtures.

For cleanup and protection rules across current and legacy workspace and cache
locations, see [automatic storage retention](build-manager.md#automatic-storage-retention).

## Historical evidence

The historical mobile evidence archive is retained locally at
`test-results/mobile-evidence/`. It was moved from
`docs/development/mobile-evidence/`. Packaging excludes `mobile-evidence/`
directories throughout the wiki, including feature guides. Documentation references to individual local
artifacts are plain text; fresh clones and release packages do not contain them.
Submodule-owned reports stay in that submodule's own ignored `test-results/`.

Keep reusable test drivers and fixtures in their existing tracked test owners.
Keep concise descriptions of validation scope and known limits in the owning
developer guides. Past results do not validate later changes; use the
[testing guide](testing.md) to rerun the relevant checks.
