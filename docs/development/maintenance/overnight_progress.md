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

## Blue Hole 5.2.2 alpha integration

- Synchronized exact committed shared revision `b3e0b9f994b0d367bbf940330c0f76531fa6f311`
  into the vendor, preserving namespace isolation. Vendor commit: `1567df9`.
- Three new consumer regressions failed before the installer change: interrupted
  copy damaged existing preferences, corrupted copy replaced them, and successful
  installation kept none of the recovery files promised by the README.
- Deluxe now stages/verifies privately and publishes through repaired shared
  promotion. Previous preferences and keymaps remain as recovery files. Its two
  publications remain separate; second-file failure reports completed paths and
  leaves Blender open. Registration, exports, environment formats and target
  Blender metadata are unchanged. Consumer fix: `8cef361`.
- All 31 consumer tests pass. Actual-vendor shared checks pass: 9 persistence,
  19 archive and 24 Perforce tests. Exact vendor membership and bytes match the
  recorded shared commit. No live Blender or Perforce-server check was possible.
- Logistics pin checkpoint: `f561bef5`; IDE checkpoint: `d5e21cf1`.

## Final validation checkpoint

The matrix below distinguishes restricted runs from targeted host reruns rather
than relabeling an initially failed command as passing.

| Validation | Result |
| --- | --- |
| Shared isolated suite | 179 files executed; 4 files failed watcher assertions in sandbox. All four are covered by successful host reruns: 11 browser files and 14 index files, zero failed files. |
| Desktop isolated suite | 179 files executed; 6 failed in sandbox. Each passes separately with required native notifications/loopback access: Git preferences, IDE browser, LM UI, mobile chat, Markdown speech DOM and mobile portability. |
| Mobile isolated host suite | 162 files, zero failed files with loopback access and disposable storage. |
| Shared native adapters in mobile environment | 25 files, zero failures and no skips, dummy Toga backend; includes all four lifecycle tests otherwise skipped by desktop. |
| Focused changed owners | 11 shared persistence/exclusive-copy tests, 19 archives, 12 editor extensions and 26 IDE tests pass. |
| Blue Hole / actual vendor | 31 consumer, 9 persistence, 19 archive and 24 Perforce tests pass; exact vendor checker passes. |
| Regression runner / release tooling | 25 tests pass with one native Windows launcher test skipped; includes all seven regression-runner tests. Release publishing is mocked in tests; nothing uploaded. |
| Documentation | All 5 hierarchy/link/ownership tests pass. |
| Syntax | All 1,859 tracked non-vendored Python files compile without execution. |
| Correctness lint / architecture | Pass; unchanged 25 host adapters and 15 cross-feature edges, zero boundary violations. |
| Toolchain / source hygiene / compatibility inventory | Pass; no dependency added. |
| Release packaging | Built and integrity-checked a local 2,216-file source ZIP after committing the exact submodule pin. The earlier attempt correctly rejected the uncommitted pin mismatch. Nothing published. |

Skipped tests are not counted as passes: the desktop suite reports six native
mobile-bridge skips; shared desktop reports 27 optional-Toga skips, exercised
separately through the 25-file native run; mobile host reports two browser DOM
skips requiring Node/Playwright; release tooling skips one Windows cmd/PowerShell
case. No Blender executable, native Windows/Linux session, device bridge, live
Perforce server or real mobile device was used. No temporary Boox apps installed.
No type checker is configured; no type-check success is claimed.

There are no unexplained remaining failures in the executed host scope after
required-access reruns. A single full unrestricted desktop/shared run was not
performed; the result is full restricted runs plus named successful reruns.
Raw reports and the local package remain ignored. No reset, push, release, merge
or production-data mutation was performed.

## Remaining priorities and resumption

1. Define offline volume identity and index retention before changing scan/prune
   policy. Existing SQLite schemas and resumable generations need migration proof.
2. Review eager versus deferred imports within the potential cyclic groups in the
   audit. Do not split framework construction solely to reduce file sizes.
3. Validate promotion/no-replace primitives on native Windows/Linux and Deluxe
   registration/installation under the actual Blender 5.2.2 embedded runtime.
4. Run device-bridge/browser DOM checks with their required runtimes and verify
   cooperative native reader/browser retirement on devices. Host dummy tests do
   not certify native accessibility, rendering or storage providers.
5. Continue focused Git backup/restore, EPUB metadata and legacy ZIP extraction
   reviews. Inspected paths already use captured arguments, source checks or staged
   writes; no speculative rewrite was made without a reproduced defect.
6. Formalize shared supported runtime/dependency ranges and consumer API policy;
   current CI pins are not a universal support promise.

The [audit assessment](architecture_audit.md#beforeafter-assessment-of-this-pass)
records evidence by quality dimension. The requested ecosystem-wide 7/10 target
is not established. This is a committed incremental rehabilitation series with
explicit remaining architecture and platform work, not certification that the
whole ecosystem has been rehabilitated. Resume from these branches and commits;
there is no scheduled background continuation.

## Final permission review

- A new regression reproduced mode loosening in the initial staged Blue Hole
  installer: a private read-only target became readable by other users after
  replacement. The final implementation copies the existing writable mode to
  staging and rejects symbolic-link/junction targets before permission changes.
- The private-mode and unchanged-link-target cases pass along with all 31 Blue
  Hole consumer tests. Follow-up commit: `9e4914f`. Native Windows permission/ACL
  behavior still requires its platform check; POSIX mode assertions are explicitly
  skipped on Windows.
