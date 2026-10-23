# Ecosystem maintenance progress

## Session rules and recovery

Started October 22, 2026 (America/Toronto). Work branches are
`codex/ecosystem-maintenance` in all three repositories; original branches and
baseline revisions are in the [audit](architecture_audit.md). No remote writes,
release publication or production-data operations are authorized for this pass.
Raw reports remain ignored; tracked guides contain concise results only.

## Discovery and baseline

- Confirmed clean worktrees and the actual Blender 5.2.2 alpha branch.
- Read repository/developer ownership and commonUtils integration contracts.
- Measured tracked non-vendored Python and inspected feature/import boundaries.
- Doctor, architecture (25 host adapters / 15 feature edges), toolchain consistency,
  hygiene and configured correctness lint pass.
- Started full isolated shared/desktop/mobile suites plus Blue Hole adapter tests.
- No Blender executable found. No device tests or temporary Boox apps installed.
- Initial priorities: no-overwrite installation promotion, shortcut persistence,
  staged archive publication and malformed project state. Implementation and
  validation entries follow as work units complete.

## Shared installation promotion

- Reproduced three baseline failures: racing publication overwritten, existing
  recovery copy overwritten, and external content replaced during rollback.
- All promotion/backup/restoration moves now use existing atomic no-replace
  publication. Conflicted restoration retains and reports its recovery path.
  Resolved path overlap checks also reject parent aliases.
- Validation: 11 focused persistence/exclusive-copy tests pass; existing directory
  promotion and normal rollback remain covered. Shared commit: `69b2ef1`.
- Limitation: host macOS primitives exercised; native Windows/Linux CI not run.

## Test harness isolation and optional backend

- Initial complete runs: shared 179 files / 5 failed; desktop 179 / 11 failed;
  mobile 162 / 2 failed. Blue Hole: 26 tests pass. These are fresh baseline results,
  not regressions introduced by promotion (which had no production call sites).
- Baseline failures include sandbox-denied commonUtils cache/temp writes, denied
  loopback socket fixtures, watcher/timing assertions and missing optional Toga.
- Regression runner now scopes shared storage, `Path.home()` and platform
  config/cache roots before discovery; it restores state and removes only its own
  fixtures. HOME remains unchanged. Seven runner regressions pass, including
  single-process/module-isolated storage creation and cleanup.
- Shared native-browser lifecycle tests now explicitly skip when optional Toga
  is absent, matching other native test modules; all four pass in the existing
  mobile environment with the dummy backend. No dependency added.
- Full reruns are in progress. Native backend tests remain distinct from device
  tests; a skip in the desktop interpreter is not recorded as a pass.

## Editor shortcuts

- Reproduced retained changed bindings after JSON serialization failure and leaked
  temporary QActions after malformed shortcut values.
- Replaced duplicated file staging/fsync/replace with shared atomic JSON writer;
  restored live bindings after serialization/value/I/O failure; validation actions
  now retire through a full-loop finally block. Existing persisted mapping and
  post-save cross-window propagation remain intact.
- All 12 editor-extension tests pass, including new failure and cleanup cases.
  Commit identifier follows in the next work-log checkpoint.

## Archive extraction

- Reproduced publicly visible partial output during per-child publication.
- Completed staged directory now publishes through one atomic no-replace rename;
  failed publication no longer recursively removes a public directory.
- All 19 shared archive tests pass, including format/encryption round trips,
  cancellation, complete-tree publication and racing destination preservation.
  Shared commit identifier follows at the next checkpoint.

## Commit checkpoint and IDE admission

- Shared archive publication: `988cfa2`; optional Toga test correction: `b3e0b9f`.
- Logistics runner isolation: `3d985a4e`; editor shortcuts: `1dfcb214`.
- All 11 shared browser test files pass outside the restricted sandbox with private
  storage. This distinguishes native watcher restrictions from publication changes.
- IDE regression reproduced partial project admission and accepted malformed
  `open_ids` / `active_id` / duplicate project IDs. The store now validates complete
  state before publishing it and bounds the actual read instead of relying on an
  earlier stat size. Invalid checkpoints remain untouched and cannot be saved over.
- All 26 IDE tests pass. Existing version-1 files, deduplication of open IDs,
  stale string-ID filtering and concurrent-writer protection remain covered.
