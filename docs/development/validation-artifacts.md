# Local validation artifacts

Test screenshots, recordings, machine-readable results and one-off probe copies
are local working material. Keep them under ignored `test-results/` or the
owning tool's ignored `mobile_build/logs/` directory. The standalone widget and
video API validators write new reports under ignored `tmp/test-results/`.
These report locations are excluded from source releases and mobile offline help.

Run one-off commands through `python -m logistics_build.build_retention --scratch
COMMAND ...`. Arguments containing `{workspace}` expand to the disposable
directory under `tmp/runs/scratch/`. The command receives its own
`COMMONUTILS_STORAGE_ROOT`, so automatic document history
and shared caches cannot write into the user's normal cache. This overrides an
inherited storage root. Save evidence outside the workspace before it exits.
Python callers of `scratch()` must set `COMMONUTILS_STORAGE_ROOT` inside their
workspace before importing application or shared UI modules. Probes must also
redirect any feature preferences or credentials they modify to private fixtures.

The historical mobile evidence archive is retained locally at
`test-results/mobile-evidence/`. It was moved from
`docs/development/mobile-evidence/`, which is also ignored and explicitly excluded
from packaging for older checkouts. Documentation references to individual local
artifacts are plain text; fresh clones and release packages do not contain them.
Submodule-owned reports stay in that submodule's own ignored `test-results/`.

Keep reusable test drivers and fixtures in their existing tracked test owners.
Keep concise descriptions of validation scope and known limits in the owning
developer guides. Past results do not validate later changes; use the
[testing guide](testing.md) to rerun the relevant checks.

Logistics ignores directories named `mobile-evidence` under either legacy documentation layout, including `docs/development/mobile-evidence/`.
