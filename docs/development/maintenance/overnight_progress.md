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

## First validation checkpoint (before resumed work)

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

The [first-checkpoint assessment](architecture_audit.md#beforeafter-assessment-at-the-first-checkpoint)
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

## Resumed execution: Git discard backup verification

The earlier final checkpoint was an unjustified stopping point, not an execution
limit or hard blocker. Work resumed from clean branches without repeating the
completed baseline. Remaining priorities continue to govern selection.

- Four new Git backend regressions reproduced unverified corrupt backup data,
  newer edits overwritten after a copy, earlier selection changes during later
  copies, and a new file appearing where the initial selection was missing.
- Backup preparation now uses shared verified snapshots, flushes copies, compares
  their SHA-256, and validates the entire selection while atomically publishing
  the unchanged backup manifest. Cancellation is translated to Git's existing
  cancellation result; no new dependency or shared API is introduced.
- This detects observed preparation races, not a lock against external editors
  after the final validation. Raw evidence stays in ignored maintenance results.

- Git validation: all 36 backend tests (including cancellation during backup),
  12 actual preferences/UI tests and 6 merge tests pass; correctness lint passes.

## Resumed execution: EPUB backup verification

- A new EPUB regression reproduced successful metadata replacement despite a
  corrupted recovery backup. The writer now hashes bytes read from the original
  and verifies the complete backup before replacing the book, using the existing
  shared stable-snapshot API. Failed verification preserves the original and
  removes only failed backup/staging paths. Existing names, metadata schema,
  source conflict checks and private-provider behavior remain unchanged.
- All 16 EPUB model/metadata tests pass, including corruption, backup permission
  failure, cancellation, duplicate backup naming and retained resource content.

## Resumed execution: portable native-browser lifecycle admission

- Fresh-interpreter tests reproduced that importing browser lifecycle required
  Toga through the parent initializer, including in an isolated vendored namespace.
- Kept the existing public package exports and moved their presentation body
  unchanged into `ui/native_browser/presentation.py`. The small package initializer
  now defers toolkit presentation and directly exports the portable lifecycle.
  An AST comparison confirms the presentation implementation is unchanged.
- Lifecycle-only tests now execute without Toga; only actual presentation cases
  retain backend skips. Package import blocker and namespace isolation tests pass.
  All 25 shared native test files pass in the mobile environment, and all three
  mobile browser consumer test files pass. No toolkit dependency was added.
- The mobile required-source list includes the moved implementation; packaged
  startup passes, as do all seven source-packaging tests and correctness lint.
- Prior resumed commits: Git backup verification `7bc7cb04`, EPUB verification
  `ced6b55a`, progress checkpoint `1824cd5e`.

## Resumed execution: deferred architecture references

- New contract tests reproduced missed colon-qualified feature/host references
  and deferred UI dependencies in modules declared portable. The AST scanner now
  normalizes valid `module:attribute` strings and recognizes deferred commonUtils,
  PySide6 and Toga module references without importing any implementation.
- Invalid references/prose remain excluded. Existing import handling is retained;
  a redundant identical branch in package-name calculation was removed.
- All eight architecture/ownership/compatibility tests pass. The current tree
  still has 25 reviewed host adapters, 15 cross-feature edges and zero violations;
  no policy exception or dependency was added to obtain that result.
- The full unrestricted shared suite now passes all 179 test files. Desktop and
  mobile full runs are still active; their final outcomes will be recorded here.

## Resumed execution: worker error and restart contracts

- New tests reproduced blank/invalid error-formatter output becoming an empty
  success signal, formatter exceptions escaping result publication, and stale
  result/error/cancellation fields on restarted workers. An actual progress-widget
  regression showed a `TimeoutError()` displayed as a successful finished job.
- ResultWorker now resets state per run and always publishes a nonempty failed
  outcome. A failed redaction formatter uses type-only fallback details, never
  unredacted exception text. Success, configured cancellation and cooperative
  thread retirement retain their existing contracts.
- All four ResultWorker tests and seven operation/progress tests pass. Consumer
  checks and shared pin/vendor coordination follow before this unit is committed.
- The full unrestricted mobile suite passes all 162 files. Native-browser vendor
  synchronization is committed in Blue Hole as `997b837`; deferred architecture
  reference coverage is committed in Logistics as `821f0e3a`.

## Resumed execution: complete binary stream writes

- Reproduced silent truncation after short writes, successful completion after
  invalid write counts, and a would-block read incorrectly treated as EOF.
- The shared bounded copier now completes each chunk across short writes, checks
  cancellation between those writes and rejects nonprogress/invalid results.
  `None` from blocking read/write adapters raises BlockingIOError without spinning.
  Progress retains its existing completed-read-chunk byte units; normal full-write
  calls still receive the original bytes object.
- All seven stream tests pass. Five archive test files, ZIP access, seven download
  tests and seven Blender integration test files pass; only private fixtures were
  used. Supported ordinary/ZipCrypto/AES and filesystem outputs retain behavior.
- The worker follow-up full shared suite passes all 179 files; full unrestricted
  desktop and mobile runs pass 179 and 162 files respectively. Worker-specific
  validation additionally passes 26 IDE tests, six repository-tab tests, four
  actual-vendor result-worker tests and seven actual-vendor progress tests.

## Resumed execution: synchronous recovery close failures

- Two new tests reproduced first-close deferral with no pending checkpoint future
  after capture failure, and an escaping executor-submission RuntimeError.
- Recovery now marks a close as pending only when a future exists. Synchronous
  failures return to ordinary Save/Discard/Cancel immediately, keeping the draft;
  asynchronous checkpoint behavior is unchanged.
- All 12 recovery tests and 18 ordinary editor tests pass. Stream source/pin
  checkpoint: Logistics `91fa93f5`; Blue Hole exact vendor `f0ac6b4`; shared stream
  implementation `8a68cdf`. Shared worker correction is `c4d3dfc`.

## Resumed execution: verified cross-volume moves

- Four new regressions reproduced corrupt copied bytes accepted before deleting
  originals, a changed source published/deleted by low-level File moves, and a
  clipboard source edit lost after destination publication. A fifth regression
  verifies low-level late edits retain both copies with published-state metadata.
- Added a shared copy-content inventory under the existing snapshots owner:
  byte hashes, object kinds and raw symbolic-link targets, including empty folders.
  It permits hard-linked file contents while the existing strict private-tree
  inventory retains its rejection policy. Existing file_revision calls preserve
  default behavior; an explicit follow_symlinks=False checks the link itself.
- Cross-volume clipboard and low-level File moves now verify staging and recheck
  source revisions before deletion. Clipboard revisions include ctime. Their
  different collision/replacement policies, raw link meaning and between-item
  cancellation remain intact. Publication followed by a source conflict retains
  both copies and reports incomplete cleanup. These checks are not writer locks.
- Validation passes: six snapshot tests, 17 clipboard-transfer tests, 11 File-move
  tests, shared transfer-phase tests, 26 actual browser file-action tests, 58 comic
  tests and the mobile collection consumer. Correctness lint and five documentation
  contract tests pass. EXDEV and late-edit cases use synthetic temporary fixtures;
  native Windows/Linux and physical-volume testing remain separate.

## Resumed execution: relocation cleanup admission

- Two more regressions reproduced storage relocation deleting a file edit or
  retargeted root link after the destination had been published.
- Directory cleanup now repeats the existing manifest validation immediately
  before removal. Root-link relocation checks the link object's captured revision
  before unlinking. Both use the existing published/incomplete result boundary,
  preserving both locations on an observed conflict. Rebased link meaning and
  migration collision policy are unchanged.
- All nine relocation tests, 39 LocalCrypt consumer tests and correctness lint
  pass. Cross-volume copy/source verification was committed as shared `4a6f241`.

## Resumed execution: empty recovery errors

- A failed Future with an empty OSError message reproduced clearing the recovery
  failure flag and scheduling another checkpoint/automatic suspension attempt.
- Recovery error presentation now supplies a nonempty fallback message, preserving
  failure state and the ordinary close prompt without exposing new error details.
- All 13 recovery tests and 18 editor tests pass. The committed filesystem cleanup
  revision `6c20833` also passes the full unrestricted 179-file shared suite, exact
  vendor comparison, 31 Blue Hole tests and the actual-vendor snapshot/transfer/
  move/relocation suites.

## Resumed execution: legacy object/provider boundary consistency

- New fixtures reproduced File copy/move/deletion/permission methods bypassing
  host-managed provider roots, Directory deletion bypassing protected descendants,
  and denied rename creating a parent directory before the existing path guard.
- Those legacy object methods now call the existing namespace-local access guard
  before mutation. Directory preflight covers descendants before sibling deletion;
  File rename preflights before creating parents. Existing provider-record grants
  and unregistered-path behavior remain unchanged. This is routing policy, not
  a new filesystem sandbox.
- Four local-access tests (with per-operation cases), six object-operation tests,
  11 file moves, link creation, File Tools, 58 Comics tests and 39 LocalCrypt tests
  pass. No user storage or credentials were opened; all mutations used fixtures.

## Resumed execution: literal executable permission paths

- Three regressions reproduced shell-expanded filenames, use of a shell command
  string and ignored chmod failures. The permission helper now passes an absolute
  path through argv with shell=False, preserving native +x/umask behavior and the
  prior idle timeout. Failed command results raise OSError.
- Native POSIX tests use a synthetic filename containing quotes and a harmless
  substitution expression; its literal file receives the expected permissions
  with all non-executable bits and bytes preserved. Relative option-like names
  are also covered. Perforce's 24 shared tests and seven Blender integration
  test files pass. No real Perforce server or Blender runtime was used.

## Guard compatibility correction

- Compatibility review caught a regression introduced by the legacy-object guard:
  resolving a cyclic directory link blocked deleting that unregistered link even
  with no active provider policy. The guard now returns immediately when no roots
  are registered, preserving ordinary filesystem behavior without unnecessary
  resolution. All five access tests pass, including the reproduced loop case;
  existing link-creation checks pass with their native Windows-only skip.

## Resumed execution: Git settings lost-update protection

- Three new tests reproduced stale bookmark overwrite, clobbering preferences
  created after an initially missing file, and silently recreating an externally
  deleted file. The writer now checks its loaded bytes before independent INI
  changes and during JSON publication, advancing the baseline only on success.
- A compatibility test caught stale baselines in the existing settings fanout.
  Saved-state adoption now belongs to Preferences and moves the existing fields
  and byte baseline together; UI fanout no longer duplicates field assignments.
- All 16 Git preference/backend/UI tests pass, including retained views saving
  after a settings update. Existing JSON shape, newline behavior, malformed-file
  protection and credential rules remain intact. INI/JSON are still independent
  writes, and external writers can race after the last optimistic check.
- The latest shared boundary/permission revision `9c2f420` passes all 179 shared
  files in one unrestricted run and exact vendor comparison; 31 Blue Hole consumer
  tests pass. No remote push or release has occurred.

## Continued execution: local export provider boundaries

- Two regressions reproduced local document export publishing directly into a
  host-protected provider root, including a root registered during copying.
- The existing path guard now runs before source access and before publication.
  Denial preserves the selected file and removes only the export's own stage.
  Existing successful overwrite and failed-copy behavior remain covered.
- Shared `0e25281` passes all six document-export tests, the 25-file native suite
  with Toga's dummy backend and correctness lint. Consumer picker (5), editor
  picker (7), screen privacy (15) and LocalCrypt UI (3) tests pass. The preceding
  full mobile run completed all 162 files with zero failures.
- Logistics `51691705` pins that revision; Blue Hole `0a67b2b` vendors its exact
  bytes and passes all 31 consumer tests. Actual Android/iOS pickers remain
  outside host validation. Git settings changes were committed as `357af455`,
  the preceding shared pin as `8a4a86f2`, vendor as `f8881cb`.

## Continued execution: IDE checkpoint baseline and size consistency

- Two regressions reproduced an IDE save adopting another writer's bytes after
  publication and saving a checkpoint too large for its own reader to reopen.
- The writer retains its own published bytes as the next conflict baseline and
  checks the same 4 MiB byte limit as the reader before staging. JSON schema and
  formatting remain unchanged; concurrent edits still use optimistic checks.
- All 28 IDE tests pass after the fixes; correctness lint and the existing
  architecture policy pass without added dependency exceptions.

## Continued execution: provider stream ownership

- Two regressions reproduced a nonblocking read being treated as EOF during
  local creation and verification. One fixture published corrupted staged bytes
  as a supposedly verified empty save. Local creation now calls copy_stream;
  verification uses iter_chunks with the same cancellation/error contract.
- Shared `00c11e5` passes all 13 provider-operation tests in desktop and mobile
  environments, four shared resource test files, mobile resource-import tests
  and focused LocalCrypt consumers (one case requires the native bridge and
  remains skipped). Existing destination and stage cleanup semantics remain.
- Logistics `3a7300a6` pins the revision; Blue Hole `2040abb` vendors it exactly
  and passes all 31 consumer tests. IDE checkpoint fixes are `86ee872b`.
- A fresh package contains 2,217 source files plus generated identity and install
  manifests. All 2,218 content hashes were verified, with correct root revision,
  required lazy browser presentation, and no local evidence or external emulator.
  All 25 build-script tests pass with one Windows-only skip; publishing is mocked.
- Doctor, dependency compatibility, toolchain, source hygiene and architecture
  checks pass. Full desktop/shared suites are in progress at this checkpoint;
  their completion is recorded separately rather than assumed.

## Continued execution: shared INI publication consolidation

- INI saves duplicated staging/flush/fsync/permissions/replacement/cleanup and
  bypassed host provider boundaries for existing files and new parent directories.
  The format owner now delegates publication to atomic_write_bytes while retaining
  INI parsing, BOM/newline handling and byte-conflict policy. The shared writer
  also verifies staged contents before replacement.
- All nine INI tests pass in both Python environments, including new boundary and
  mid-stage external-write fixtures. Seven shared settings files, three Logistics
  settings tests and three configuration migration tests pass. Lint/architecture
  pass; no new dependency or JSON/INI format was introduced.
- Shared `9518d82`, Logistics pin `4b4704c3` and Blue Hole vendor `08ae869` are
  committed. Vendor membership/bytes match and all 31 Blue Hole tests pass.
- The preceding full shared run at `00c11e5` completed all 179 files with zero
  failures. The later INI change received the focused coverage above.

## Continued execution: bounded mobile transfer record loading

- A fixture grew a valid record beyond 4 MiB after metadata preflight; the old
  reader admitted it after an unbounded read. Actual reads now stop at the shared
  limit plus one byte and preserve/reject oversized records without admitting jobs.
- All 29 transfer job tests and 14 mirror UI tests pass; committed as `63ce436b`.
- A new full mobile run passed 160 of 162 files; two were blocked by sandbox denial
  of their temporary loopback HTTP listener. Both passed unrestricted reruns
  (15 chat UI tests and one complete mobile workflow). These are environment
  failures followed by passing reruns, not a single unrestricted all-green run.

## Continued execution: late Bulk Rename tree layouts

- Full desktop verification completed 179 files with one failing file: Bulk
  Rename navigation intermittently lost the selected folder after a later model
  layout. A standalone 19-test rerun passed, but diagnostic repetition reproduced
  two failures in eight attempts. Evidence showed a valid selected row far outside
  the viewport after the initial reveal had already retired.
- Model sorting/insertion now remembers whether the selection was visible and
  defers a visibility correction until layout settles. It does not expand collapsed
  branches or follow an already offscreen selection; hidden/closed widgets skip
  correction. The existing initial reveal remains responsible for navigation.
- All eight diagnostic repetitions and all 20 tests pass. The final fixture uses
  owned sibling folders rather than host directory counts, and fresh indexes
  after asynchronous sorting. Lint, architecture and five documentation checks
  pass. The full desktop failure and subsequent focused repair remain in the
  record; a full-suite rerun is separate validation.

## Bulk Rename layout owner and deterministic regression

- The second full desktop run completed 179 files with one failure in the new
  regression's asynchronous filesystem sibling setup; the original navigation
  case passed. No timeout increase or assertion removal was used.
- Deferred layout ownership now belongs to a private _FolderTree view in the
  existing widget module. Its regression uses an in-memory Qt item model to verify
  visible-selection restoration, manual scrolling and collapse preservation,
  independently of filesystem watcher timing. Hide retires its deferred timer.
- All 20 Bulk Rename tests and eight real-filesystem navigation repetitions pass
  after that extraction. The original race had failed two of eight repetitions.
  A new full desktop run is separate from those focused results.

## Complete bounded text reads and measured-stream integrity

- A short-read provider fixture reproduced admitting only the first two bytes of
  a complete text file as an editable baseline. ResourceTextSession now reads
  through short reads to EOF or its byte ceiling plus one, then applies its
  existing total editing limit and source revision checks.
- Shared read_up_to owns that bounded prefix mechanism; ten stream tests, five
  selection tests, four shared resource files in the mobile environment and seven
  picker tests in each UI environment pass. Shared `1959963` was pinned as
  Logistics `e29901a6` and Blue Hole vendor `c555097`; exact vendor and 31 consumer
  tests pass.
- Measured reads also reproduced hiding would-block as EOF and turning an
  oversized result into an unlimited read. They now reject both while retiring
  the progress scope and leaving source ownership unchanged. Six progress tests
  pass in each environment, plus seven mobile file-loading and five notes/library
  tests. Shared `6a9bcd4`, Logistics `3e696e46` and Blue Hole `e81bd7b` are committed;
  exact vendor and all 31 consumer tests pass. A fresh full shared run is underway.

## Committed verification isolation and bounded Git staging checks

- Shared `6a9bcd4` completed all 179 files with zero failures in the new full run.
  Bulk Rename ownership extraction is committed as `89d2cfd6`.
- A full desktop run picked up an intermediate Git test fixture while its macOS
  resolved-path spy was being corrected. The corrected seven-test merge suite
  passes; the new bound regression fails against the previous committed method
  loaded in memory, without reverting the working source.
- Optional conflict staging now reads only the expected saved byte count plus
  one after rechecking index entries. A changed/enlarged result remains untouched
  and unstaged. Committed as `96d38b79`; lint, architecture and docs checks pass.
- Broad verification now uses a managed checkout frozen at `96d38b79`, with an
  independent local clone pinned to shared `6a9bcd4` and the existing desktop/mobile
  interpreters. No remote fetch or dependency installation was needed. This keeps
  ongoing source edits out of test discovery and exercises a checkout without the
  external emulator. Full desktop and mobile runs are underway there.
- Only the verification checkout's two environment symlinks are untracked; its
  tracked source and shared clone are clean. Logs remain with ignored main-checkout
  evidence. Retire this owned checkout and clone after its validation is saved.

## Notes Library complete preview reads

- Short provider chunks reproduced both a truncated Markdown preview and admission
  of a note exceeding the total preview limit. NotesLibrary now uses read_up_to
  with its existing maximum plus one, retaining its post-read size, revision,
  cancellation and UTF-8 checks. No extra cache or discovery was introduced.
- Six desktop Notes Library tests and five mobile Notes Library tests pass, along
  with lint, architecture and five documentation checks. Committed as `13ce06fb`.
- Immutable mobile verification at Logistics `96d38b79` / shared `6a9bcd4` completed
  all 162 files with zero failures in one unrestricted run. The later Notes change
  has the focused coverage above. Immutable desktop verification is still running.
- The source package rebuilt at `13ce06fb`; all 2,218 manifest content hashes and
  its root revision verify, with external emulator and local evidence exclusions.

## UTF-8 archive preview boundaries

- Six fixtures reproduced valid multibyte text being rejected when the 256 KiB
  preview ceiling split a character. Incremental strict UTF-8/BOM decoding now
  retains the complete prefix and truncation notice, omitting only a pending
  boundary character. Invalid bytes within the preview and incomplete complete
  files still receive the existing unsupported-text fallback; a BOM case is covered.
- All 21 shared archive tests and 13 Logistics archive UI tests pass in the
  desktop environment. The mobile interpreter passes 17 archive cases, including
  the new regressions; four encryption cases error because its environment lacks
  optional pyzipper. This is not reported as a green 21-test mobile result, and
  no dependency was added to that environment.
- Shared `8e32471` is committed. Exact Blue Hole vendor membership/bytes and all
  31 consumer tests pass. Documentation checks and correctness lint pass.

## Native tool availability in the committed verification tree

- Immutable desktop verification completed 179 files: 178 passed and the rclone
  review file failed because the new checkout lacked the already-installed native
  binary. Several other files skipped their native rclone cases for that reason.
- A cross-checkout tool link was rejected by the existing software containment
  guard. That guard was preserved. An owned copy of the installed binary was
  placed inside the verification tree and its SHA-256 compared with the original;
  no download or user configuration change was required.
- All 17 rclone review tests then passed. The eight other files with native rclone
  skips were rerun and all passed: Folder Sources UI, LocalCrypt, LocalCrypt file
  operations, rclone progress, push policy, sessions, structured UI and Remote
  Browser. Native-bridge/platform skips remain distinct. This is a full run plus
  repaired-environment reruns, not a claimed single all-green desktop run.
- Broad source verification remains frozen at `96d38b79` / shared `6a9bcd4`;
  subsequent Notes, archive and JSON changes receive their recorded focused checks.

## JSON publication consolidation

- Two fixtures reproduced JSON writes bypassing provider boundaries for existing
  files and missing parents. JSONFile now serializes/encodes first and delegates
  staging, verification, permissions, replacement and cleanup to atomic_write_bytes.
  Native text newlines remain explicit, including Windows CRLF behavior; actual
  Windows execution remains outside this host validation.
- All five JSON tests pass in desktop and mobile environments, including existing
  malformed/BOM/Unicode/serialization/failure contracts. Cleanup assertions now
  inspect all stage-directory contents, rather than only a .tmp filename pattern.
  All 16 comic catalog tests pass after targeting fault injection at the atomic
  owner. Lint and five documentation checks pass.
- Shared `cfdad79` is committed; exact Blue Hole vendor bytes and all 31 consumer
  tests pass. The main worktree remains separate from the immutable test checkout.

## XML publication consolidation and destination revalidation

- Three fixture cases reproduced XML exports bypassing provider boundaries and
  replacing a symlink created after the writer's initial check. XMLFile now
  delegates publication to atomic_write_bytes and rechecks its explicit symlink
  refusal before publication. Serialization, no-op bytes, DOM metadata, export
  identity and existing mode policy remain owned by XMLFile.
- All 15 XML tests pass in desktop and mobile environments, including late-link,
  provider, malformed DOM and export identity cases. All 58 Comics tests pass;
  lint and five documentation checks pass. Temporary cleanup assertions inspect
  complete directory contents rather than the former stage-name pattern.
- Shared `aa5bcae` is committed; Blue Hole vendor bytes match exactly and all
  31 consumer tests pass. JSON pin/vendor commits are Logistics `463b728a` and
  Blue Hole `4ba794d` respectively.

## Legacy text export destination permissions

- New fixtures reproduced alternate-path text exports making the source writable,
  failing on a read-only destination, and writing through a protected destination.
  TXTFile now prepares the selected output's permissions, preserving the source;
  in-place saves retain subclass dispatch. TXT/CSV guards run before parent mkdir.
- A CSV fixture also reproduced creating a nested directory before denial; that
  empty-directory mutation is now prevented. Streaming, native newline, link and
  existing in-place write behavior remain intact; no blanket atomic migration or
  whole-file buffering was introduced for these legacy APIs.
- All 12 file-object tests pass in both environments, plus five local-access,
  string-table, three settings and nine layered-settings tests. All 58 Comics and
  five native rclone session tests pass. Lint and docs checks pass.
- Shared `c1eb35a` is committed, with exact Blue Hole vendor and 31 consumer tests
  passing. XML pin/vendor commits are Logistics `53082958` and Blue Hole `30907e9`.

## Legacy text encoding admission before mutation

- Two fixtures reproduced an invalid Unicode surrogate on a later text line
  truncating existing output after writing a prefix and changing read-only mode.
  TXTFile validates UTF-8 before parent creation, permission preparation or opening
  the destination, retaining its existing in-place streaming/newline behavior.
- All 13 file-operation tests pass in desktop and mobile environments, including
  source/alternate output and permission preservation. Nine layered-settings and
  all 58 Comics tests pass. Lint and documentation checks pass.
- Shared `8086ff6` is committed; exact Blue Hole vendor bytes and all 31 consumer
  tests pass. The preceding legacy export pin/vendor commits are Logistics
  `034e11ed` and Blue Hole `9f9383b`.

## Complete-tree archive extraction provider boundaries

- Two fixtures reproduced extracting plaintext into a managed provider root,
  including one protected during the final copied file. Complete-tree extraction
  now checks its recursive destination before creating parents and immediately
  before publication, cleaning only its own stage on denial.
- All 23 shared archive tests and 13 archive workspace UI tests pass. Lint,
  architecture and five documentation checks pass. Shared `04a94e3` is committed;
  exact Blue Hole vendor bytes and all 31 consumer tests pass.
- The later text-encoding pin/vendor commits are Logistics `b2d3d768` and Blue Hole
  `5c86f3d`. The existing provider boundary remains application routing policy,
  not an OS sandbox or a new global restriction on arbitrary third-party I/O.

## Read-only software metadata and explicit native test availability

- A fixture reproduced executable metadata lookup creating both Software and
  Credentials directories in an otherwise untouched checkout. LogisticsConfig
  now supports create_resources=False; software lookup uses it, while existing
  no-argument callers retain default directory creation. No path or INI schema
  changed. Committed as `eee80a80`.
- All 12 software tests, five credential-discovery tests and 17 native review
  tests pass, plus lint, architecture and five documentation checks.
- Four real-CLI review cases lacked the file's existing optional-tool guards,
  producing errors instead of declared skips in a fresh checkout. Installed-tool
  validation still runs all 17 cases successfully. A separate missing-tool profile
  runs eight non-CLI cases and explicitly skips nine native cases, without moving
  or disabling the user's installed binary.
- This restores the developer guide's existing local optional-tool policy; skipped
  cases are not reported as native coverage. The original immutable environment
  failures and later installed-tool reruns remain recorded above.

## Batch success admission without unnecessary hashing

- A fixture reproduced successful dictionary items raising TypeError for both
  stop-on-error modes. The runner looked up every successful item in its failure
  dictionary, contrary to its documented hashability requirement only on failure.
- The loop now tracks the current attempt's failure directly. Result shape,
  stop-on-error, between-item cancellation and failed-item key policy remain intact.
- All eight batch/worker/progress tests pass, plus two Dropbox, nine File Tools
  and 23 image-staging tests. The pure batch success profiles also pass in the
  mobile interpreter without importing a UI toolkit. Lint and docs checks pass.
- Shared `199309c` is committed; exact Blue Hole vendor and 31 consumer tests pass.
  Native test availability correction is Logistics `667bc472`.

## Range reader buffer and numeric argument admission

- Typed array buffers used element count rather than byte capacity and then
  failed after consuming data. Read-only buffers likewise advanced the reader
  before rejecting assignment. RangeReader now validates and views writable
  buffers as bytes before reading, retaining existing strided byte-view support.
- Separate standard-I/O comparison fixtures reproduced float offsets/counts
  changing position, fetching data before failure or reading an entire source.
  Integer conversion now occurs before source access or position changes.
- All 12 browsing/range tests pass in both environments, with standard BytesIO
  comparisons, no-fetch failure checks and explicit strided-view preservation.
  All 12 desktop PDF and 15 mobile remote-reader tests pass. Lint and docs pass.
- Shared `7978a28` is committed; exact Blue Hole vendor bytes and all 31 consumer
  tests pass. The preceding batch pin/vendor commits are Logistics `403a0ac1` and
  Blue Hole `ee710aa`.
- Expanded read-only Blender discovery checked PATH, both application folders and
  the OS application index; no executable/bundle was found. Native Blender 5.2.2
  registration remains unverified. No application was downloaded or installed.

## Bounded IDE conflict validation and immutable verification

- A new fixture reproduced the workspace's conflict validator reading an entire
  externally enlarged file before rejecting it. Loading and save validation now
  use the shared bounded reader, preserving the 4 MiB policy and original bytes.
- The new regression failed before the repair; all 29 IDE tests pass afterward.
  Lint, architecture and all five documentation checks pass. Committed as
  `f9ec2519`; the later frozen full run does not include this additional fix.
- Frozen Logistics `07e76ab2` with shared `7978a28` passes all 162 mobile and
  all 179 shared isolated test files. Desktop validation is still in progress.
  The source tree being validated was not edited during either completed suite.

## Read-only location lookup and PDF worker admission

- Location labels and local-connection root lookup reproduced the same unrelated
  Software/Credentials directory creation as software metadata lookup. Both now
  select the existing no-creation configuration mode. The default constructor and
  folder initialization workflows retain their behavior. Committed as `e0a56193`.
- Both new lookup profiles failed before the change. All 13 software, five location
  and 39 real-rclone local-crypt tests pass after it, with lint/architecture/docs.
- PDF search worker submission failure escaped into the GUI callback and left
  navigation controls disabled. Busy state is now published only after submission;
  expected startup errors remain visible and retryable, including empty messages.
- The two startup-error profiles failed before repair and retry real extraction
  afterward. All 13 desktop PDF and two mobile PDF tests pass, plus lint,
  architecture and documentation checks. Committed as `3f197f23`.

## Immutable full-suite checkpoint

- Unedited Logistics `07e76ab2` and pinned shared `7978a28` pass all 179 desktop,
  162 mobile and 179 shared isolated test files. Test totals include skipped cases:
  desktop 1,654 with six skipped; mobile 1,161 with two skipped; shared 1,212 with
  25 skipped. Zero failing files in all three suites.
- Desktop skips require rebuilt optional native mobile/cloud bridges. Mobile skips
  require Node/Playwright. Shared skips cover unavailable desktop Toga, Windows
  readers/junctions and a case-sensitive filesystem. These are not passing native
  platform coverage. Real rclone is present in the frozen checkout and its review
  suite executes rather than skipping for missing software.
- Subsequent IDE bounds, location lookup and PDF startup fixes have the focused
  validation above; these full-suite totals do not include those later changes.
- A narrower static import inventory excludes function bodies and TYPE_CHECKING
  branches: Logistics has zero module-scope candidate groups, shared has two and
  Blue Hole three. Package-facade bootstrap references are still included. Shared
  candidates are its intentional Qt facade and command package submodule imports;
  Blue Hole candidates span pie/action declarations and environment/file helpers.
  This is not proof of eager initialization failure. Native Blender registration
  remains unavailable, so no speculative registration/import rewrite was made.

## Blender publication collision consistency

- Five isolated macOS profiles reproduced replacing an empty destination created
  after preflight: whole-bundle install, preset duplication, preset rename, addon
  import and Blue Hole commit-cache publication. All use the existing shared
  atomic no-replace rename now; cooperative locks and owned staging remain intact.
- All 94 tests across seven Blender files pass, including preservation/cleanup in
  each race. Network responses, DMG calls and Blender launch are fixtures; no real
  Blender was downloaded, installed, launched or removed. Lint, architecture and
  all five documentation checks pass. Committed as `b4550300`.
- Latest shared `7978a28` also passes all 106 tests in 25 native Toga test files
  through the mobile interpreter/dummy backend. This covers the optional toolkit
  profiles skipped in the desktop shared suite, not real-device UI behavior.

## Personal configuration reset recovery ownership

- Two fixtures reproduced reset cleanup deleting an externally published
  configuration directory: after publication failure, and after replacement of
  the reset's directory during runtime activation. Reset now uses no-replace
  backup/publication/recovery and records the identity of its own published tree.
- Rollback removes only that identity. A different directory is retained and the
  original settings stay in the existing named recovery backup. Success also
  verifies directory identity before discarding that backup. Migration metadata
  is not rewritten when publication never succeeded. Junctions join symlinks in
  the existing admission guard; native Windows junction execution is unverified.
- Both failure regressions failed before repair. All ten reset tests, three service,
  28 settings UI and three migration tests pass, plus lint, architecture and five
  documentation checks. Committed as `544116f1`.
- This is optimistic directory-identity validation, not cross-process locking or
  attribution of concurrent writes inside the same published directory. Backup
  naming, data/configuration ownership, schemas and normal reset behavior remain.

## One native exclusive-rename owner

- Filesystem rename duplicated the persistence owner's platform FFI setup, with
  different missing-symbol and diagnostic behavior. Its provider guards and
  private batch hook remain; the native call delegates to publication now.
- Eight platform/entry-point profiles reproduced AttributeError when a native
  symbol was missing. Both owners now raise OSError(ENOTSUP) before mutation,
  retain destination diagnostics and explicitly declare the C result type.
- All ten persistence tests pass in both environments, plus bulk rename (one
  case-sensitive-filesystem skip), five access, 17 file-operation, nine relocation,
  13 resource-operation and 23 archive tests. Three host rename files and all 94
  Blender manager/library tests pass. Lint and architecture checks pass.
- Shared `eb757e5` passes all 179 isolated test files from a separate immutable
  export. Blue Hole's exact vendor membership/bytes and all 31 consumer tests pass.
  Pin/vendor commits are Logistics `a0234886` and Blue Hole `5c5b522`.
- Android's official libc header introduces renameat2 at API 30. Missing support
  already prevents guaranteed no-replace operations on older runtimes; no unsafe
  fallback or raw syscall guess was added. The separate legacy mobile collection
  copy publication was not migrated without native older-Android evidence. Shared
  API limitations are documented in their owning reference, not copied here.

## Available older Blender and reusable embedded checks

- Expanded discovery of Logistics-managed software found Blender 4.5.1 LTS;
  --version confirms that release. Earlier application-folder/PATH checks did not
  find it. No compatible 5.2.2 executable has been found.
- Added a reusable Blue Hole smoke-test launcher with temporary user resources,
  background factory startup, blend autoexecution disabled and isolated shared
  storage. It imports the real vendor under an independent namespace, without
  registering the target add-on or opening/saving user projects/preferences.
- All five smoke tests pass in actual Blender 4.5.1 / embedded Python 3.11.11:
  portable imports, short streams/typed range buffers/batch success, native rename
  preservation, ZIP/JSON publication and captured Blender version subprocess.
- These are portable embedded-runtime checks, not target 5.2.2 registration,
  operator/UI/export validation or a new claimed Python support range. The driver
  and guide are committed in Blue Hole as `2108b3f`.
- Frozen Logistics `bdb7c28d` / shared `7978a28` now passes all 162 mobile files;
  all 179 desktop files pass too. This checkpoint includes the later settings
  and Blender repairs but precedes the shared rename-owner consolidation.

## Native browser queued-work retirement

- Two regressions reproduced accepting a new task after stop and raising on a
  closed supplied loop while leaving an open coroutine. Admission now closes
  unscheduled coroutines and returns None for either retired state. Existing
  running tasks remain retained until close; prepared-tree reuse stays supported.
- All seven lifecycle cases pass (two optional Toga skips in desktop), and all
  108 tests in 25 native Toga files pass through the mobile dummy backend. All
  21 mobile folder-navigation and 15 screen-privacy tests pass. Lint/architecture
  checks pass. Shared `c61e24b` is committed.
- Exact Blue Hole vendor verification and all 31 adapter tests pass. Its five
  actual embedded smoke tests also pass on Blender 4.5.1 / Python 3.11.11, now
  exercising retired admission and valid lifecycle reuse. Vendor/driver commit
  `0f070b6`; Logistics pin `21aa3b9c`.
- Complete frozen checkpoint totals: Logistics `bdb7c28d` has 1,664 desktop tests
  (six native-bridge skips) and 1,161 mobile tests (two Node/Playwright skips),
  across 179/162 files with zero failures. Shared `eb757e5` has 1,213 tests across
  179 files, zero failures, 25 declared platform/toolkit skips. The later lifecycle
  guard has the focused/native validation above, not a claimed new full run.

## Cohesive Bulk Rename widget construction

- Constructor construction mixed folder/filter controls, browser/rule panes and
  progress/preset/apply controls. Three private builders now name those sections
  within the same widget/module, without new files, public APIs or state layers.
- An AST comparison expands the builders back into initialization and verifies
  the exact original statement order. The constructor is 31 lines instead of 226;
  this reduction reflects named responsibilities, not deleted controls or behavior.
- All 24 tests across three host rename files pass, including 20 Bulk Rename UI
  cases, plus lint, architecture and all five documentation checks. Existing
  selection/reveal, preview, apply/undo, presets and cooperative-close checks remain.
- Committed as `656347ae`; the focused suite covers this later refactor,
  not the earlier frozen full-suite checkpoint. No extra mirror tests were added
  for this reversible organizational change.

## Recovery envelope admission before mutation

- Six invalid-envelope profiles reproduced overwriting a readable checkpoint with
  data that SessionStore's existing reader rejects, or creating a new directory
  for such a save. The version/documents/count admission now has one private
  owner shared by read and write, before write-side directory creation.
- Nested document fields remain host-owned. JSON escaping, NaN policy, bytes,
  64 MiB bounds, durable publication, private permissions and formats are intact.
  The API map now distinguishes the store's existing envelope from host schema.
- All four store tests pass in both environments; all 13 editor recovery and 28
  document workspace tests pass. Lint, architecture and five documentation checks
  pass. Shared `3ba394b` is committed, Logistics pin `386c79c5`.
- Blue Hole exact vendor membership/bytes and all 31 adapters pass; its five actual
  embedded tests also exercise valid/invalid recovery writes on Blender 4.5.1 /
  Python 3.11.11. Vendor/driver commit `9d22aba`.
