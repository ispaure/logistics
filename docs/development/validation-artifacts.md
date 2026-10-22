# Local validation artifacts

Test screenshots, recordings, machine-readable results and one-off probe copies
are local working material. Keep them under ignored `test-results/` or the
owning tool's ignored `mobile_build/logs/` directory. They are excluded from source
releases and mobile offline help.

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

Published branches and tags were separately rewritten to remove the historical
archives, and affected GitHub releases were deleted. Existing Git checkouts should
back up local changes and re-clone rather than merge the old and cleaned histories.
Private recovery bundles remain under ignored `test-results/history-cleanup/`.

Logistics ignores directories named `mobile-evidence` under either legacy documentation layout, including `docs/developer/mobile-evidence/`.
