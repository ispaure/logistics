# Ecosystem architecture audit

## Current assessment after the October 23 maintenance pass

This section summarizes the latest implementation; the baseline and earlier
checkpoints below retain their original scope. Source snapshot: Logistics
`e755287d`, commonUtils `288ccbb`, Blue Hole `098f3f1`, all on dedicated local
maintenance branches. Both consumers pin the exact same shared content. No
remote push, release, dependency installation or persisted-format migration.

The [follow-up review](overnight_progress.md#follow-up-review-of-all-maintenance-changes)
found no additional runtime defect. It clarified shared extraction documentation
and removed test whitespace without changing its AST. Both consumers now pin shared
`e2f18fd` (Blue Hole `0edf0d2`); production behavior and the implementation metrics
below are unchanged. The follow-up records fresh host suites and their skips.

| Repository | Baseline → current production lines | Baseline → current test lines | Python files |
| --- | ---: | ---: | ---: |
| Logistics | 89,213 → 89,510 | 75,541 → 76,703 | 1,152 → 1,152 |
| commonUtils | 42,360 → 42,533 | 22,128 → 23,426 | 506 → 509 |
| Blue Hole | 22,806 → 22,804 | 525 → 771 | 201 → 203 |

Composition spans (including the definition line) are Bulk Rename 227 → 31,
LM 200 → 40 and Blender 197 → 39. Their private builders remain in existing
modules; the composition-only transformations preserve expanded statement trees.
These figures show clearer responsibility boundaries, not deleted functionality.

Counts use the original tracked-source exclusions. New shared files are the
optional presentation owner and portable batch/wiki test owners; Blue Hole adds test
drivers. File count and line count are not quality scores.

| Dimension | Implemented evidence | Remaining limit |
| --- | --- | --- |
| Readability | Bulk Rename, LM and Blender construction now have named, cohesive builders in their existing modules; expanded statement trees preserve construction order. Failure paths name their publication/cleanup phases. | Large mobile composition, index and Blender UI owners still need domain review; length alone does not justify splitting them. |
| Modularity | Native browser lifecycle/package imports stay portable; optional presentation has a separate owner with preserved public exports. Stream completion, bounded reads/hashing and publication mechanisms stay in existing reusable owners; application policy stays in consumers. | Framework-specific composition and callback ownership remain substantial. |
| Testability | New fault profiles reproduce late edits, replaced backups, short/nonblocking I/O, empty worker failures, oversize state and stale widgets. Real rclone, embedded Blender, Chromium DOM and owned iPhone/iPad fixtures complement isolated host suites. | Device/runtime coverage is bounded; skipped tests and earlier failed attempts remain recorded. |
| Coupling | The real Blue Hole pie presentation cycle was removed with descriptors/bindings preserved. Reviewed unused imports reduce the configured host adapter count from 25 to 24; policy reports 15 feature edges and zero violations. | All-import candidate groups are 27 / six / two; shared query reuse merges candidate groups, growing the largest from 91 to 105 modules. Module-scope groups remain zero / two / two. A merger is not cycle elimination, and deferred groups are not proven runtime failures. |
| Duplication | Atomic JSON/XML/INI publication, provider copies and complete byte writes use existing shared owners. Only stable mechanics move into commonUtils. | Exact repeated production bodies of 20+ lines were absent both before and after; near-duplicate workflows are not exhaustively eliminated. |
| Consistency | Both applications track the same verified shared revision. Error/cancellation contracts, read/write size bounds, name selection and content manifests are explicit and regression tested. | Platform-specific filesystem semantics still require native validation. |
| Reliability | Verified moves/rollback preserve changed or surviving copies; archive publication checks late source identity; LocalCrypt rejects incomplete input; queued Qt work retires with native owners. | Filesystem revision checks are optimistic samples, not arbitrary-writer isolation. Native pickers, original iPad scene closure and some target platforms remain unverified. |

The conservative graph inventory is Logistics 659 modules / 1,610 edges,
commonUtils 326 / 956 and Blue Hole 196 / 586. Module-scope edges are 859 / 780 /
569. The module-scope shared groups are the Qt facade and command package; Blue
Hole retains environment and project-filter groups. The command group includes
parent-package export/submodule edges. No broad cycle
rewrite was attempted without matching runtime evidence. Shared junction reuse
adds three explicit import edges and merges conservative all-import groups; this
is a recorded coupling tradeoff, not an improvement inferred from the lower count.

The same source package passes all 2,220 manifest hashes and real offscreen
startup after fresh extraction. Owned fixtures exercise Bulk Rename, expanded
LM controls and Blender preset settings without provisioning or launching Blender.
All 1,864 tracked Python sources compile without writing bytecode. Configured
lint, compatibility, hygiene and architecture checks pass; no type checker is
configured.

Desktop/mobile retain `e755287d` / `288ccbb` unchanged throughout their full
runs. The shared full suite completed at the same shared revision, before the
later mobile-only change:

| Validation | Executed result | Scope |
| --- | --- | --- |
| Desktop | 179 files, 1,685 cases, zero skips/failures | Includes all six native bridge scenarios using the separately recorded cached dylib. |
| Mobile host | 162 files, 1,163 cases, zero skips/failures | Toga dummy plus both real headless Chromium DOM fixtures, using existing runtimes. |
| Shared | 181 files, 1,232 cases, 25 skips, zero failures | Shared `288ccbb`, with root `fc6438b8`; later changes affect only mobile input. |
| Blue Hole adapters | 33 cases pass | Exact shared membership/bytes and recorded revision also match. |
| Embedded Blender | 161 cases, one filesystem skip, zero failures | Blender 4.5.1 / Python 3.11.11; syntax and selected portable contracts only. |
| Native iOS | 33 acceptance cases on each owned simulator | Earlier source snapshot below; independent-window gate required on iPad. |

Counts are per suite, include skipped cases, and are not unique-case totals across
runtimes. Earlier sandbox watcher failures, resource-sensitive setup timeouts and
fixture mistakes remain in the work log with their subsequent scoped reruns.
Assertions/timeouts were not weakened. The initial baseline failed five shared,
eleven desktop and two mobile files, including environmental/harness issues;
those raw failures must not be conflated with later deliberately failing regressions.

Native iPhone and iPad reports belong specifically to `b3031665` / `178f5da`:
33 acceptance cases pass on each, with actual independent-window/draft and
second-scene close/restore coverage on iPad. Original launch-scene closure and
native system picking are explicitly unverified. Embedded Python is 3.12.10 on
iOS 27.0; existing bridge archives were reused with recorded hashes. Both owned
simulators were deleted and their disposable worktree archived after evidence
preservation. No Boox test app was installed or changed.

Blue Hole's exact current copy passes 33 consumer adapters and 161 embedded
portable/syntax cases (160 pass, one filesystem skip) on Blender 4.5.1 / Python 3.11.11.
The driver also compiles vendored production sources without importing optional
toolkits. Metadata scanning and wiki traversal now reuse the existing junction
query after both APIs reproduced Python 3.11 pathlib failures. Three unchanged
wiki tests have a portable test owner. These results do not validate registration/
export on target Blender 5.2.2.
Windows/Linux native checks, a connected Android/Boox run, live Perforce and
original-scene/system-picker behavior remain outside the executed evidence.

Six host bridge scenarios also execute against an existing cached macOS dylib:
listing, encrypted text/metadata/large-file round trips, comic passwords, remote
readers and mobile file operations. Its recorded build info has vcs.modified=true;
exact source provenance is unknown and no fresh Go build was performed. A native
short-read fixture reproduced three-byte-only encoding before the mobile bounded
read fix, then preserved full input afterward. Oversize/would-block inputs are
rejected before encoding; their staging cleanup is checked independently.

Reliability, consistency and testability have stronger evidence than whole-system
structural simplification. The original approximate 5/10 was not independently
measured, and an unqualified 7/10 is not supported by an agreed rubric. The
specific changes and limits above are the defensible before/after assessment.

Next priorities are target Blender 5.2.2 registration/export; native Windows/Linux
filesystem and process contracts; physical device picker/scene lifecycle checks;
and deeper responsibility/identity review of mobile composition and offline index
generations. Preserve existing APIs and establish regressions before further moves.

## Scope and baseline (October 22, 2026)

This is a fresh assessment of already substantially refactored repositories, not
confirmation of the proposed 5/10 starting score. All three worktrees were clean.
Dedicated `codex/ecosystem-maintenance` branches start from:

| Repository | Checkout / original branch | Baseline commit |
| --- | --- | --- |
| Logistics | `/Users/marca/GIT/logistics`, `alpha` | `f5bbf252` |
| commonUtils | Logistics `Python/commonUtils` Git submodule, `main` | `07e8363` |
| Blue Hole | `/Users/marca/GIT/BlueHole`, `blender-5.2.2/alpha` | `c6608c4` |

Logistics pins commonUtils; Blue Hole vendors that exact revision inside
`Lib/commonUtils` and records it in `Lib/commonUtils.revision`. Namespaces remain
independent. No application-specific discovery or policy belongs in the library.
The external emulation checkout is excluded from this initiative.

## Measurements

Tracked Python files only; physical lines including comments/docstrings/blank
lines. Excluded submodules, vendored `Lib`, generated Deluxe keymap payload,
build output, virtual environments and caches. Tests include nested `tests/`
and `test_*.py`; native device fixtures are under `native_tests/tests/`.
These counts measure source size, not complexity or quality.

| Repository | Python files | Production lines | Test lines | Test/support files | Maximum parent depth |
| --- | ---: | ---: | ---: | ---: | ---: |
| Logistics | 1,152 | 89,213 | 75,541 | 453 | 5 |
| commonUtils | 506 | 42,360 | 22,128 | 181 | 3 |
| Blue Hole | 201 | 22,806 | 525 | 5 | 5 |

Largest production modules include Logistics `mobile/app.py` (1,282 lines),
`mobile/workspace_navigation.py` (890), `mobile/folder_hub_ui.py` (819);
commonUtils `ui/file_browser/__init__.py` (669), `ui/workspaces/workspace.py`
(617), `ui/native/navigation.py` (616), `filesystem/index/store.py` (609);
Blue Hole `preferences/environment/bridge_props.py` (779), `operators/add_ops.py`
(671). Large test files are not production refactor targets.

Large production functions include Bulk Rename widget construction (227 lines),
LM layout (200), Blender feature layout (197), shared Markdown construction (179),
Apple image-canvas backend (166), index scanning (153), Blue Hole bridge drawing
(344), filtering (272) and container drawing (204). Largest classes include
Logistics' mobile App, shared FileBrowser/Workspace, and Blue Hole's bridge
property group. These combine framework construction with domain responsibilities;
line count alone is insufficient justification for splitting them.

AST comparisons of exact function bodies of at least 20 lines found no repeated
production bodies. This does not exclude near-duplicates or cross-project policy
similarity. Manual inspection found editor shortcut persistence reimplementing
shared staging/flush/fsync/replace mechanics.

## Architecture and contracts

Logistics composes `desktop/`, `mobile/`, `services/` and feature owners; factories
in `features.application.registry` support lazy feature loading and optional
dependencies. Desktop uses PySide6; mobile has separate native adapters. Shared
filesystem, archive, persistence and runtime mechanisms sit below optional Qt and
native presentation. Blue Hole registration is in its root add-on `__init__.py`;
Blender actions/operators/preferences depend on vendored reusable mechanisms.

The configured architecture check passes: 25 reviewed feature-to-host adapters,
15 cross-feature edges, zero violations. These approved upward dependencies and
lazy import strings remain cycle risks; static approval is not proof that every
runtime import graph is acyclic. No new layer or import compatibility shim is
justified by the inspected consumers. Existing package exports, deferred factory
strings, registry ownership and cooperative close protocols must be retained.

Persisted contracts include INI defaults/personal overrides, editor text encoding,
BOMs/newlines, JSON project/session/recovery stores, index SQLite generations and
Blue Hole environment INI/preferences. Atomic writes do not supply cross-process
locking. Command and worker results distinguish failed startup, cancellation,
publication and incomplete source cleanup. Never infer success from progress alone.

## Toolchain and baseline checks

Logistics pins Python 3.12.2 and PySide6 6.12.0 in `Python/pyproject.toml` and its
uv lock. Both existing desktop and mobile environments pass `dev.py doctor`.
commonUtils has no independent dependency manifest; CI uses Logistics' environment
and runs isolated test modules on Windows/macOS/Linux. Blue Hole consumer CI uses
Python 3.12.2, while add-on metadata targets Blender 5.2.2. This host interpreter
is not proof of compatibility with Blender's embedded Python.

Fresh architecture, dependency-pin consistency, source hygiene and configured
correctness lint checks pass. Full desktop, shared and mobile isolated suites and
Blue Hole adapter tests were started before implementation; results and any
baseline failures are recorded in the work log. No static type checker is
configured. Release packaging and documentation tools are inspected separately.
No compatible Blender executable was found under `/Applications`; no live Blender,
Perforce server, Windows/Linux desktop or mobile device validation is claimed.

## Prioritized remediation

1. **Publication and recovery:** test promotion races before changing shared
   primitives. Existing `Path.rename` can overwrite a destination created after
   preflight or during rollback. Preserve the old installation, new stage and
   racing content; retain recovery locations when automatic restoration fails.
2. **Editor persistence:** consolidate shortcut publication through the existing
   shared atomic writer, retaining JSON shape and rolling back live bindings on
   any failed save. Check temporary QAction lifetime on invalid input.
3. **Archives:** review complete staged extraction/publication and failure cleanup.
   Avoid recursive removal of externally modified output after publication races.
4. **Project/settings stores:** validate malformed input and all-or-nothing loading;
   preserve stored data on failure and reject accidental overwrite.
5. **Git boundary:** retain captured argument lists, option terminators and command
   outcomes. Review backup/restoration and conflict writes with isolated repos.
6. **Consumers:** update the exact committed shared pin/vendor together, run
   actual-vendor adapter tests and verify vendored membership/bytes. Blue Hole
   changes should remain integration-focused.
7. **Deferred architecture:** offline volume identity/index retention, complex
   native UI lifetimes and Blender-native behavior require explicit contracts and
   platform evidence before larger migrations.

Do not assign a 7/10 outcome from these measurements. Assess readability,
modularity, testability, coupling, duplication, consistency and reliability from
verified changes, and retain platform limitations in the final assessment.

## Follow-up import-risk inventory

A conservative AST graph includes imports inside functions and conditional blocks,
resolves relative imports and records edges to known project modules. It excludes
tests/vendors and does not execute registration or resolve arbitrary dynamic
strings. Its initial snapshot records:

| Repository | Modules | Internal edges | Potential cyclic groups | Largest group |
| --- | ---: | ---: | ---: | ---: |
| Logistics Python tree | 659 | 1,612 | 27 | 40 |
| commonUtils | 326 | 941 | 7 | 91 |
| Blue Hole | 196 | 597 | 1 | 80 |

These are **potential cycles including deferred imports**, not demonstrated
startup failures. The large shared group includes filesystem/formats plus lazily
opened presentation; Logistics groups include desktop browser/document routing
and mobile presentation; Blue Hole's group spans registration, actions, containers
and preferences. The configured boundary check and consumer import tests pass.
Changing these groups safely requires distinguishing eager initialization from
intentional deferred cross-references; broad graph-driven moves are deferred.

## Before/after assessment at the first checkpoint

| Dimension | Baseline evidence | Implemented improvement / remaining limit |
| --- | --- | --- |
| Readability | Shortcut save reimplemented staging; installation error paths obscured recovery state | Shortcut publication delegates to its shared owner; promotion and IDE admission have explicit phases. Large UI construction/filter functions remain. |
| Modularity | Existing feature owners and grouped shared packages already in place | Kept all production modules and entry points recognizable; no package moves or new abstraction layers. This pass does not claim a whole-repository modularity transformation. |
| Testability | Extensive tests existed, but some used default shared storage and optional Toga failed discovery | Regression runner isolates default storage/preferences before discovery; new failure regressions and optional-backend execution cover the changed contracts. Device validation remains separate. |
| Coupling | 25 approved host adapters, 15 cross-feature edges and deferred cyclic groups | No added feature-to-feature edges. Blue Hole and archive extraction consume the existing publication primitive. Large deferred graph groups remain. |
| Duplication | Shortcut writer repeated shared staging/fsync/replace logic | Removed that duplicate and reused shared verified promotion in Blue Hole. No exact repeated production function bodies of 20+ lines found; near-duplicates are not exhaustively eliminated. |
| Consistency | Similar mutation paths had different collision and cleanup behavior | Shared promotion and complete archive extraction use no-replace publication. Invalid IDE state is admitted atomically; shortcut failures restore live state. Atomic publication still is not multi-file locking. |
| Reliability | New tests reproduced overwritten racing files, partial extraction visibility, changed shortcuts after failed save, partial IDE admission and damaged Blender preferences | The reproduced cases pass after fixes, with exact vendor verification and consumer tests. Native Blender, Windows/Linux and actual device behavior remain unverified. |

At that checkpoint, measured production/test lines totaled Logistics 89,215 / 75,645,
commonUtils 42,363 / 22,250 and Blue Hole 22,814 / 580. Python file counts are
unchanged. Small production-line changes accompanied substantial targeted failure
coverage; line reduction itself was not used as a quality score.

No numeric 7/10 outcome is asserted. This pass provides evidence for incremental
reliability, testability and persistence consistency gains. An ecosystem-wide
score needs an agreed rubric, deeper review of remaining cyclic groups and native
consumer evidence. See the [work log](overnight_progress.md) for executed checks
and precise limits.

## Continued work assessment (October 23, 2026)

The first checkpoint was followed by further implemented, committed repairs.
The original measurements above remain the baseline. At committed checkpoint
Logistics `544116f1`, commonUtils `7978a28` and Blue Hole `f50fa424`, tracked Python
counts are Logistics 1,152 files (89,375 production / 76,255 test lines),
commonUtils 507 (42,494 / 23,093) and Blue Hole 201 (22,814 / 580), using the
same exclusions. Exact repeated production function bodies of 20+ lines remain
absent under the same AST comparison; this does not establish no near-duplication.

| Dimension | Additional evidence and limits |
| --- | --- |
| Readability | Git preference adoption owns saved fields and their conflict baseline, replacing repeated UI assignments. INI publication and provider stream loops use existing shared owners. Large UI construction methods remain. |
| Modularity | Native browser presentation moved intact into its owner module; package and lifecycle imports work without Toga or Qt. Existing public exports retain identity. A private Bulk Rename tree owns deferred layout preservation and accepts an independent Qt model for testing. No broad feature moves were justified. |
| Testability | New regressions exercise damaged backups, late source changes, short/nonblocking streams, empty worker failures, stale settings and checkpoint size conflicts. Native Toga fixtures run in the mobile environment rather than treating missing desktop dependencies as coverage. |
| Coupling | The architecture policy still reports 25 approved host adapters, 15 feature edges and zero violations. Portable lifecycle imports no longer require a toolkit. Deferred import groups and live consumer coupling remain. |
| Duplication | Local provider copying/verification and bounded text reads use shared stream mechanisms. INI delegates staging, verification, permissions and replacement to the atomic writer; saved preference adoption sits in Preferences. Application-specific credential and cleanup policy stays with consumers. |
| Consistency | Legacy File/Directory operations and local document exports respect existing provider guards. Cross-volume moves verify copied content and revalidate sources before cleanup; settings writers retain their own published bytes. These remain optimistic checks, not filesystem isolation or cross-process locks. |
| Reliability | Reproduced data-preservation failures have focused regression coverage. Shared revision 7978a28 passes all 179 files; both consumers track it exactly, with verified Blue Hole membership/bytes and 31 passing consumer tests. Late folder layouts, short reads and post-save bounds have dedicated regressions. Windows/Linux, real Android/iOS pickers, Blender and live Perforce remain unverified. |

Reliability and testability have stronger evidence than whole-system structural
simplification. A numeric 7/10 remains unsubstantiated: the remaining large UI
owners, intentional deferred cycles, platform contracts and native runtime
evidence still need deeper review. No dependencies, storage formats, release or
remote history were changed. The work log records each completed unit and its
validation; generated reports and package artifacts remain ignored.

A later immutable Logistics `07e76ab2` / shared `7978a28` checkpoint passes all
179 desktop, 162 mobile and 179 shared isolated test files, with platform/toolkit
skips recorded separately in the work log. Another 106 tests in 25 native Toga
files pass in the mobile dummy backend. Subsequent IDE bounds, metadata lookup,
PDF startup, Blender publication and settings-reset repairs have their focused
regressions recorded independently; the immutable totals exclude those later fixes.

Further publication cleanup makes JSON and XML use the existing atomic writer,
retaining format-specific policies; legacy text exports retain streaming/in-place
semantics while validating encoding and destination access before mutation.
The new range-buffer, batch-success and archive-preview tests exercise ordinary
portable contracts alongside fault injection. Blender installation/presets/cache
now share no-replace publication. Settings reset retains the old backup when an
external directory occupies its path, rather than treating arbitrary current
contents as its owned rollback output. These changes improve consistency without
adding production packages or cross-feature policy layers.

## Later verification and structural assessment

At Logistics `b98da89a`, shared `86a5d51`, Blue Hole `5c63af4`, the same tracked-file
measurement gives 1,152 / 508 / 203 Python files, respectively; production/test
lines are 89,399 / 76,342, 42,502 / 23,201 and 22,804 / 757. The added shared files are the native-browser presentation owner and portable
batch-test owner; Blue Hole adds consumer test drivers. No new
production package or dependency was introduced. Exact repeated production bodies
of at least 20 lines are still absent under the same comparison.

Bulk Rename widget construction is now a short composition of three cohesive
private builders in its existing module; expanded statements match the original
constructor AST. This improves navigation without moving state into new objects.
Natural sorting for filesystem paths, portable browse labels and comic pages now
uses one standard-library filename owner. Raw/tagged keys and persisted index
encoding match all 2,006 previously supported comparison cases, while superscript
and circled numerals no longer abort listings. Reader state uses bounded reads;
comic badge total and position come from one admitted snapshot.

The conservative all-import graph now records Logistics 1,612 edges / 27 groups
(largest 40), shared 953 / 7 (91), Blue Hole 586 / 2 (35). A separate module-scope
inventory excludes function/lambda and TYPE_CHECKING imports: Logistics 861 edges
and no candidate groups, shared 777 and two groups, Blue Hole 569 and two groups.
Neither static graph resolves arbitrary dynamic imports or proves absence of
runtime cycles. Shared candidates are the Qt facade bootstrap and command package
exports; Blue Hole candidates are environment/context and project/filter helpers.
The actual pie action/menu declaration cycle was removed using the existing menu-ID
contract. All 46 serialized descriptors, 22 bindings and catalog order are unchanged.

An existing Blender 4.5.1 LTS executable was subsequently found in managed software
storage. Its real embedded Python 3.11.11 passes 98 selected portable/vendor cases
with one filesystem skip, using a factory startup and temporary user profile.
All 33 host adapter cases and the exact vendor checker pass. Blender 5.2.2 add-on
registration, operators, export workflows and native UI are still unexecuted;
older-runtime contract checks do not establish target-runtime compatibility.

Frozen shared `86a5d51` passes all 180 files (1,220 cases, 25 skips); frozen mobile
Logistics `f4e35aee` passes 162 files (1,161 cases, two Node/Playwright skips).
The prior desktop `5e22726b` checkpoint passes 179 files (1,664 cases, six skips).
A desktop run at `f4e35aee` is ongoing. The later reader-state unit has separate
52 book/seven comic checks. A freshly extracted `5e22726b` package starts the real
application offscreen with an isolated profile, opens a fixture in Bulk Rename,
retains the reserved tools menu and exits normally. No device/native desktop
focus behavior, real user settings or target Blender registration is implied.

These results strengthen readability, duplication ownership, testability and
reliability. Existing feature boundaries remain recognizable and policy checks
remain at 25 reviewed host adapters, 15 feature edges and zero violations. The
remaining large native UI owners, deferred graph groups and unexecuted platform
contracts prevent an evidence-based ecosystem-wide 7/10 assertion. Continue with
cohesive layout simplification and native lifecycle contracts; retain API/data
compatibility and focused review rather than optimizing graph or line counts.

## Subsequent composition and admission checkpoint

At Logistics `a4e10aba`, shared `73a8c86`, Blue Hole `53ec9cb`, tracked production/
test lines are 89,436 / 76,450, 42,511 / 23,249 and 22,804 / 758; file counts
remain 1,152 / 508 / 203. LM layout composition fell from 200 to 40 lines by
using three cohesive private builders in the same module. The expanded AST is
identical; all 115 existing LM cases pass. No page state or new layer was added.

Command pipe read errors now propagate after supervised cleanup instead of
silently becoming EOF; timeout/cancellation retain their outcomes. Both interpreters
pass the new fault profiles and existing capture contracts. IDE search/preview,
optional gutter markers and Git decorations recover from worker admission failure
using their existing UI state and retry paths. Focused tests reproduce each prior
failure and exercise successful retries. Reader writes now enforce the existing
read limit before publication, preserving the prior readable checkpoint; Unicode
byte bounds and last-state preservation are tested in both environments.

The previous frozen `f4e35aee` checkpoint completed all 179 desktop files (1,668
cases, six skips), 162 mobile files (1,161, two skips) and 180 shared files (1,220,
25 skips). The subsequent `f15fdb8c` desktop integration run is ongoing; its shared
`73a8c86` suite completes 180 files / 1,222 cases / 25 skips, and mobile completes
162 / 1,161 / two skips, all without failed files. Later write-bound tests are
recorded separately. Real embedded portable coverage is now 141 cases, with 140
passing and one filesystem skip; target Blender registration remains unexecuted.

The scoped optional unused-import review is not a new quality gate. Its 46
candidates include intentional exports and consumer patch targets, so no bulk
removal was performed. Configured correctness lint remains green. Remaining
priorities are native target/platform validation, large mobile UI responsibilities,
offline index identity contracts and individually reviewed import/API cleanup.
These bounds still do not support an unqualified numeric ecosystem score.

## Further persistence and rollback validation

At Logistics `572250fe`, shared `178f5da`, Blue Hole `3b679c3`, production/test
lines are 89,498 / 76,633, 42,521 / 23,278 and 22,804 / 758; Python file counts
remain 1,152 / 508 / 203. No exact repeated production bodies of 20+ lines are
found. The potential all-import groups remain 27 / seven / two; module-scope
candidate groups remain zero / two / two. Private UI import review removes five
proven unused leaf imports while retaining intentional exports and patch targets.

Comic metadata preparation now enforces its existing read limit on encoded edited
XML before any batch write. EPUB failure cleanup verifies the created backup's
identity before trusting/removing its pathname. LM and workspace restoration read
within their existing limits. LM moves verify destination content, recheck path
revisions and preserve recovery copies when source/copy state changes. Seven
fault profiles reproduce prior lost-copy/newer-edit failures; all 118 LM cases pass.
Optional bounded hashing remains in the existing stream/snapshot owners, with
unchanged default behavior. No application policy moved into commonUtils.

The complete frozen `f15fdb8c` / `73a8c86` checkpoint passes desktop 179 files /
1,675 cases / six skips, shared 180 / 1,222 / 25 skips and mobile 162 / 1,161 /
two skips. Later units have focused evidence in the work log. The two browser DOM
cases subsequently pass in actual headless Chrome using the existing bundled
Node/Playwright runtime and temporary profiles, without installing dependencies.
The raw full-run skip counts remain accurate for their original environment.
Embedded Blender portable coverage is now 143 cases (142 pass, one filesystem
skip); all 33 adapters and exact vendor membership/content checks pass.

A later native-tool inventory found installed iOS 26.5/27.0/27.1 simulator runtimes,
all existing devices shut down, and no connected Android device. Native iOS
validation is therefore being prepared with an owned simulator/build. This is
not yet a passing native result. Target Blender 5.2.2 registration and native
Windows/Linux remain unexecuted. The 7/10 target still needs broader structural
review and platform evidence; line counts or added tests alone do not certify it.
