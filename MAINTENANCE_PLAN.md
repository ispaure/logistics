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
- [ ] Run full suites, compression parity and extracted-package validation.
- [ ] Commit and push all four repositories; wait for GitHub checks and repair failures.

Release tagging follows a validated pushed revision and an agreed version.
