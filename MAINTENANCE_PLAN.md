# Coordinated maintenance

Historical record, not the current application contract. Start with
[developer documentation](docs/developer/README.md) for current behavior and validation.

Work through each change with focused checks before committing. Preserve the
historical support assumptions; current runtime requirements are in the root README.

- [x] Validate Hue targets and settings; move bridge calls off the UI thread.
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

- Local suites: Logistics 828 tests plus three regression-runner checks,
  commonUtils 637 tests (one skip),
  plus 10 release-tooling tests; external-project results are maintained by their owners.
- All four repositories' GitHub workflows passed. Logistics passed Windows,
  macOS, Ubuntu and Fedora checks, including compression parity.
- The [source release checks](https://github.com/ispaure/logistics/actions/workflows/release.yml)
  build a ZIP from tracked source and pinned submodules. The downloaded artifact
  is compared against the tested local package. Public and private launches were
  checked locally.
- macOS intermittently crashed inside Qt when unrelated shared test files reused
  one application. Shared test files now use fresh processes; assertions, crashes
  and timeouts still fail validation. The application suite stays in one process.
  CI also retains native crash reports. The exact native defect is unconfirmed.
  Live Blender, Hue hardware and external services were not exercised.
- Windows browser fixtures exceeded their five- and eight-second startup waits.
  Their waits now allow 20 seconds and report unfinished work; the shared-suite CI
  budget allows ten minutes rather than five. Completion is still required.

Release tagging follows a validated pushed revision and an agreed version.
