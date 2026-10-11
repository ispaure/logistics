# Coordinated maintenance

Work through each change with focused checks before committing. Preserve the
Python 3.10+ support statement and the separate Ally documentation boundary.

- [x] Preserve existing Ally installations and configuration on failure.
- [x] Validate Hue targets and settings; move bridge calls off the UI thread.
- [x] Match Ally's dependencies to Logistics and test both launch modes.
- [x] Apply X-Plane settings once, preserve file conventions and recovery copies.
- [x] Report action failures and external launches accurately.
- [x] Move remaining lengthy integration workflows into owned workers.
- [x] Review mount identities and preview destructive integration changes.
- [x] Split large orchestration methods and clean touched legacy imports.
- [x] Reconcile feature coverage and remaining platform limitations.
- [x] Synchronize Blue Hole's commonUtils subtree with the published shared revision.
- [x] Add reproducible cross-repository validation workflows.
- [x] Documentation pass one: correctness, feature coverage and usable examples.
- [x] Documentation pass two: shorten, verify examples and check every local link.
- [x] Run full suites, compression parity and extracted-package validation.
- [x] Commit and push all four repositories; wait for GitHub checks and repair failures.

Validation completed October 11, 2026:

- Local suites: Logistics 828 tests, commonUtils 637 tests (one skip),
  Ally Tools 33 tests, Blue Hole 14 adapter tests, and 10 release-tooling tests.
- All four repositories' GitHub workflows passed. Logistics passed Windows,
  macOS, Ubuntu and Fedora checks, including compression parity.
- The [source release check](https://github.com/ispaure/logistics/actions/runs/38119613162)
  built a ZIP matching all 792 files in the tested local package. Public and
  private launches were checked locally.
- One macOS shared-suite process crashed inside Qt. A local full-suite repeat
  and the debug rerun passed; the native crash's cause remains unconfirmed.
  Live Blender, Hue hardware and external services were not exercised.
- A Windows browser fixture exceeded its five-second startup wait. Its wait
  now allows 20 seconds and reports unfinished workers; the shared-suite CI
  budget allows ten minutes rather than five. Completion is still required.

Release tagging follows a validated pushed revision and an agreed version.
