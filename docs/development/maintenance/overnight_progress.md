# Ecosystem maintenance progress

## Sequential audit implementation: C4 Markdown presentation and conversion

Shared `c542e92` separates fragment classification, inline/fenced-code typography
and image leading from the existing quote-depth traversal. Authored-source
conversion names inline planning and fence materialization while retaining reverse
replacement order. Expanded AST matches every original ordered statement and
signature in both entry points. All 148 Markdown cases across 14 files pass
before/after in identical order; Notes six, IDE Markdown three, Ally 48 and Blue
Hole two current-source contracts pass. Shared wiki, configured lint and whitespace
pass. No source/undo/persisted/API change, external consumer edit or push occurred.
L4 source work was not started: concurrent rclone/LocalCrypt changes also touch
`files_ui.py`; its initial folder baseline failure was in the concurrent adapter's
missing fixture generation, subsequently being updated by that work. It remains
outstanding until that editing boundary is stable.

## Sequential audit implementation: L3 provider draft and library publication

`ProviderView` replaces the anonymous construction namespace with explicit
adopt/discard ownership. A real failed-build regression first reproduced an active
unpublished CodeInput, then passes with partial construction and veto cleanup.
Reader-source ownership remains with the opener/supplying workflow. Tests cover
acquired versus prepared sources, preserved current readers, cleanup failure and
idempotence, successful adoption and a post-adoption neighbor failure. Library
EPUB preparation and chapter/bookmark projection are named inside ReaderUI;
expanded AST matches every original ordered page-publication statement/signature.
All 71 reader cases across 12 files pass before/after with identical selection;
private sessions, remote readers, PDF, publication, EPUB/comics, provider contracts,
staged startup, architecture, lint and wiki checks pass. Native rendering remains
separate acceptance. No external consumer changes, persisted format changes or push.

## Sequential audit implementation: L2 frame and drawer ownership

`file_drawer.py` now owns the existing retained browser implementation and widget
detach helper; navigation retains routes, drawer references/open state, paired
selection and frame layout. Existing imports remain available through navigation.
All classes/functions/signatures match their original AST, with no new state or
native toolbar changes. The curated mobile manifest includes the new module.
All 32 navigation and ten delayed-listing cases pass before/after, including
rotation, retained widgets, private credentials and stale results. Fold, route,
Android chrome, staged startup, packaging, architecture, lint and wiki checks pass.
Native pose validation remains separate. No external consumer edits or push.

## Sequential audit implementation: L1 managed-document workflows

`ManagedDocumentWorkflows` groups 15 existing create/open/save/inventory/preview
and import/export callbacks. All moved methods and retained app members match
their original AST; startup, retained factories, scene publication and aggregate
checkpoint guards stay in the app. No additional state owner, forwarding layer,
persisted format or callback signature is introduced. The curated mobile manifest
includes the new module. New original/refactored tests cover import completion
after switching and export completion after closing its origin. Document,
checkpoint, picker, privacy, workspace, secondary-window and staged startup
contracts pass, as do packaging, architecture, lint and documentation checks.
These are host contracts, not new native-device acceptance. No external consumer
changes, deployment or push occurred.

## Sequential audit implementation: C2 browser policy and retirement

Network/watch-set/revisit/notification callbacks move unchanged into the existing
BrowserIndexing mixin; FileBrowser retains inherited callbacks and overall close
coordination. Close and idle now use the same original admission expression.
A blocked details-worker regression passes before/after and rejects publication
after stop while retaining the running worker. All 107 browser cases across 12
files pass in identical order; Logistics browser/controller checks pass 19/2,
real watcher checks 12 and external compatibility 48/2. Exact method/body/signature
comparison, lint, shared wiki and whitespace pass. No external consumer edit,
public API/persisted change or push occurred.

## Sequential audit implementation: C3 workspace transfer

Workspace adoption now captures an immutable transfer snapshot and names acceptance
and rollback, with guards/flags/signals/cleanup retained in `adopt` (85 → 55 lines).
Header refresh separates dock and tab-bar projection (87 → 9 orchestration lines).
Capture evaluation order and every original statement/signature match after
expansion. A new original/refactored regression covers failures after arrangement
and lost destination registration, checking order, active views, signals and flags.
All 67 workspace cases pass before/after; Logistics document/main-window consumers
pass 28/34 cases, Ally 48 and Blue Hole two compatibility cases. Lint, shared wiki
and whitespace pass. No external edits, persisted layout/API changes or push.

## Sequential audit implementation: C1 index reconciliation

Shared `17978f2` names target selection, bounded descendant validation and replaced
record retirement inside the existing module. The transaction entry point is 85
rather than 136 lines; generation admission, active writer state, rollback/commit
and snapshot publication retain their ownership. Expanded AST matches all original
ordered statements and signatures. All 151 index cases across 17 files pass in
identical before/after order, plus the Logistics index-service case, Ally's 48
contracts and Blue Hole's two current-source namespace contracts. Shared wiki
checks, configured lint and whitespace pass. No schema/API or external-consumer
change, deployment or push occurred. C1 is committed before starting C3.

## Sequential audit implementation: T2 owner selections

Expanded specialist selections for nine archive/reading/chat/provider/storage
owners, retaining registry coverage and existing command behavior. Overlapping
patterns are deduplicated; invalid suite keys now fail instead of silently using
the mobile folder. All declared patterns resolve. Ten architecture/ownership
contracts, the complete expanded archive owner group and configured lint pass.
The remaining audit units are still open; this entry does not mark them complete.
No shared or external-consumer source changes, deployment or push occurred.

## Deterministic lint scope and shared test matrix

Logistics `75395cc0` implements audit T1 and the shared-matrix part of T2 on the
current branch. Ruff retains its default exclusions and explicitly omits mobile
build/payload/log/deployment/toolchain trees and the optional feature link. In the
build-heavy local checkout, lint selection falls from 4,028 to 1,705 files: exactly
all 1,703 tracked Python files plus two project TOMLs. A disposable fixture proves
that generated invalid Python is excluded while new untracked source is selected
and fails lint when invalid. CI and local lint keep the same roots and rules.

`dev.py test shared [filename/glob]` runs shared Qt/portable tests in the desktop
environment, then matching `test_native*.py` contracts in the Toga environment.
Both retain file/profile isolation, explicit import paths and exit failures;
missing required toolkit modules fail before discovery. Custom Qt/native
interpreters, dry-run, filename intersection and both-leg failure propagation are
covered. Existing desktop/mobile commands retain their environments and behavior.
The static CI job runs the selection contracts with its pinned Ruff installed;
the lint-specific fixture is explicitly optional in nondeveloper environments
without Ruff. No application dependency or installation flow changed.

The complete new command passes in one permitted invocation: Qt/portable 184
files / 1,260 cases / 25 optional or platform skips; native 25 files / 108 cases /
zero skips. Counts overlap and are not distinct coverage to add together. All 16
command/scope, nine runner and eight architecture-contract cases pass. An actual
wrong native interpreter returns failure for absent Toga as intended. Configured
lint, doctor, architecture, toolchain, documentation and whitespace checks pass.
Hosted CI, Windows/Linux and native-device acceptance were not run; actionlint
was unavailable locally. Real watcher tests used permitted notifications and
isolated storage, without weakening assertions or extending timeouts.

commonUtils remains unchanged at `2cd0516`; Ally Tools and Blue Hole remain clean
and untouched. No push or deployment occurred. Raw reports remain ignored. T2's
broader owner-test selection is still open; C1/C3 transaction clarity and mobile
owner contracts remain subsequent audit priorities.

## Complete remaining-work audit

Assessed clean Logistics `4f78de7d` / commonUtils `2cd0516`, retaining the current
branches. The [current remaining-work audit](remaining-work-audit.md) replaces
historical next-step suggestions as the active backlog: eight shared-library,
ten Logistics and five cross-cutting work items, each with scope and preservation
checks. No production code, shared revision or external consumer changed.

The Git-index inventory covers all 1,703 Python files across the two repositories,
excluding generated/toolchain trees and the optional feature link. Detailed review
concentrates on the ranked owners, transactions, state contracts and their tests;
it is not a claim of exhaustive runtime path verification. A concrete tooling
finding is that configured lint currently selects generated/toolchain copies;
tracked-only optional diagnostics are recorded separately from passing CI rules.

Fresh full host suites were attempted, then every permission-dependent failed
file was rerun successfully using disposable fixtures and the needed host
capabilities. Reconciled results: Logistics desktop 179 files / 1,694 outer cases /
six native-bridge skips; mobile 165 / 1,185 / two DOM skips; shared Qt/portable
184 / 1,260 / 25 optional/platform skips; shared native 25 / 108 / zero skips.
Shared/native overlap is not additional distinct coverage. An initial shared run
in the wrong environment is explicitly excluded from source-regression conclusions.
No unresolved executed-group failures remain; this is not one unrestricted
all-suite run or native acceptance. Doctor, configured lint, architecture,
toolchain, hygiene and Logistics/shared documentation checks pass.

Ally Tools and Blue Hole remain clean and untouched. Their scope is explicitly
limited to changes required by shared import/signature/binding/resource migration;
unrelated refactors or vendor refreshes are excluded. No push, deployment, native
app installation, real remote/collection mutation or release occurred. The audit
sets no numeric ecosystem score and keeps raw evidence outside the public wiki.

## Provider preparation/publication and collection operations continuation

Started from clean Logistics `47cdc198` on `alpha`, with shared `2cd0516` on
`main`. Current branches are retained; no push is authorized.

- Logistics `585abf2e`: provider opening names initial Markdown preview preparation
  and admitted-view publication in its existing module. `open` is 72 rather than
  99 lines, keeping reader acquisition, cancellation checks, view veto, password
  lifetime, remote-source cleanup and busy release visible. The acquired reader
  remains assigned before either page or preview preparation can fail; supplied
  prepared readers retain their existing cleanup policy. Publication still clears
  the previous reader, adopts view fields, selects Markdown presentation, refreshes
  privacy and installs layout observers before comic-neighbor preparation.
- Logistics `d48b1e64`: collection operations name confirmation-text preparation
  and captured progress rendering. `_collection_operation` is 99 rather than
  124 lines. Selected-volume capture, pre/post-confirmation admission, partial
  progress-control cleanup, worker dispatch and restart policy remain in that
  entry point. No operation service or persisted storage marker changes. Progress
  still returns through `call_soon_threadsafe` to controls captured for that job.
- Four new provider contracts pass against original and refactored source:
  preview-error fallback/publication ordering, cancellation during preview,
  acquired-versus-prepared reader ownership after a view veto, and page failure
  after remote-reader acquisition. The new collection regression passes before
  and after across eight action/state combinations: copy/recover/empty/wipe each
  recheck active work and checkpoint success after confirmation, restore controls
  and never invoke the worker when revalidation fails.

Expanding extracted helpers reproduces every original ordered AST statement,
including captured arguments and callback bodies; public signatures and untouched
methods match. No production module, package, dependency, public API or persisted
format changed. The existing mobile runtime guide records these owner boundaries.

| Executed validation | Result |
| --- | --- |
| Original baselines | Existing storage UI 11 cases and provider Markdown 11 cases pass. |
| Added contracts before/after | Four provider methods and the expanded 12-case storage UI suite pass against both versions. |
| Final focused mobile checks | 114 cases across 11 files pass, zero skips/failures: provider opening 4, storage UI 12, private sessions 17, remote readers 15, provider Markdown 11, storage service 24, Android storage 5, collection parity 1, document navigation 8, screen privacy 15, storage reader opening 2. |
| External consumers | Ally Tools 48 tests and Blue Hole two current-source namespace/import/signature/binding checks pass unchanged. |
| Documentation and gates | Five Logistics wiki tests, configured lint, architecture (24 host adapters / 15 feature edges / zero violations), toolchain, hygiene, syntax and whitespace pass. |

commonUtils remains clean and unchanged at `2cd0516`; no library adjustment was
needed for these application workflows. Ally Tools remains clean at `d2c00b8`,
Blue Hole at `665c184` with its vendor unchanged. No compatibility edits were
required. These are isolated host fixtures and synthetic providers, not native
iOS/Android/Boox or Blender validation. No real collection was copied/erased, no
app was installed, and no production data, release or remote branch was changed.
Full suites were not rerun; previous totals retain their recorded source scope.
Raw reports, original source copies and the comparison driver stay under ignored
test results, outside the documentation wiki.

Next candidates are storage-page construction and provider view assembly, after
checking ownership of partially created controls and failure cleanup. Native
adapter changes still need platform-specific validation. No new ecosystem score
is claimed from this bounded pass.

## Mobile lifecycle owner continuation

Started from clean Logistics `9e66f04b` and shared `b425d5d`, on the current
`alpha` / `main` branches. No push is authorized.

- Shared `2cd0516` separates recycled-browser navigation/list construction from
  callback, event-loop and renderer-state admission. Construction is 27 rather
  than 61 lines. List rendering is 23 rather than 41 lines, retaining generation
  invalidation and thumbnail-request reset before a named native row-publication
  phase. Its `updating` guard still encloses records, identity/index maps and
  selection highlighting and is released in `finally`.
- Logistics `e6f5c44c` separates private-controller registration and successful
  document publication from `PrivateSessions.open`. The admission/rollback flow
  is 92 rather than 127 lines. Capacity, checkpoint, workspace token, memory
  budget and remote busy cleanup stay in that entry point; credentials and
  privacy are registered before reading. Publication receives the original
  captured session, reader and identity, restores reading position, records
  permitted history and respects navigation during the asynchronous read.
- A new regression passes on the original and refactored implementations. Its
  rejected-result, exception and invalidated-token scenarios each retire only
  the new owner, release opening state and restore the previous unsaved draft.
  Existing tests also exercise navigation while opening, memory/capacity limits,
  privacy, credential retirement and independent reader/session ownership.

Expanding the private phases reproduces every original ordered AST statement,
including captured arguments, public signatures and all untouched methods. No
production package/module, dependency, public API or persisted format changed.
The shared and Logistics owner guides describe the internal boundaries.

| Executed validation | Result |
| --- | --- |
| Shared browser before/after | Eight cases across two files pass with Toga dummy installed; zero skips/failures. Includes independent consumer, stale rows, bounded tiles/caches and cooperative worker retirement. |
| Private sessions original/new | Original 16-case baseline passes; all 17 cases including the new three-scenario regression pass before/after. |
| Final focused mobile run | 126 cases across 12 files pass; zero skips/failures. Sessions 28, application/reader lifecycle 17, native browser 2, screen privacy 15, credential lists 14, transitions 2, remote readers 15, document navigation 8, provider Markdown 11 and progressive browser 14. |
| Consumer compatibility | Ally Tools 48 tests and Blue Hole two current-source namespace/import/signature/binding checks pass. |
| Documentation | Five Logistics and three shared wiki cases pass. |
| Repository gates | Configured lint, toolchain consistency, source hygiene, architecture (24 host adapters / 15 feature edges / zero violations), syntax compilation and whitespace checks pass. |

Ally Tools remains clean at `d2c00b8`; Blue Hole remains clean at `665c184`, with
its vendor unchanged. Both require no compatibility edits. No UIKit/Java adapter
was modified. These are host regressions using disposable fixtures, not native
iOS/Android/Boox or Blender validation. No app installation, production-data
mutation, release or push occurred. Earlier full-suite totals retain their
recorded source scope; they were not rerun. Raw copies, comparison driver and
reports are local-only under ignored test results.

Next priorities: review provider-document preparation/publication and collection
operations with the same captured-owner and failure-path discipline. Native
navigation and appearance construction remain candidates only with relevant
platform validation. This bounded pass does not establish a new ecosystem score.

## Qt resource browser and editor Save/Save As continuation

Started from clean Logistics `9ee21663` / shared `cd21efe` on the current
development branches. Ally Tools remains at `d2c00b8`; Blue Hole at `665c184`.
No push is authorized and no external consumer change is required.

- Shared `b425d5d` names navigation, search, provider-view, optional-preview and
  operation-control construction in the existing resource-browser module. The
  constructor retains provider binding, navigation/keyboard connections,
  cooperative owner registration and initial navigation, in 42 rather than 136
  lines. Widget fields, subclass hooks and provider/lifecycle owners stay intact.
- Logistics `1e6c644b` separates overwrite confirmation and captured local
  publication from `save_document()` admission. The 45-line entry point retains
  destination choice/release and private handoff policy; the previous 124-line
  body also held the local worker and completion/failure callbacks. A typed
  optional revision tuple distinguishes confirmed overwrite from cancellation.
  Source snapshots, read limits, conflicts, encoding, callback order and recovery
  policy retain their existing implementations.
- Five new editor contract methods pass against the original code before the
  refactor and after it. They cover two read-only states, picker/overwrite
  cancellation, late destination edits, private handoff ordering and two private
  preparation failures. This is regression protection for preserved behavior,
  not a claim to repair a previously failing Save As implementation.

Resource construction expands to every original ordered AST statement. Expanding
the local-save helper and normalizing the overwrite helper's `None` cancellation
back to the entry point's `False` reproduces the complete original save statement
tree. Existing public signatures and all other methods in both owners match.
No production module was added or moved; no package, dependency, public API or
persisted format changed.

| Executed validation | Result |
| --- | --- |
| Resource browser before/after | Same 10 ordered cases; zero failures/skips. |
| Text editor before/after/final | All 23 cases, including five added contracts; zero failures/skips. |
| Resource lifecycle/lifetime/operations/selection | 24 cases across four files pass. |
| Resource picker consumers | Seven cases pass, including release, Save As and private-document paths. |
| Editor recovery | All 13 cases pass, including actual recovery scrubbing. |
| Remote browser consumers | All 10 cases pass with installed rclone and synthetic local/crypt backends; no real remote account used. |
| Editor change review | All 12 cases pass. |
| Ally Tools | All 48 existing fixture/import/signature cases pass unchanged. |
| Blue Hole current-source compatibility | Both existing static import/call-signature/global-binding contracts pass against current shared source in its private namespace. |

Both external worktrees and Blue Hole's vendor revision remain untouched. The
namespace probe is not native Blender registration/export validation. No device
testing, app installation, production-data mutation, release or push occurred.
Raw source copies, comparison drivers and reports stay under ignored test results.
Final checks pass: five Logistics/three shared wiki cases, configured lint,
toolchain consistency, source hygiene, architecture (24 host adapters / 15 feature
edges / zero violations) and whitespace. The two edited production modules and
regression module compile without execution. All 99 focused browser/resource/
editor/consumer cases pass, with no failures/skips; documentation and compatibility
checks are recorded separately above. Full suites and native platforms were not
rerun; earlier totals below keep their recorded source scope.

## Reader composition and Git execution readability continuation

This continuation starts from clean Logistics `355daf04`, shared `a2ab228`,
Ally Tools `d2c00b8` and Blue Hole `665c184`. Current development branches remain
unchanged. The work is readability/ownership maintenance with no push authorized.

- Shared `cd21efe`: Markdown viewer construction now names navigation, document
  surfaces, properties and reading-control phases in its existing module. Initial
  document admission, wiki composition, provider policy and lifetime wiring remain
  visible in the constructor. Its span changes from 184 to 68 lines.
- Logistics `bb13dcb2`: EPUB `build_controls(page)` composes menus, header,
  appearance, sidebar, reading area and footer through same-module private
  builders. The composition span changes from 191 to 15 lines. Existing page
  fields, callbacks, external menu embedding and speech/spread ownership remain.
- Logistics `2368b8a8`: Git runner separates argv/executable and environment
  preparation from captured process execution. `run()` retains admission,
  cancellation/timeout translation and result checking in 59 rather than 115
  lines. Application-specific Git and credential policy stays with the feature.

For all three units, expanding the helper calls reproduces every original ordered
AST statement, including callback bodies, imports and control flow. Returned
locals and helper parameters are checked explicitly. These are construction/
preparation boundaries, not new controllers, packages or state copies. Function
lengths describe navigation improvements, not a numeric quality target.

| Executed validation | Result |
| --- | --- |
| Shared Markdown before/after | Same 145 ordered case identities across 13 files; zero skips/failures in both runs. |
| EPUB before/after | Same 54 cases across three files; zero skips/failures in both runs. |
| Git backend before/after | Same 36 cases; zero skips/failures, using temporary local repositories. |
| Git old/new request comparison | 576 argv/environment/result/progress/error profiles match; no process started by this probe. |
| Reader consumers | Three IDE Markdown, four real documentation viewer and five cross-reader parity cases pass. |
| Ally Tools | All 48 existing fixture/import/signature cases pass against current shared source. |
| Blue Hole current-source compatibility | Both existing import/call-signature and global-binding contracts pass with current shared source loaded under the add-on's private namespace. |

Ally Tools and Blue Hole need no compatibility edits: no shared public method,
import path or signature moved. Both external worktrees, including Blue Hole's
existing vendor revision, remain untouched. The current-source namespace probe
does not replace native Blender registration/export validation.

Raw before/after source copies, comparison drivers and reports stay in ignored
test results. Final checks pass: four reading-feature cases, five Logistics and
three shared wiki cases, configured lint, source hygiene, toolchain consistency,
architecture (24 host adapters / 15 feature edges / zero violations) and whitespace.
The three edited production files compile without execution. No dependency,
module, package, public API or persisted format changed; no production data,
device app, remote repository or release was modified.

No failing or skipped case remains in this continuation's executed scope. Full
desktop/mobile/shared suites and native platforms were not rerun; earlier totals
below keep their original source provenance. Remaining useful ownership reviews
include Qt resource-browser composition, text-editor Save/Save As policy versus
publication, and large mobile/native lifetime owners. Offline index identity and
retention still need a defined contract before any behavioral changes. This pass
supports specific readability gains, not a new whole-ecosystem numeric rating.

## October 23 continuation on the current development branches

This continuation starts at Logistics `8c844fa2`, commonUtils `3797a25`,
Blue Hole's `blender-5.2.2/alpha` and Ally Tools' `alpha`. All four worktrees
were clean. Logistics is on `alpha` and shared source on `main`; the historical
work-branch names below describe earlier sessions. Current repository instructions
prefer retaining these branches. No push is authorized. Blue Hole and Ally Tools
are restricted to necessary shared-library compatibility work in this continuation.

- Reused the existing audit and progress history rather than rerunning its old
  measurements as a new baseline. Doctor, configured lint and architecture pass
  (24 host adapters, 15 feature edges, zero violations).
- All 48 Ally fixture/import/signature contracts pass against current shared
  source. No Ally production edit is required by the retained updater APIs.
- Shared updater fault injection reproduces six profiles: corrupt recovery copies
  for the manifest/replaced/deleted files, edits during recovery/payload copies,
  and a newly occupied destination during staging. All six fail against committed
  baseline source, then pass after verification and final target checks. Shared
  commit `6ef13d8`; all 18 updater and six Logistics update cases pass.
- A second unit reproduces a prematurely published new manifest and corrupt or
  interrupted rollback output overwriting installed bytes. Private sibling staging
  now owns payload/manifest/recovery lifetimes, verifies restored bytes and
  publishes the manifest last. Shared commit `08a3e05`; all 20 updater cases pass.
- A third unit reproduces rollback overwriting external changes to replaced,
  newly created and deleted paths, plus rollback enrolling a failed atomic
  replacement. Only completed mutations enter the in-memory recovery set;
  restoration checks this transaction's published bytes before/after recovery
  copying. Shared commit `9d048e2`; all 22 updater cases pass.
- Logistics `eb2bb0b9` validates persisted receipt types and handles invalid
  settings after worker preparation. Malformed receipts stay available without
  preventing startup; invalid preferences discard staging without closing the
  application. Three added cases and all six existing update cases pass. Corrected
  baseline execution reproduces the failures; valid receipt consumption passes
  both implementations. An intermediate fixture unnecessarily combined managed
  window cleanup with an unconditional delete callback; receipt-only fixtures now
  use ordinary isolated temporary files and all nine cases pass.
- Blue Hole `36807e7` updates only its vendor's three changed shared files and
  revision marker. Exact committed membership/bytes match shared `9d048e2`;
  all 44 adapters and all 22 actual-vendor updater cases pass. No add-on workflow,
  registration, preference, Perforce or export code changed.
- Complete shared validation at `9d048e2`: 184 isolated files, 1,258 cases,
  25 declared skips and zero failures. At Logistics `eb2bb0b9` / shared `9d048e2`,
  desktop passes 179 files / 1,688 cases / six skips; mobile passes 164 files /
  1,179 cases / two skips. Both mobile DOM skips separately pass using existing
  bundled Node/Playwright and installed headless Chrome with offline fixtures.
  Production Python remained unchanged during those full runs. All 1,908 tracked non-vendored Python
  sources compile without execution; lint, toolchain, compatibility and source
  hygiene pass. No type-checker result is claimed.

### Worker admission continuation

After the full desktop checkpoint, real progress-owner fault injection reproduces
exceptions during worker construction/start leaving `busy=True` with no running
worker. Shared `a2ab228` sends these failures through queued ordinary completion,
keeping the owner busy until that event and then retiring controls/worker ownership.
Existing worker error formatting moves unchanged into one private helper used by
both paths; redaction failures still never expose underlying details. Busy-owner
rejection remains synchronous. Two new shared methods cover three failure profiles,
deferred ordering and successful retry; a real Logistics controller test verifies
that its update offer recovers without closing or preparing a request.

All 11 worker/progress cases, ten Logistics update cases, 32 archive cases across
four files and 22 Bulk Rename cases across two files pass. Final Ally fixture tests
still pass all 48 cases unchanged. Blue Hole's actual vendor passes all 11 worker
cases, all 44 adapters and exact membership/bytes; only the four shared files and
revision marker change (Blue Hole `665c184`). Logistics checkpoint `239e3269`
records the consumer regression and shared pin. The final complete shared suite
at `a2ab228` passes 184 files / 1,260 cases / 25 skips / zero failures.
The full desktop/mobile totals above precede this shared Qt-only unit;
they are not relabelled as runs against a later source revision.

Release-tool fixtures pass 18 cases with one native-Windows launcher skip; their
publishing calls are mocked and nothing is uploaded. Documentation layout/viewer
checks pass five/four cases respectively. No release, device installation, Boox
package change, reset, remote push or external-app workflow operation occurred.

### Packaged-source checkpoint and resumption

The local source ZIP built at Logistics `239e3269` / shared `a2ab228` contains
2,332 tracked members plus version metadata; all 2,333 manifest hashes pass.
A fresh extraction starts the actual Qt application with an owned temporary
profile, opens the fixture in Bulk Rename, displays LM and Blender preset settings,
retains `DestinationRail.tools_menu`, and exits normally. The fixture file stays
unchanged. This is host offscreen startup, not native device/Blender validation.
Raw package, screenshots and reports stay in ignored test results.

Final tracked-source measurements: Logistics 1,173 files / 89,647 production /
77,232 test lines; commonUtils 529 / 42,808 / 23,981; Blue Hole excluding vendor
206 / 22,813 / 1,303. All 1,908 sources compile without execution. Exact repeated
production bodies of 20+ lines remain absent under the existing comparison.
No production module/package/dependency was added. All tracked worktrees are clean
at the implementation checkpoints; the last local documentation commit saves this
record. Ally Tools remains at `d2c00b8`, unchanged.

No unresolved failing check remains in the executed scope. Baseline fault-injection
failures and intermediate fixture mistakes above remain distinct from passing
post-fix checks. Native Windows/Linux, target Blender 5.2.2 registration/exports,
real devices and crash/power-loss recovery were not exercised here. Native Toga
cases retain the 25 shared skips in this interpreter. The historical platform
evidence below keeps its original scope; it is not new validation of this pass.

Resume with native platform/target-runtime checks, large mobile/native lifecycle
owners, offline index identity/retention policy and individually verified ownership
simplification. Preserve external-consumer scope: no Ally/Blue Hole refactor is
authorized solely to improve their architecture. This bounded continuation does
not establish the requested whole-ecosystem 7/10 outcome.
- One intermediate fixture compared macOS temporary-path aliases lexically and
  missed two injections. Canonical source-path comparisons fix the fixture; all
  corrected profiles were rerun against baseline and changed implementations.

The updater is a standalone stdlib script copied outside the installation. Its
mechanisms therefore remain in that owner rather than importing the package's
atomic writer. Public arguments, request/manifest formats and consumer shutdown
policy stay intact. These are optimistic content checks, not external-writer
locking or crash-atomic whole-tree replacement. Native Windows/Linux restart and
target Blender validation have not been rerun for this continuation.

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
  the exact original statement order. The constructor is 31 lines instead of 227 (inclusive spans);
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

## Active-provider cyclic links and portable test ownership

- A new regression found a remaining interaction in the earlier provider guards:
  an unrelated registered root prevented ordinary cyclic-link deletion. The guard
  now checks an unresolvable leaf by its resolved parent/name; looping ancestors
  still fail, protected links remain denied, and ordinary aliases keep resolution.
- All six boundary tests pass in both environments, with 17 file-operation, 13
  file-object, five removal and 13 resource-operation tests. The real-rclone file
  operation suite passes three cases with one explicit missing-native-bridge skip.
  Lint/architecture pass. Shared fix `04143cb`; Blue Hole vendor `1310200`.
- The standard copy checker correctly refused an intermediate source HEAD newer
  than the recorded vendor pin. Direct committed-tree comparison subsequently
  verified all 597 regular-file modes/blob identities for that historical vendor;
  the standard checker passes again at the final matching pin. This was a
  checkpoint mismatch, not a claimed successful comparison against the wrong HEAD.
- Three pure batch tests unnecessarily inherited Qt test infrastructure. Their
  unchanged bodies now live in test_batch.py with plain unittest; the five Qt
  worker/progress cases stay in their owner. All three portable cases pass in
  desktop and mobile interpreters, and all five Qt cases pass. Shared `6ff379e`.
- Blue Hole's embedded driver reuses existing portable regression modules instead
  of duplicating their assertions. Only its namespace/lifecycle and actual Blender
  command checks remain consumer-owned. The driver shrank from 179 to 129 lines
  while coverage expanded to 93 cases: 92 pass and one case-sensitive-filesystem
  case is explicitly skipped in real Blender 4.5.1 / Python 3.11.11.
- This includes existing stream, range, batch, persistence, recovery, boundary,
  rename, SSE, JSON/XML and selected plain ZIP extraction contracts. No optional
  crypto/GUI dependency was installed or mocked as native coverage. Both library
  namespaces have independent registries; diagnostics cannot open test dialogs.
- All 31 Blue Hole adapter tests and exact current vendor checks pass. Vendor/driver
  commit `19956ed`; Logistics pin `a4007ed6`. Native target 5.2.2 registration,
  Windows/Linux and physical-device validation remain unexecuted. No Docker,
  Podman or Colima CLI/standard app executable was found locally.

## Actual packaged startup and a Blue Hole declaration cycle

- Built Logistics `5e22726b` with shared `6ff379e`: 2,218 source members plus
  generated manifests/identity. All 2,219 content hashes match; evidence and the
  external emulation project are absent. A fresh extraction imports its own code.
- Offscreen launch runs real settings initialization, feature activation, the main
  window and index service with an owned temporary profile. Update checks are
  disabled for this offline probe. Bulk Rename opens one fixture, renders its
  controls and preserves its bytes. The tools-menu object remains present.
- Initial close is deferred by cooperative workers; the application subsequently
  exits normally with code 0 and stops the index service. This is packaged startup
  validation, not native macOS menu/focus or physical-device UX coverage. The
  screenshot/log/probe remain ignored evidence; the temporary extraction/profile
  is removed. The archive is a local verification artifact, not a published release.
- Blue Hole pie actions eagerly imported ten menu modules, while seven imported
  those actions for drawing. The existing helper accepts registered menu-ID
  strings; using those literal IDs removes the declaration-to-presentation edge
  without a new API, wrapper, registration change or UI rewrite.
- Before/after serialized comparisons match all 46 full descriptors, 22 keymap
  bindings and catalog order byte-for-byte. Two new tests reject presentation
  imports and verify IDs against actual menu declarations; import fails before
  the repair and both tests pass afterward.
- All 33 adapter tests pass. The actual embedded suite now has 95 cases: 94 pass
  and one filesystem case skips. Static module-scope candidate groups drop from
  three to two (580 to 569 internal edges), eliminating the eight-module pie
  group. Remaining environment/context and project/filter reciprocal helpers
  are not rewritten merely to lower graph counts without target-native evidence.
- Blue Hole commit `e0202d9`; no target 5.2.2 registration/operators were exercised.
  Immutable Logistics `5e22726b` / shared `6ff379e` runs completed: desktop
  179 files / 1,664 cases (six skips), shared 180 files / 1,218 cases (25 skips),
  zero failed files. Discovery includes the new portable batch file.

## Read-only path queries

- Local-folder discovery, Plex path queries, FUSE remote mount lookup and bundled
  ffmpeg lookup created unrelated software/credential directories through Config.
  Five lookup call sites now explicitly suppress resource creation. Actual Local
  folder creation, operation setup and default Config behavior remain unchanged.
- Three new fixture regressions failed before repair. All 16 software lookup,
  23 Plex, 25 FUSE, 17 YouTube and 39 folder UI tests pass; installer/downloader
  output in these suites is mocked. Architecture/lint and five documentation
  checks pass. Commit `18a7fd3b`; no real installations/downloads were performed.

## Shared natural filename ordering

- Superscript/circled numerals could enter integer conversion and abort directory
  scanning, native browse queries and comic page enumeration. Three regressions
  failed before repair. The existing standard-library search.names owner now
  supplies raw natural parts and tagged label keys; public path/comic wrappers
  preserve their signatures and key shapes.
- Previously supported sample keys and SQLite encoded sort bytes are identical for
  all 2,006 comparison cases. Decimal Unicode runs remain numeric; other numeric
  symbols remain text. New traversal, browsing and archive tests pass (3/13/59).
- Fourteen index suites ran 108 cases: two watcher suites failed under restricted
  filesystem access; their 12/11 cases pass with normal access. The other twelve
  suites pass. No failed run is counted as a passing whole suite. Twenty Bulk
  Rename tests, portable traversal/browsing and documentation/lint checks pass.
- Shared commit `86a5d51`, Logistics `f4e35aee`, Blue Hole `5c63af4`. Exact vendor
  comparison and all 33 adapter tests pass. Real Blender 4.5.1/Python 3.11.11 now
  runs 99 cases (98 pass, one filesystem skip), reusing traversal regressions too.
- Frozen shared `86a5d51`: all 180 files / 1,220 cases complete, 25 explicit skips,
  zero failed files. Frozen mobile Logistics `f4e35aee`: 162 files / 1,161 cases,
  two explicit Node/Playwright skips, zero failed files. Full desktop is still
  running at this checkpoint. Target 5.2.2 registration remains unavailable.

## Bounded reader state and consistent badge snapshots

- Book/comic resume loaders checked size before an unbounded read. Stale size
  metadata admitted oversized valid JSON. Comic badges also read state twice,
  allowing concurrent saves to mix total and position from different records.
- Both feature owners use the existing bounded stream reader with their existing
  128 KiB policy. Comics owns one private JSON admission method and a position
  projection, reused by resume and badges. Saved identity, JSON shape, name-first
  restoration, clamping and malformed-state fallbacks stay unchanged.
- Three new regressions fail before repair and pass afterward: oversized book and
  comic records plus an actual fixture save between badge reads. All 52 book and
  seven comic resume cases pass; portable Unicode/invalid JSON/invalid encoding/
  oversized profiles pass in the mobile interpreter. Files are preserved by reads.
- Lint, architecture and five documentation checks pass. Commit `b98da89a`.
  Frozen full-suite totals above predate this unit; these focused checks validate
  it separately. Writes retain their existing policy; no state migration occurs.

## LM layout composition

- The 200-line LM layout function mixed sidebar, session controls and message
  construction. Three private builders in the existing layout module now own
  those sections; top-level composition is 40 lines. Widget reference names,
  parent/layout order, callback ownership and signal statements are unchanged.
- Expanding helper bodies reproduces the original constructor AST exactly.
  Existing LM tests run all nine files, including real local HTTP fixtures,
  screenshots, appearance, generation, leases, shutdown and session behavior.
  All 115 cases pass; lint, architecture and five documentation checks pass too.
- The owner guide also removes an obsolete claim that deleted forwarding modules
  still exist. No public imports, new production files or dependencies were added.
  Commit `e75e73e3`.

## Command pipe read failure propagation

- Command stdout/stderr reader exceptions were silently treated as EOF. Four
  injected OSError/ValueError profiles reproduced missing errors while real owned
  child processes were running. Reader failures now travel to the supervising
  caller, which retires the child/streams before propagating the original error.
- Timeout/cancellation still return explicit outcome flags and partial output.
  A companion test interrupts a blocked reader during stop and confirms that its
  cleanup error does not mask the timeout. No output/argument/result format changed.
- All 23 command/capture, 11 mobile-interpreter command, five Perforce adapter and
  two supervisor tests pass. Exact vendor checks, all 33 Blue Hole adapters and
  embedded 99-case checks pass (one filesystem skip). Live Perforce is unexecuted.
- Shared commit `73a8c86`, Logistics pin `d4e52350`, Blue Hole vendor `f4cc8c0`.
- Frozen Logistics `f4e35aee` desktop also completed: 179 files / 1,668 cases,
  six explicit native-bridge skips and zero failed files. Together with its mobile
  and shared runs above this is a completed full-suite checkpoint. Later reader,
  LM and command units have their own focused validation, not these older totals.

## IDE search and optional decoration startup

- Find in Files search/preview submit failures escaped Qt callbacks and left
  searching/loading feedback. Two tests (four OSError/RuntimeError profiles)
  reproduce these errors before repair; submissions now report visible context,
  cancel the failed request and leave no claimed future. Empty completion errors
  also display their type. Real executor retries succeed after every profile.
- All six Find in Files cases pass. The eight-file IDE owner run executes 62
  cases: one real watcher case fails in restricted access; all six cases in that
  file pass with normal access. The other seven files pass. Documentation, lint
  and architecture checks pass. Commit `35ababf7`.
- Optional gutter markers and project Git status had the same unhandled admission
  failure. Their existing fallback publication now serves startup and completion
  errors, while periodic refresh/retry and core editing/browsing remain available.
  Each controller has one cohesive private publication method, not a new worker
  framework or exception-swallowing service.
- Both new tests fail before repair under both startup error profiles. All 12
  editor baseline/autosave cases, seven IDE browser cases and 43 Text Editor
  cases across three files pass. Source fixture bytes remain unchanged. Lint,
  architecture and five documentation checks pass. Commit `f15fdb8c`.

## Broader real embedded portable validation

- Blue Hole's embedded smoke driver now reuses five more existing library test
  modules: content snapshots, INI files, encoded text files, three-way merge and
  format registration. No duplicated assertions, packages or runtime dependencies
  were added. These owners do not invoke host-Python subprocess fixtures.
- Real Blender 4.5.1/Python 3.11.11 executes 141 cases: 140 pass and one filesystem
  case skips. The actual vendor remains `73a8c86`; the driver and owning guide are
  committed separately as `53ec9cb`. This expands portable runtime evidence, not native add-on
  registration/operator/UI coverage for target Blender 5.2.2.

## Preserve readable checkpoints on oversized reader saves

- Reader writers could replace a good checkpoint with JSON exceeding their own
  read limit. Five long but valid bookmark labels reproduce this in Books; a
  deliberately oversized comic page identity exercises the portable API guard.
  Both new preservation tests fail before repair.
- Both owners now supply their existing 128 KiB limit to atomic_write_json. Bounds
  apply to encoded UTF-8 bytes before publication; previous bytes remain readable
  after rejection. The existing reader save-error handling reports the failure.
  No schema, encoding or identity changes were made.
- All 53 book and eight comic resume tests pass. The stale-size read fixture now
  writes an externally invalid checkpoint directly because the repaired writer
  correctly refuses to create it. Its read-bound assertions remain unchanged.
- Mobile-interpreter checks reproduce oversized Unicode writes for both owners
  and confirm the prior state survives. Lint and five documentation checks pass.
- A scoped optional F401 report found 46 candidates, many intentional package
  exports and compatibility/patch targets. No bulk auto-fix or new lint gate was
  applied; configured correctness lint remains green. Further import cleanup
  requires individual interface review, not just an unused-name count.

Reader write-bound commit: `a4e10aba`. The full frozen `f15fdb8c` / shared
`73a8c86` integration run is ongoing for desktop; shared completes all 180 files /
1,222 cases (25 skips), mobile all 162 files / 1,161 cases (two skips), zero failed
files. The newer reader bound has its focused checks above.

## Completed integration checkpoint and packaged LM startup

- Immutable Logistics `f15fdb8c` completes all 179 desktop files / 1,675 cases,
  six explicit native-bridge skips, zero failed files. Matching shared `73a8c86`
  completes 180 / 1,222 / 25 skips; mobile completes 162 / 1,161 / two skips.
  These totals precede the later reader write-bound and comic XML admission units.
- Built local package `cc1f3b31`: all 2,219 content hashes verify. Fresh extraction
  starts the real app with a private profile, renders fixture Bulk Rename and LM,
  retains tools_menu and exits normally. Expanded generation/token controls were
  visually inspected. LM is enabled through the normal API only in that profile;
  it is disabled by default, so an initial probe assumption failed before the
  probe was corrected. Both attempts remain ignored evidence. No network updates,
  user profile/preferences or published artifact was used.
- Current compile checks cover 1,863 tracked Python sources across the three
  owners. Compatibility, source hygiene, toolchain consistency and doctor pass.
  Release tests run 18 cases (17 pass, one Windows-only skip); publishing output
  is mocked, and no release/upload occurs.

## Comic metadata write/read admission consistency

- ComicInfo reads reject XML over 4 MiB, while edits could publish larger XML and
  make the comic unreadable afterward. XML escaping can cross the limit even
  when the submitted text is much smaller. Two regressions fail before repair:
  one save and a two-comic batch with only the later archive near its limit.
- The existing document preparation path now applies the read limit to serialized
  bytes. Single/local/private saves and portable batch plans share that path;
  preflight rejects the batch before any earlier archive is replaced. Rejected
  edits preserve both loaded metadata and exact archive bytes. No format changes.
- All 34 comic library/editor cases, 19 encrypted comic cases, 39 real-rclone private
  cases and the mobile collection privacy case pass. A portable mobile-interpreter
  metadata plan also rejects escaped XML overflow without changing its fixture.
  Lint, architecture and five documentation checks pass.

Comic XML admission commit: `bb6a40ca`.

## EPUB backup pathname ownership

- Failure cleanup unlinked the backup pathname even if another writer replaced
  it after the exclusive creation. An identical-byte replacement also admitted
  publication despite no longer being the independently created backup.
- A real fixture regression reproduces three profiles: different bytes, identical
  bytes, and a symbolic link. Before repair the foreign paths are removed or the
  source is published. After repair original EPUB bytes, loaded metadata, moved
  owned backup bytes, foreign paths and link targets all survive appropriately.
- The writer captures the created descriptor's device/inode, checks the regular
  pathname identity before permissions and final publication, and cleans only
  while that identity remains. Existing corrupt same-file backups still abort
  and clean up. This is optimistic identity validation, not a cross-process lock
  or attribution of external in-place writes to the same file object.
- All 54 book cases pass, including legacy corruption/cancellation/permissions/
  failed-replacement coverage. Lint, architecture and five documentation checks
  pass. The final one-snapshot lstat predicate additionally passes all 19 EPUB
  cases. Native Windows/network-filesystem behavior remains unexecuted.

EPUB backup ownership commit: `5b9876a7`.

## Reviewed private UI import cleanup

- The optional import report was reviewed against tracked consumers in all three
  owners. Five unused Path/GitError imports were removed from private Git/IDE/
  comic UI implementation leaves. Direct/star consumers and qualified references
  were checked; all five owners import, scoped F401 and configured lint pass.
- Public package exports, DownloadCancelled, legacy comic patch targets and
  registry facade names remain intact. No lint gate was weakened or global
  automatic import rewrite applied. No new tests were needed for these removals.
- Mobile composition was inspected separately: its explicit typed controller
  factories duplicate a few lines but make ownership visible, while the existing
  decorator supplies enumerated compatibility accessors. Replacing them with more
  generated behavior was rejected as a readability regression. No device/UI
  behavior change is inferred from a smaller line count.

## Bounded LM and workspace restoration reads

- LM conversation/profile reads and mobile workspace restoration checked size
  metadata before unbounded reads. Two public-load regressions reproduce oversized
  JSON being admitted when stat metadata is stale.
- Both owners now use the existing bounded reader with their unchanged limits:
  32 MiB for LM records, 64 KiB for workspace manifests, plus one detection byte.
  JSON schemas, defaults, warning behavior, save veto and file bytes are preserved.
- All 116 LM cases in nine files pass, including real local HTTP fixtures. All 43
  native-dummy workspace UI cases in four files pass. The five pure workspace
  cases and two injected-lock LM adapter cases also pass in the mobile interpreter.
  Lint, architecture and five documentation checks pass. No new shared API/dependency.

LM/workspace bounded-read commit: `197943e7`; private UI import cleanup: `db39d3cf`.

## Bounded signature verification and guarded LM move rollback

- Existing stream/file snapshot hashing now accepts optional max_bytes. Default
  behavior and result formats are unchanged. Oversized input raises ValueError,
  never returns a prefix digest, and stops growing streams with at most one 1 MiB
  chunk of lookahead. Negative/noninteger limits fail before stream reads.
- Eleven stream and seven snapshot cases pass in both interpreters. The reused
  embedded suite runs 143 cases (142 pass, one filesystem skip) in real Blender
  4.5.1 / Python 3.11.11; all 33 Blue Hole adapters and exact vendor checks pass.
  Shared `178f5da`, Blue Hole `3b679c3`, Logistics pin `66dc2aa4`.
- LM moves previously deleted a changed/new destination after source retirement
  failed, and could delete late source edits or roll back the only surviving copy
  when the source vanished. Seven profiles reproduce against the committed prior
  implementation: four replacement/edit/link rollback cases plus late source,
  destination and missing-source cases (six assertion failures, one expected
  uncaught FileNotFoundError in that baseline probe).
- Moves verify published content with the bounded snapshot API, recheck source and
  copy revisions, and remove a rollback copy only while both paths still match.
  Changed/missing sources retain the surviving copy; replaced/modified copies are
  preserved with both paths named in the conflict. In-memory revision/folder state
  advances only on complete success. Checks remain optimistic filesystem samples.
- The initial test design removed an unchanged copy after any source change; review
  identified that this could erase the only surviving copy if the source vanished.
  Coverage was strengthened to require retained recovery content for changed or
  missing sources before implementation was committed. No passing baseline was
  claimed for the failing profiles.
- All 118 LM cases across nine files pass, including ordinary rollback, locks,
  history/drafts, generation and local HTTP fixtures. Mobile-interpreter injected
  lock smoke verifies successful move and unchanged rollback without Qt locks.
  Lint, architecture and five documentation checks pass.

Guarded LM move commit: `572250fe`.

## Existing browser and native runtime inventory

- The bundled workspace runtime provides Node 24 and Playwright; installed Chrome
  is available even though Node is absent from the default shell PATH. Both
  previously skipped browser DOM cases now pass against their unchanged offline
  fixtures using explicit runtime/Chrome paths and temporary profiles. No package
  or browser was installed; this is Chromium evidence, not iOS WebKit rendering.
- Read-only native inventory finds installed iOS 26.5/27.0/27.1 runtimes and no
  connected Android device. Existing simulators are all shut down. Native iOS
  evidence is being prepared in an owned simulator/build, preserving existing
  simulator data and generated builds. No Boox app was installed or changed.

## Breadcrumb teardown and integration checkpoint

- Full runs held Logistics `b3031665` / commonUtils `178f5da` unchanged: shared
  1,224 cases (25 skips), mobile 1,161 cases (zero skips with the existing
  Node/Chrome runtime), and optional native Toga 108 cases all passed.
- Desktop ran 1,684 cases (six skips), with three eight-second worker setup
  timeouts in the Bulk Rename UI file while native compilation was also running.
  The same 20-case file passed alone in 10.85 seconds. Resource contention is a
  possible explanation, not established causation; the full run remains failed.
- The passing Bulk Rename host file also emitted a real Qt callback traceback:
  deferred breadcrumb scrolling accessed a retired native scroll area. A focused
  regression reproduced two unhandled errors before the fix. Binding the timer
  to its Qt owner and checking the child's native lifetime removes both errors.
  Six browser polish, nine presentation and two affected host cases pass; lint
  and five documentation checks pass. No test timeout was relaxed.
- Shared fix `3d4ba2f`; exact Blue Hole sync `adb20b6`. All 33 adapters and
  143 embedded shared cases (one filesystem skip) pass on Blender 4.5.1 /
  Python 3.11.11. Target Blender 5.2.2 registration remains unverified.
- Native runner `b3031665` selects Briefcase through the active Python module,
  repairing an existing stale console-script interpreter path. Its 14 report
  contract cases pass, including the added interpreter-prefix assertion.
- An isolated clean native build of `b3031665` / `178f5da` completed all 33
  iPhone acceptance cases on iOS 27.0 / embedded Python 3.12.10. Exact staged
  source verification passed. Independent windows and native system picking were
  not exercised on this phone. Rotation/light-dark and synthetic private-file
  fixtures were saved locally before cleanup. Existing bridge archives were
  reused with recorded hashes; Go bridge compilation was not repeated.
- The first copied Xcode project omitted a required framework build helper;
  restoring that exact existing helper resolved the build. Both build logs are
  retained. No dependencies were installed, no existing simulator/device data
  was changed, and no Boox test package was installed. A newly owned iPad
  simulator is now exercising the explicit independent-window gate.

## Completed frozen checkpoint and Blender layout ownership

- Frozen Logistics `d52b65d8` / commonUtils `3d4ba2f` completes desktop
  179 files / 1,684 cases / six skips and shared 180 / 1,225 / 25 skips,
  with zero failed files and no deleted-widget traceback. Tracked trees stayed
  clean throughout. The earlier timeout run remains recorded above.
- The isolated iPad build of `b3031665` / `178f5da` passes all 33 native
  cases with the required independent-window gate: drafts remain separate and
  second-scene close/restore retains its saved state. Original launch-scene
  closure/restoration and native system picking remain explicitly unverified.
  Both owned simulators were deleted after saving complete reports/fixtures; the
  disposable build/clone was removed and its verification worktree archived.
  Existing devices, generated builds and user data were preserved.
- Desktop Blender layout mixed configuration navigation, preset controls and
  addon selection in a 197-line builder. Three cohesive private builders remain
  in the same existing module; the composition entry is 39 lines. Expanding the
  calls yields exactly the prior AST, preserving widget/signal order, text,
  parenting and settings/standalone modes. No new file or public interface.
- All 18 Blender page cases and five documentation checks pass; configured lint
  passes. Mobile controller methods inspected already have cohesive owners and
  were not split merely for their line counts.

Blender layout commit: `84597674`.

## ZIP publication and selection contracts

- ZIP editing checked source identity before staged fsync/chmod and the final
  cancellation callback. Two deterministic fixture writers in that later window
  replaced newer archive bytes before the fix. The identity guard now runs
  immediately before replacement, after those callbacks. This remains optimistic
  validation, not a lock against arbitrary concurrent writers. Shared `ba82c4a`.
- Both late-change profiles fail on the prior implementation in desktop and
  mobile Python, then pass with the fix. All 24 archive cases and 13 archive
  workspace UI cases pass. A temporary candidate's first broader probe used
  copied globals and missed an existing monkeypatch; correcting the probe to use
  the real module globals passed all cases. The first tracked regression copy
  omitted its local import; that fixture error was corrected before commit.
- A one-pass removal iterator was exhausted by the first archive member, leaving
  later selected files/directories untouched. Capture the removal selection once
  before scanning. Tuple/list controls pass before; the iterator regression fails
  before and passes after. All 25 archive cases and both mobile plain-ZIP profiles
  pass. Shared `9a9ea65`; no archive schema/encryption policy changed.
- Follow-up review binds the resize-triggered breadcrumb timer to its Qt owner
  as well as the set-paths timer. Existing six polish cases pass; shared `84ed1c8`.
  Configured lint passes. Blue Hole exact-copy verification and 33 adapters pass;
  its existing embedded driver now includes the two new portable ZIP profiles.

Embedded result: 145 cases on Blender 4.5.1 / Python 3.11.11, 144 passing and
one filesystem skip. Both new ZIP methods execute there without optional
encryption packages. Target Blender 5.2.2 registration is still not claimed.

## Reviewed UI imports and packaged startup

- An optional broader F401 inventory reports 109 candidates across desktop,
  features, services and mobile. Many are intentional exports/patch targets;
  this is not a configured gate and no bulk fix was applied. Cross-repository
  tracked-source import/attribute searches support removing four unused names
  from three existing private implementation locations: Blender layout's
  LaunchCard import, Blender page's two typography imports, and the Markdown
  launch callback's unused local Qt import. Supported page/catalog exports stay.
- All 18 Blender page and three document-launcher cases pass; correctness lint
  and diff checks pass. The same-module composition remains unchanged.
- A clean `cc5a0661` / `84ed1c8` source package passes all 2,219 manifest
  hashes and real offscreen startup from fresh extraction with its own profile.
  Bulk Rename opens the owned fixture without altering it; expanded LM controls
  render, reserved Misc tools_menu is present, and cooperative shutdown exits 0.
  This package precedes the subsequent import-only cleanup. No release was
  published and no update download was run.

Reviewed import cleanup: `0ac67e1c`.

## Stable archive member-plan inputs

- The shared open-adapter planner repeatedly tested membership in `include` and
  `stored` inputs. One-pass iterators were exhausted by earlier members: a
  retained-name iterator produced an empty rebuild, and a stored-name iterator
  silently lost a later compression override. Both profiles fail before the fix;
  tuple/list controls retain their previous behavior.
- Capture those name sets once when lazy plan consumption begins. Existing
  ordering, replacement append semantics, comment/attribute preservation and
  compression defaults are unchanged. The helper remains in its current archive
  owner with no format-specific EPUB/comic policy. Shared commit `9398118`.
- Five rebuilding cases pass in both Python environments; 25 full archive,
  19 EPUB and 34 comic library/editor cases pass. Existing embedded coverage now
  includes the complete five-case rebuilding module: 150 cases on Blender
  4.5.1 / Python 3.11.11, 149 passing and one filesystem skip. All 33 consumer
  adapters and exact vendor checks pass; configured lint passes.

## Complete archive output buffers

- A short-writing archive output adapter accepted only three bytes per call.
  Rebuilding ignored each write count and returned full-content hashes despite
  truncated output. Zero/None writer returns also produced a success manifest.
  Three fault profiles fail before the fix.
- Extract the already-tested complete-buffer loop from `copy_stream` as
  `write_all` in the same stream owner; both copying and retained ZIP members
  use it. Partial writes retry with cancellation checks; invalid/would-block
  returns raise before any manifest is returned. No new dependency or package.
- Seven rebuilding and 11 stream cases pass, rebuilding also in mobile Python;
  25 archive, 19 EPUB and 19 encrypted-comic cases pass. Existing progress units
  and stream cancellation tests remain unchanged. Shared `43838b0`.
- Embedded Blender runs 152 cases (151 pass, one filesystem skip); 33 adapters,
  exact vendor checking and configured lint pass. Native iOS reports remain tied
  to their earlier clean source snapshot, not relabeled to this portable change.

## LocalCrypt input completion

- The desktop provider's manual upload loop treated a would-block (`None`) read
  as EOF. Real pinned-rclone fixtures reproduce successful publication of empty
  or partial encrypted files for two interrupted-input profiles. Both fail the
  new expected-error regression before the fix.
- `create_file` now delegates copying to the existing shared stream owner. Input
  errors propagate through the existing binary command failure contract; owned
  encrypted staging is removed and existing documents remain unchanged. No new
  plaintext staging or storage format was introduced.
- Five file-operation cases run: four pass, one mobile host-bridge case skips.
  Both fault profiles verify exact ciphertext-tree preservation and original
  document readability. All 39 real-rclone LocalCrypt integration cases pass,
  including encrypted reads, metadata, editing and transfer/resource behavior.
  Lint and five documentation checks pass.

LocalCrypt input completion commit: `395b7821`.

## Native cover queue retirement

- A queued cover request outlived its Qt views and accessed a deleted CoverModel.
  A minimal real-widget regression reproduces the unhandled native-object error
  before the fix. Both deferred enqueue and queue-advance timers now carry the
  owning view as their Qt context, matching column selection's existing policy.
- All ten browser presentation cases and two Bulk Rename host cases pass. The
  broader 30-case browser file first fails two watcher/model-loading checks under
  the sandbox, then passes all 30 with normal filesystem notification access.
  Assertions and timeouts are unchanged; both results are retained.
- Shared fix `a3c12c9`; `1e8f891` also lists the new write_all function in the
  existing stream API catalog/table. Lint, exact vendor checking and all 33
  Blue Hole adapters pass.

The exact `a3c12c9` copy also passes the embedded 152-case suite (one filesystem
skip), including independent canonical/add-on namespaces and no optional UI
toolkit imports. This does not execute Qt widgets inside Blender.

## Frozen complete-contract integration checkpoint

- Logistics `a287c5ca`, shared `a3c12c9`, Blue Hole `156b227` stayed tracked-clean
  and unchanged throughout the full runs. Desktop completes 179 files / 1,685
  cases / six skips; shared 180 / 1,232 / 25 skips; mobile 162 / 1,161 / zero
  skips with the existing Node/Chrome DOM runtime. Zero failed files; no Qt
  deleted-object callback tracebacks. Earlier failed attempts remain above.
- Architecture reports 24 host adapters (one fewer after reviewed unused-import
  removal), 15 feature edges and zero violations. Lint, pin compatibility and
  source hygiene pass. All 1,863 tracked Python files compile without bytecode.
- The same clean source package passes all 2,219 hashes and actual offscreen
  startup after fresh extraction. The owned-profile probe verifies Bulk Rename,
  expanded LM controls and a temporary Blender settings preset without download
  or Blender launch. The Blender screenshot was visually inspected. This
  archive belongs to this checkpoint, before the later junction compatibility fix.

## Python 3.11 traversal compatibility

- Deeper embedded validation reproduces AttributeError in metadata scanning and
  GUI-free wiki traversal: direct Path.is_junction calls require Python 3.12.
  Existing desktop 3.12 tests had passed, so the narrower earlier embedded suite
  had not established these APIs' older-runtime compatibility.
- Metadata scanning, Windows index checks and wiki traversal now use the existing
  filesystem.links.is_junction owner, including its documented Windows fallback.
  No new fallback implementation, public path or version dependency. The synthetic
  junction exclusion test patches that query boundary rather than Path internals.
- Three existing catalog tests move unchanged into a GUI-free test owner; their
  AST is identical. Eight viewer tests retain their Qt owner. This extra test
  file makes real embedded catalog coverage possible without GUI dependencies.
- Shared `288ccbb`: 51 directory cases across five files plus 15 persistent index
  cases pass; four index and three catalog cases also pass in mobile Python.
  All 11 wiki/catalog and five packaging/import cases pass on desktop. Lint and
  five documentation checks pass; no new module-scope cyclic group is introduced.
- The expanded embedded suite passes 160 cases (one filesystem skip), including
  metadata writer/scanner, four directory snapshot/cache and three catalog cases.
  Native Windows junction behavior remains unexecuted; this is not all-platform
  or Blender 5.2.2 registration proof.

The final expanded driver also compiles vendored production sources in Python
3.11 without importing optional toolkits: 161 cases, 160 pass and one filesystem
skip. Syntax acceptance is distinct from registration/runtime behavior. All 33
consumer adapters and exact vendor checking pass.

## Cached native bridge and bounded mobile input

- Further inventory found an existing arm64 host dylib, SHA-256
  `6bba37af1852f7c318afe31d1ca72a1b52f0c78afd876681f30b29ade5320f67`.
  Embedded build info reports Go 1.26.9, revision `f5e4ea39377f12a8ef5f59e5170cff3446d1f06f`
  and vcs.modified=true. Its exact source provenance is unknown; no fresh Go
  build or matching-current-source claim is made. The cached binary is unchanged.
- Six previously skipped native scenarios execute against that binary using
  synthetic local/in-memory remotes: batched listing, two encrypted round trips,
  comic password/lifecycle, direct remote readers and mobile file operations.
  All pass; earlier full-run skip counts remain accurate for their environment.
- The mobile provider read no-descriptor input once. A three-byte reader sent
  only that prefix to native encoding; an oversize short-reader bypassed the
  existing 1 MiB limit, and would-block input raised TypeError. Two assertion
  profiles plus that TypeError reproduce before the fix. The actual cached
  native bridge separately confirms the three-byte truncation.
- Reuse shared read_up_to with the existing maximum-plus-one bound and
  cancellation. Full input is encoded, invalid input never reaches the native
  encoder, and owned staging is removed. Nine configuration, three UI and all
  five desktop/native file-operation cases pass, with no skips in that targeted
  native-enabled run. No input cap, ciphertext format or credential policy changes.
- The first native post-fix run retained the new test file before an existing
  empty-tree assertion. Removing that owned fixture after its verification
  restores the original assertion unchanged; the corrected full file passes.
- The complete post-junction shared suite also finishes: 181 files / 1,232 cases /
  25 skips, zero failed files. The extra file contains the three unchanged
  portable wiki cases; it did not inflate the case count.

Mobile bounded-input commit: `e755287d`; shared `288ccbb`; Blue Hole `098f3f1`.

## Current-source native-enabled verification

- Desktop/mobile held all three tracked trees clean at `e755287d` / `288ccbb` /
  `098f3f1` throughout their runs. Desktop: 179 files / 1,685 cases / zero skips
  and failures, including all six
  cached-host native scenarios. Mobile: 162 / 1,163 / zero skips and failures,
  including both existing Chromium DOM cases and the new bounded-input profiles.
  Shared `288ccbb`: 181 / 1,232 / 25 skips / zero failed files, completed with
  root `fc6438b8` before the subsequent mobile-only input change.
- The cached host dylib is byte-identical after validation. Its unknown modified
  build provenance remains separate from the source snapshot, which is proven
  only for the Python code. No current Go build claim.
- All 1,864 tracked Python sources compile. Configured lint, doctor, toolchain,
  compatibility, hygiene and architecture pass. The source package contains
  2,219 tracked members plus version metadata; all 2,220 manifest hashes pass,
  followed by actual owned-profile startup/Blender settings rendering and exit 0.
- Fresh graph inventory: Logistics 659 modules / 1,610 edges / 27 all-import
  candidate groups; commonUtils 326 / 956 / six; Blue Hole 196 / 586 / two.
  Module-scope edges/groups are 859/zero, 780/two and 569/two. Shared junction
  query reuse merges conservative candidate groups and grows the largest from
  91 to 105 modules; the smaller group count is not cycle elimination. No new
  module-scope group appears. This coupling tradeoff is explicit in the audit.
- The audit now leads with all seven assessment dimensions, current measurements,
  exact validation scope and remaining platform/architecture work. Documentation
  verification commands include the extracted portable catalog cases and retain
  the earlier October 16 evidence's original scope.
- Both created simulators are verified deleted; the owned verification worktree
  is archived after saving evidence. No Boox package was installed/changed, no
  existing device/app data was cleared, and no remote was pushed or published.

Final guide validation: all five documentation-layout and four real viewer
integration cases pass. Inclusive AST spans confirm constructor/composition
changes of 227→31, 200→40 and 197→39; the earlier 226 count excluded the
definition line and is corrected above.

## Follow-up review of all maintenance changes

Reviewed the production diffs and affected contracts across Logistics, commonUtils
and Blue Hole, including publication/rollback, move cleanup, bounded I/O, background
submission and Qt lifetime handling, presentation extraction, consumer pins and
documentation scope. No additional runtime defect was confirmed in this review.
The shared architecture guide needed a clearer distinction between the complete-tree
archive workspace extractor and the lower-level ZIP extractor, which still stages
individual files. One extra blank line at the end of the portable wiki test was
removed; its AST is unchanged. Shared commit `e2f18fd` contains those corrections;
Blue Hole `0edf0d2` vendors the exact same revision. Production Python is unchanged.

Fresh host validation completed:

| Suite | Result | Scope |
| --- | --- | --- |
| Desktop | 179 files, 1,685 passes, zero skips/failures | Offscreen Qt with the existing cached native bridge. |
| Shared | 181 files, 1,207 passes, 25 skips, zero failures | Declared optional toolkit/platform cases remain skipped. |
| Mobile host | 162 files, 1,161 passes, two skips, zero failures | Both skipped DOM cases subsequently pass using existing Node/Playwright/Chrome; 1,163 cases pass across the full run and focused rerun. |
| Blue Hole adapters | 33 passes | Exact shared vendor membership/content also verified. |
| Regression-runner contracts | Seven passes | Includes discovery isolation and preservation of failure outcomes. |

Correctness lint, architecture policy (24 host adapters / 15 feature edges / zero
violations), toolchain consistency, source hygiene and whitespace checks pass.
The cached native bridge hash is unchanged. Initial audit test invocations omitted
the repository root from PYTHONPATH and encountered sandbox watcher/loopback
restrictions; those runs were interrupted and retained as failed attempts. A
comic-reader timing assertion failed in that initial run and passed in the complete
corrected desktop run. No test assertion or timeout was weakened.

This review did not repeat native device UI, Windows/Linux validation, target-version
Blender registration/operators/exports or a fresh Go build. Earlier evidence keeps
its recorded source/platform scope. The prior packaged source archive was not
rebuilt for these documentation/whitespace corrections. No push or release occurred.

## Readability follow-up: generated-project adapters

Six related build/artwork adapters move into `mobile_build/build_support/` with
explicit bridge-builder composition. Assets, signing inputs, workspaces and
Perforce architecture are preserved. All 13 non-camera adapter cases, camera
cases in the mobile host environment, five wiki cases, lint and CLI import
checks pass. Earlier camera invocations lacked the sibling import path and then
Toga; neither was a product failure. See [current readability work](readability.md).
No push or release retry; this work is on an isolated local branch.

## Readability follow-up: deployment owner

Build-adapter grouping is committed as `3456c489`. Twelve deployment/distribution
modules now share one explicit package import context. Six existing Finder
launchers are exercised from an unrelated directory. Real workers still overlap
and isolate output; the real Qt subprocess fixture still tests split confirmation
markers and both user answers. Fifty-three deployment cases, ten external JWT
cases and thirteen launcher/UI/wiki cases pass (some overlap). Lint, TestFlight
workflow actionlint, CLI help and whitespace checks pass. Initial GUI fixtures
used obsolete script argv and a fake script outside the new package; that owned
run was stopped, fixtures adapted, and the corrected run passes. No upload or
device install occurred.

## Readability follow-up: native validation tooling

Deployment grouping is committed as `84b4a3af`. Six native validation/fixture
drivers now have one discoverable owner; the root has three Python entry points
versus 27 before the grouping. Twenty report/gate/resume cases pass, plus
actionlint, Ruff and CLI help. The initial Duo help check exposed its old
script-versus-package import branch; replacing that with the canonical module
import fixes the check. Device tests and generated evidence retain their paths.
No push, release retry, native build, app install or upload.

## Readability follow-up: central documentation wikis

Native validation grouping is committed as `e85a40d0`. Shared `38c5d80` centralizes
65 guides under docs/ with 79 wiki pages, H1 titles, linked landing pages and short
legacy source entry links. Logistics moves 107 feature/Bulk Rename guides into
`docs/features/`; real desktop Settings/menu/viewer and mobile staged-help paths
retain one root sidebar. Five Logistics layout, four real viewer, fourteen mobile
help/startup and fourteen shared wiki cases pass. Cross-library links point at
canonical shared articles, including heading anchors. Perforce runtime, saved
formats and consumer packaging are unchanged. No push or release operation.

## Readability follow-up: grouped host regressions

The central Logistics wiki is committed as `50480def`. All 163 mobile host test
modules move into nine subject folders with explicit cross-folder fixture imports.
Before and after runs each discover 1,169 cases, zero failed files and two DOM
skips; both DOM cases pass separately with existing Node/Playwright/Chrome.
Filenames and recursive developer selection remain stable. All moved files are
trackable (the tooling group avoids generated-build ignore rules). Configured
lint, ownership/architecture, toolchain and hygiene checks pass. Blue Hole
`428f338` passes all 33 adapter cases and exact shared vendor checking; production
Python including Perforce is byte-identical to its prior copy. No push.

## Readability follow-up: explicit build declarations and final review

Grouped test contracts are committed as `b81979d9`. The final review fixes remaining
README feature links and TestFlight module strings and retains both legacy and
central-wiki mobile-evidence exclusions. Its actual five-module command passes
39 cases; all 25 workflow/package cases run, with only the native Windows launcher
skipped. The single shared supplement declaration preserves all 82 members.
Old/new staging emits 979 byte-identical members including source manifests.
Native adapter composition uses explicit modules and script/package selection.
The final tooling group passes 108 cases in 17 isolated files; 26 payload/wiki/dev
runner cases, all actionlint, configured Ruff and whitespace checks pass.

Real offscreen previews of both wiki roots were inspected. The current assessment
and remaining native/large-owner work are in [the readability record](readability.md).
No new overall numeric score is claimed. Shared `38c5d80` is available as a local
branch in the canonical shared repo without touching its dirty checkout. The
primary app's concurrent navigation edits remain untouched. No push, release
monitoring/retry, app deployment, upload or Perforce server operation occurred.

## Continued readability: shared image and comic workflows, Blue Hole gates

Shared `f872be7` exposes three private image phases. Eight public contracts,
48 byte-exact old/new profiles and 120 consumer cases pass. Comic compression
exposes explicit page/path inputs and preserves the publication owner: 194 comic
cases and 32 full plain/AES parity runs pass. Blue Hole `f5849bb` repairs the
existing outside-source diagnostic NameError; `6dcc730` separates diagnostics
from checks. Eight preflight contracts, 1,078 parity profiles and all 41 adapters
pass. Perforce predicates/order and all build/consumer architecture remain intact.
No push, release monitoring/retry, user-data operation or server submission.
