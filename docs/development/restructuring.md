# Architecture restructuring assessment

Status: historical October 16 assessment with subsequent implementation records.
The [developer index](development.md) and owning guides describe current contracts.
See [the October 21 implementation record](restructuring.md#october-21-developer-maintainability-pass)
for the incremental developer-tooling and controller changes.

[Developer index](development.md) · [Current code map](code-map.md)

This page is a historical assessment and migration record, not the onboarding
checklist. Use [feature conventions](features.md) and the current code map for
new work. Larger source refactors remain separate from onboarding/tooling.

For the work identified against the October 20 working tree, see the
[feature ownership audit](ownership-audit.md). Its local implementation builds on the completed migrations below.

Assessment: October 16, 2026. This proposal records the initial local source tree;
the implementation status below distinguishes completed local work from plans.
The goal is to make ownership predictable for a new programmer while retaining
the existing feature and platform boundaries.

## Local implementation status

The subsequent ten-item ownership pass is implemented. The [sequential feature refactors](#sequential-feature-refactors) and integration audit below describe the current layout; the original assessment and baseline candidates remain historical context.

The first LM pass is implemented locally: desktop presentation lives in `ui/`,
widget/layout/profile responsibilities have separate modules, and `session.py`
owns conversation records, leases, saving and streaming response transitions.
Root-level presentation imports remain compatible. The page retains navigation,
transport dispatch, timers and close prompts. See the
[LM module map](../../Python/features/lm/docs/development/development.md) for the current owners.
The mobile pass adds composed Open/Save As and saved-import controllers, explicit
host service/state access and workflow-local picker cancellation. Git history,
search and preview orchestration now has a composed controller using its existing
sequential job owner. Blender's main/preset and addon-library presentation now
lives under `ui/`, with a separate layout builder and compatible root imports.
See the [mobile map](mobile-runtime.md),
[Git owners](../../Python/features/git/docs/development/development.md), and
[Blender owners](../../Python/features/blender/docs/development/development.md).

Shell and infrastructure naming has been reassessed: keep `desktop` and the
feature infrastructure import paths stable during these migrations. The
[feature infrastructure map](feature-infrastructure.md) and
[host service map](services.md) make their ownership explicit.
Tests also keep their current flat layout to preserve Qt module isolation and CI
discovery; [owner-to-test pointers](testing.md#find-the-tests-for-your-change)
provide navigation without a test-runner migration. Further feature moves and
remaining host mixin extractions are incremental follow-up work.

The baseline module sizes and candidates below describe the initial assessment.

## What already works

Feature packages are the right primary unit: Git, LM, Books, Comics and rclone
already own recognizable behavior. Feature registration supplies extension
points instead of requiring every tool to be wired directly into the shell.
Portable format logic, mobile adapters and the separate commonUtils submodule
provide useful boundaries. Preserve these rather than flattening the project
into repository-wide `controllers`, `widgets` and `utils` folders.

## Priorities

| Priority | Observed obstacle | Recommended change | Completion evidence |
| --- | --- | --- | --- |
| 1 | The developer index mixes first steps with specialist mobile plans and evidence reports | Put a short onboarding path and task-to-code map first; keep specialist guides available below | A newcomer can find an entry point, owner and focused test from one page |
| 2 | Feature presentation has inconsistent placement: Git uses `ui/`, LM and Blender have root `page.py`; Books has root desktop reader code plus `mobile/` | Establish a convention for new code, then migrate individual features as they are changed | Registration, imports, readers and payload checks still resolve after each migration |
| 3 | `LogisticsMobile` inherits many host and feature UI mixins; state and callbacks cross those classes through `self` | Replace one workflow at a time with a composed controller and explicit host services | Controller state has one owner; multi-window, stale-result and close tests pass |
| 4 | Large presentation modules combine independently changing workflows | Extract by responsibility, beginning with LM conversation lifecycle and mobile editor file selection | Existing behavior tests pass without depending on a larger shared app object |
| 5 | `features/` contains both optional packages and registry/settings infrastructure; `services/` spans several domains | Document these exceptions now; consider a named application infrastructure package only after feature cleanup | One documented import direction, with stable registry APIs during migration |
| 6 | Tests live in two host suites plus native scenarios; grouping is mostly by filename | Publish owner-to-test pointers first; evaluate directory grouping separately | Every test remains discoverable and Qt module isolation remains intact |

Priority 1 is addressed by the accompanying code map and onboarding links. The
LM/Blender passes address feature presentation consistency; the mobile and Git
passes extract the named workflow candidates. Infrastructure/test ownership is
documented while existing import/discovery contracts stay stable.

## Feature convention

Use this as a destination for features that need these layers, not a mandatory
set of empty folders for every small tool:

```text
Python/features/<stable_id>/
    __init__.py          # lightweight registration entry point
    contributions.py    # declarations, when registration needs its own module
    config.ini          # feature defaults
    <domain modules>.py # portable behavior, named for their purpose
    ui/                 # desktop Qt presentation
    mobile/             # mobile presentation/adapters when supported
    README.md           # short link to the developer guide
    docs/
        docs.md         # feature wiki landing
        development/development.md # implementation and test pointers
        user/user.md    # canonical desktop user guide
        user_mobile/user_mobile.md # where supported
    user_docs/
        index.md        # in-app compatibility link
    mobile_sources.json # payload allowlist where supported
```

Portable modules must remain importable without loading Qt or Toga. Desktop and
mobile presentation can depend on the portable core. Host composition decides
navigation, session ownership and application policy. Shared toolkit mechanisms
stay in commonUtils, whose own documentation remains authoritative.

Keep feature IDs, saved configuration keys and lazy registration references
stable. An import-compatible forwarding module may be needed during a move.
Do not move core browser or Bulk Rename into duplicate feature packages.
Retain `DestinationRail.tools_menu` and the reserved Misc glyph.

## Concrete extraction candidates

These local line counts are indicators of review effort, not architectural
limits or reasons to split a module on their own.

| Current module | Evidence | First useful boundary |
| --- | --- | --- |
| `Python/features/lm/page.py` (~1,385 lines) | Contains composer widgets, profile selection, conversation selection, edit leases, persistence, generation and closing | Move composer widgets into feature `ui/`; then give conversation persistence/lease/generation lifecycle an explicit controller, retaining GUI-thread timers and close vetoes |
| `Python/mobile/files_ui.py` (~908 lines, active local edits) | Contains file mutations, editor Open/Save As selection and comic batch entry points | Extract editor picker state and callbacks as one owned workflow; keep privacy checks, provider identity and cancellation explicit |
| `Python/mobile/app.py` (~938 lines) | Composes many UI mixins and owns startup plus document operations | Keep startup as the composition root; introduce owned controllers incrementally, following the explicit services already used by `reader_host.py` |
| `Python/features/git/ui/repository_view.py` (~966 lines) | Coordinates rendering, previews, history search and repository commands, with jobs/layout already extracted | Follow existing job ownership; separate history/preview orchestration before adding more UI mixins |

The mobile reader cleanup already moved format presentation into Books/Comics
and added explicit reader host services. Build on that work; the historical
baseline in the [mobile roadmap](mobile-architecture-roadmap.md) does not describe
all current code. Its completed extractions should not be proposed again.

## Migration order and safeguards

1. Use the code map to establish the vocabulary: desktop shell, feature,
   mobile host, build tooling and shared library. Add module/test pointers to
   feature developer READMEs when touching them.
2. Pilot the feature presentation convention on LM. Separate simple widgets
   first, then lifecycle ownership. Verify streaming, persistence failure,
   lease release and cooperative closing before proceeding to other features.
3. Extract the mobile editor picker after the active Workspaces work settles.
   Update `mobile_build/tools.py` in the same change; exercise host tests, packaging
   checks and native Open/Save As behavior across Local/LocalCrypt providers.
4. Reduce mobile host inheritance one workflow at a time. Preserve multi-window
   writer ownership, cancellation, navigation generations and private content
   cleanup. A file move alone does not establish those contracts.
5. Reassess shell and infrastructure names after those boundaries are clearer.
   `desktop` is misleading but a global rename has less immediate value than
   clarifying ownership. A future rename must update lazy references, tests,
   packaging and launchers together.

Do not reorganize tests into nested directories as an incidental cleanup:
`Python/tests/run_regressions.py --isolate-modules` currently requires a nonempty
flat directory. Update the runner and CI discovery before changing that layout.
Do not edit generated Briefcase projects as the canonical source, package the
whole desktop tree into mobile, or copy shared-library implementation into
Logistics to simplify imports.

The initial assessment involved source/documentation inspection. Subsequent
implementation is verified with relevant host regressions, packaging checks and
correctness lint. Native-device acceptance is separate; source moves and host
tests do not certify device appearance or native interactions.

## Sequential feature refactors

Each item is validated and committed separately. Feature IDs and stored formats remain stable.

### 1. LM mobile ownership

Mobile chat storage, transport and presentation now live in `features/lm/mobile/`. Desktop SSE framing lives in portable `features/lm/streaming.py`; desktop transport retains its public import. The host retains only navigation/composition and its synthetic server fixture. Mobile limits, data locations and persisted formats are unchanged.

### 2. rclone host boundary

rclone mobile adapters no longer import `mobile`. Provider readers, document limits and native archive facades have neutral service owners. `MobileHostUI` declares presentation hooks; `mobile/composition/presentation.py` supplies them. The app composes provider presentation rather than inheriting it through the rclone feature.

### 3. Mobile workflow composition

The app now composes Chat, Cloud, Transfers, Workspaces, Home/Documents, Locations and Storage controllers. Each controller enumerates its host dependencies and owned fields; compatibility accessors delegate to that owner without broad attribute forwarding. Transfer/review cancellation is separate from file/cloud cancellation and global Cancel dispatches to both. Reader/session managers and host/provider document lifecycle retain their existing composition.

### 4. Text Editor mobile ownership

`features/text_editor/mobile/ui.py` owns native editor presentation; `resources.py` owns provider text adapters and `names.py` owns portable name validation. Managed recovery storage, picker orchestration and scene/workspace identity remain host-owned. Shared persistence primitives continue to supply text encoding/conflict behavior. Editor and LM presentation receive host appearance/menu/export hooks explicitly and no longer import the mobile application package.

### 5. Nest substantial workflows in each feature

Blender now owns `installation/`, `presets/` and `addons/`, with addon-library UI under `addons/ui/`. Main Blender presentation remains its feature-level composition UI. rclone owns `transfers/` and `localcrypt/`, each with desktop `ui/` and mobile adapters beside its domain behavior. Imports, Blender script/config resource paths and curated mobile sources are migrated together. Feature IDs, persisted settings and application navigation stay unchanged.

### 6. Desktop presentation ownership

Books, IDE and Text Editor now keep desktop widgets/controllers under their own `ui/` packages. Portable EPUB, metadata, project/analysis and preference modules stay outside presentation. Books Qt chapter conversion stays separate from mobile WebView conversion. Shared IDE/Text Editor change-marker integration lives in neutral `services/editors/ui/`, outside feature discovery infrastructure. Lazy registrations and configuration resource paths are updated.

### 7. Feature-owned format mutations

Books and Comics own metadata plans, archive rewrite requirements and structural validation in `mutations.py`. Desktop mutation paths, mobile library transactions and LocalCrypt adapters use those owners. The mobile library retains UUID/checksum records, conflict checks, durable journals and atomic publication. `services/documents/metadata.py` remains a thin compatibility dispatcher; it contains no format implementation.

### 8. Shared portable image validation

Bounded PNG/JPEG/WebP validation lives in `features/images/validation.py`. Books, Comics and provider readers use that owner; EPUB rendering no longer imports Comics mobile implementation. Existing byte/dimension/animation limits are preserved. Only the portable image helper and lazy package entry point enter the mobile payload.

### 9. Host service domains and portable preparation

Document adapters, limits, metadata dispatch and ZIP password policy live in `services/documents/`; Qt picker/window/privacy code lives in its `ui/`. Folder policy, sources, entries and safety live in `services/folders/`, with Qt index hosting under `ui/`. `documents/preparation.py` opens provider text/Markdown without Qt; rclone owns its bounded Markdown resource loader independently of presentation. Folder safety config remains rooted at `Python/maintenance.ini`.

### 10. Owner-declared mobile sources

Each supported feature, the mobile host and neutral services declare selected modules in `mobile_sources.json`. `mobile_build/tools.py` aggregates these strict data-only allowlists, validates staged feature/service imports (including nested adapters), and copies manifests into the payload source hash. Stage reads the target checkout manifests; no feature discovery or desktop registration runs during packaging. Existing public APP_MODULES/DOCUMENT_MODULES inventories remain available to validation tools.

### Integration audit follow-up

Desktop/mobile LM transports share portable SSE event decoding while retaining platform networking and mobile bounds. Global Cancel invokes an active transfer-review close callback as well as cancelling its scan. Focused decoder parity, controller cancellation, chat and transfer checks cover these final integration gaps.

The broad audit also migrated native/host transfer assertions to their explicit cancellation owner and corrected the desktop launcher's index-service import. New transfer controllers initialize cancellation/review state before any workflow begins.

## Verification of the completed pass

- Audited 146 desktop/portable test files with module isolation. The first run passed 144; the missing launcher service import was corrected and all seven launcher tests passed. The portability subprocess required the mobile Markdown dependency; its rerun passed using a temporary runtime combining the existing desktop/mobile environments, without changing either project environment.
- The complete mobile host rerun passed all 378 tests. Focused LM checks passed across seven isolated files, including shared decoding, response limits, streaming, cancellation and desktop UI behavior.
- Payload manifest validation, staged startup, headless feature/document imports, relative Markdown resource containment, documentation hierarchy and correctness lint passed.
- Canonical native transfer scenarios now inspect the transfer controller's cancellation token. Native builds and simulator/emulator checks were subsequently completed as recorded below; physical-device interactions remain outside that verification.

All ten ownership items have individual commits, followed by an integration-audit correction. Unrelated edits arriving concurrently in documentation, licensing and commonUtils were excluded from the final refactor commits.

## Native verification follow-up — October 17, 2026

Native build and acceptance checks exposed a controller boundary error: the cloud
controller passed itself to credential-vault creation. Both ordinary credentials
and retained ZIP storage now receive the application host, including Android's
native activity and storage policy. A host regression covers both paths.

The native audit also corrected editor shutdown on iOS: stop WebKit loading and
detach delegates before clearing a closed live preview. Native close/discard
checks force garbage collection before allowing pending callbacks to run. The
host ignores delayed Toga scroll callbacks whose Python interface has retired.
The custom source input disables scroll-edge overlays that otherwise bypassed
the ordinary input appearance hook. Native probes select the Local source before
browsing local folders and find newer UIKit floating tab labels outside the
`UITabBar` placeholder, excluding page content from navigation assertions.

- iOS: normal simulator build and arm64 device-target build passed with Xcode
  27.1. Embedded Python frameworks used local ad-hoc signing; no distribution
  signing or physical-device deployment was performed.
- Android: normal debug APK build passed, including arm64/x86_64 Go bridges and
  the build helper's 16 KiB ELF alignment checks. Both bridge builds also passed
  their Go tests.
- All 31 workflow cases plus presentation/browser Back checks passed on iPhone
  Duo (iOS 27.1), iPad Pro 13-inch M5 (iOS 27.0), and an Android API 35 arm64
  emulator. The iPad report verifies independent system windows.
- All 380 mobile host tests passed: 377 in the full sandboxed run and the three
  loopback-server tests on a rerun with local socket access. Focused ownership,
  editor, credential and report checks, correctness lint and diff checks passed.
- Normal iOS and Android launchers were restored and rebuilt after test mode.

Exact-source local reports: iPhone (local artifact `test-results/mobile-evidence/2026-10-17-refactor-iphone-native-ui-local.json`),
iPad (local artifact `test-results/mobile-evidence/2026-10-17-refactor-ipad-native-ui-local.json`), and
Android (local artifact `test-results/mobile-evidence/2026-10-17-refactor-android-native-ui-local.json`).
All three identify snapshot
`cb846c0089e5a930c39a4f2223e763b731e9555bda464691562e0b673e6f4277`,
staged from refactor commit `05fb5861` with these fixes. Reports retain
`dirty: true`, including the concurrently edited commonUtils source snapshot;
they are local acceptance evidence, not clean release certification. Validation
used an isolated Briefcase project so concurrent application/documentation edits
and existing generated builds were preserved. The separate CPython 3.14 testbed
workflow was not run by this native Toga app acceptance pass.

## October 21 developer maintainability pass

This pass began from a clean working tree and was implemented in separate local
commits, each with relevant checks before the next change. It preserves feature
IDs, persisted data, public compatibility imports, the reserved Misc destination,
the external feature boundary and the commonUtils submodule revision.

| Area | Implemented boundary | Verification |
| --- | --- | --- |
| Source/private files | Generated native output, caches, signing material and conventional secret filenames excluded from Git/release packages; indexed hygiene reports paths/categories only | Release packaging regressions, ignore probes and hygiene checks |
| CI | Mobile-only PR coverage, feature/service dependency build triggers and lightweight documentation checks | Trigger-path probes and documentation contracts |
| Developer setup | Read-only doctor, separate desktop/mobile setup, hashed mobile host lock and dependency drift checks | Developer command tests, lock resolution and environment diagnostics |
| Ownership | 32 source owner/test/guide maps and 15 compatibility import records | Ownership and canonical-target checks |
| Architecture | Reviewed host adapter/feature edges, relative imports, literal lazy references and selected portable-module rules | Architecture regressions and runtime portability checks |
| Test discovery | Nested files retain process isolation and duplicate-name safety; empty discovery fails | Runner regressions and existing command checks |
| Desktop LM | Project attachments composed through an explicit host interface | Complete LM UI regressions |
| Mobile cloud | Separate SMB form, offline-copy and credential workflows with owned state and compatible callbacks | Connection, package, restore, import, background-refresh and ownership regressions |
| Mobile host | Shutdown/resource lifetime, provider chrome assembly and toolkit-independent workspace selection have separate owners | Startup, reset, private-session, speech, reader and navigation regressions |
| Desktop host | Folder request state and workers separate from Qt rendering | Cancellation/private-path tests and Folder Hub UI regressions |
| Registry | Pure dependency availability/ordering separate from preferences and activation | Registry/preferences regressions |
| Native bridge | Shared action/envelope contract fixture, malformed-response disposal and safe Go examples | Python contract/credential tests and complete Go bridge suite |
| Onboarding | A worked contribution and direct commands in current developer navigation | Documentation link/hierarchy checks |

These are incremental boundaries, not a claim that every large coordinator was
fully redesigned. The registry still owns activation/preferences/contributions;
provider session and cloud browsing coordination remain host-owned. Broad native
widget factories remain opaque, and static import analysis cannot resolve computed
imports. Moving remaining state or adapters should follow a concrete workflow and
its behavior tests. Package names and existing flat test paths remain stable;
nested discovery makes later test moves possible without requiring them now.

The local checkout's largest directories were generated mobile builds, logs,
deployment workspaces and virtual environments. They remain local and were not
deleted during this pass. No physical-device install or Boox test-app cleanup was
needed because this pass did not install test apps. Native interaction acceptance
remains separate from host regression results.

### Host verification for the October 21 pass

- Complete desktop application regressions: 168 isolated files, 1,560 tests,
  no failing files, using the existing desktop environment with fixture sockets
  and OS watcher access.
- Complete mobile host regressions: 148 isolated files, 1,069 tests, no failing
  files, using a fresh temporary Python 3.12.2 environment installed from the
  hash-locked mobile host requirements. This exposed and corrected custom
  interpreter symlink resolution before the passing run.
- Complete Go bridge suite: `go test ./...` passed, including shared protocol
  fixtures and operation-scope regressions.
- Release/tooling suite: 20 tests passed with the native-Windows-only test skipped
  on macOS. Workflow YAML parsed, documentation contracts also passed with Python
  site packages disabled, and correctness lint/import/toolchain/hygiene checks
  passed.
- Final optional-argument annotations were followed by passing chat and
  documentation checks. No native application build, simulator interaction or
  physical-device acceptance is claimed by these host results.

All changes were committed locally in reviewable steps. No push or deployment was
performed. Existing environments, generated build directories and the separate
commonUtils checkout were preserved; the temporary lock-verification environment
was disposable.


## Review of the 28 most recent changes — October 21, 2026

The review covers the 28 commits ending with the reader sleep fix, in chronological
order. Three were already published; 25 were local. Each change was checked against
its diff, current owner and relevant regressions. The rows identify subjects rather
than hashes because the requested eight-hour timestamp correction changes local
commit IDs. Published commits and the commonUtils revision are preserved.

| # | Change | Review result |
| --- | --- | --- |
| 1 | Mobile reader controls, navigation and document decisions | Fixed cancellation leaving a document's close guard set. Regressions cover retry safety; menu, Back, progress and startup checks retained. |
| 2 | Automatic Android folder-action widths | Numeric-width fallback remains valid for fresh drawers and added/removed actions. |
| 3 | Await native modal decisions and reader readiness | Checks await their decision tasks and retained-reader operations; these scenarios deliberately mock dialog decisions rather than claim native button interaction. |
| 4 | Generated/private-file exclusions | Reviewed Git and source-release filters; signing material, runtime output and environments remain excluded. |
| 5 | Mobile and documentation CI coverage | Reviewed dependency/source triggers and workflow scope; documentation remains independently checkable. |
| 6 | Contributor setup and environment diagnostics | Fixed doctor aborting on an unlaunchable or timed-out interpreter; it now reports both environments and continues diagnostics. |
| 7 | Nested isolated test discovery | Fixed unittest recursively rediscovering same-named child-package tests within a supposedly isolated process. Child runs now load exactly one file while retaining package-relative fixture imports. |
| 8 | Import architecture checks | Reviewed relative and lazy literal references, portable rules and external-link exclusion; boundary regressions pass. |
| 9 | Source-owner/test map | Added missing comic rendering, reader recovery, privacy and document-dialog groups to focused owner selection. |
| 10 | Desktop LM attachment controller | Fixed the 64 KiB check omitting inserted separators; UTF-8 boundary tests verify rejection leaves the draft untouched. |
| 11 | Toolchain drift check | Compared native/host manifests, lock inputs and shared desktop/CI versions; no drift. |
| 12 | Owned SMB form/workflow | Reviewed lazy controls, compatibility descriptors, secret consumption and busy-state cleanup; connection regressions retained. |
| 13 | Application shutdown/resource ownership | Extraction matches original method ASTs; active-host, veto, speech and disposal ordering preserved. |
| 14 | Provider reader chrome assembly | Extraction differs only by the required local private-label import; reader/PDF/editor contracts retained. |
| 15 | Workspace selection policy | Reviewed pinned-document swapping, unavailable-session retirement and toolkit-free candidate selection. |
| 16 | Feature dependency graph | Reviewed ordering, missing/circular dependencies, duplicate identities and registry delegation. |
| 17 | Desktop Folder Hub controller | Reviewed generation snapshots, cancellation checks and private-folder contribution filtering. |
| 18 | Shared Python/Go bridge contract | Python envelope validation still frees native responses on errors; action fixtures and the full Go suite pass. |
| 19 | Presentation/connection service ports | Compared callback argument shapes with injected implementations and feature consumers; optional arguments preserved. |
| 20 | Compatibility inventory | Canonical module targets remain present, including shared-library forwarding; no automatic compatibility removal. |
| 21 | Indexed source hygiene | Reports only paths/categories and scans indexed blobs; ignored outputs and recognizable secret patterns are checked. |
| 22 | Offline-copy download workflow | Structural comparison found no behavior change in the four extracted workflow methods; import/export regressions retained. |
| 23 | Credential selection/unlock/restore workflow | Structural comparison found no behavior change in the 19 extracted workflow methods; bounded ZIP access and ownership remain intact. |
| 24 | Contributor documentation/migration boundaries | Reviewed current commands, worked contribution, documentation ownership and explicitly deferred migrations. |
| 25 | Custom interpreter identity | Symlink spelling is preserved so selected virtual environments retain their installed packages. |
| 26 | Optional presentation arguments/bridge docs | Reviewed annotations against real icon/preview callbacks and envelope decoding. |
| 27 | Host and bridge verification record | Fresh review runs distinguish host tests, tooling and native evidence instead of treating old reports as new certification. |
| 28 | Sleep/wake reader recovery | Visible-owner, route, lock and stale-token guards reviewed. Fixed the previously recorded Android sampler overflow for one-pixel draw targets; native probe now exercises that case explicitly. |

Each behavioral correction first failed a targeted regression, then passed after
the fix. The complete mobile rerun and desktop suite, focused LM/doctor/dialog/
rendering tests, release/runner tests, Go bridge suite, lint, architecture,
dependency and documentation checks verify this follow-up. The emulator's
review acceptance summary (local artifact `test-results/mobile-evidence/2026-10-21-reader-review-android.json`)
records exact tested source hashes and seven sleep/trim/wake cases plus one-pixel
native decoding. No physical Boox or iOS interaction is claimed by this review.

Native output remains in ignored `mobile_build/logs/reader-resume/review`; the disposable
QA package is removed after evidence capture. This follow-up does not change
commonUtils. Commit timestamp rewriting is limited to commits absent from refreshed
remote references; it changes author/committer times and IDs, preserving file trees,
messages, identities, time-zone offsets and parent order. No push is performed.

## October 22 readability and shared-mechanism pass

The application now declares retained mobile controller factories directly, with
expanded controller inventories and typed presentation callback contracts. Existing
app accessors remain for internal callers; composition can navigate directly to the
owner. Startup has eight named phases, with unchanged yields, asynchronous model
preparation and document restoration order. Reader actions, PDF tools and reader/
editor mounting have separate assembly functions; platform appearance installation
has separate iOS/Android owners. Folder row labels/lock state are projected before
native reconciliation. Desktop LM menu assembly has its own module.

The commonUtils extraction adds explicitly admitted indexed local resource search,
disk-spooled command capture, best-effort diagnostic redaction, data-only SSE
framing, callback-backed archive views, optional Pillow encoding/classification,
and exclusive link/copy publication. Logistics keeps provider eligibility,
credentials, session validity, Git options/environment, LM response semantics and
all image/comic retention policy. The copy fallback remains non-atomic; it does
not replace the distinct atomic exclusive-rename contract. Shared API documentation
stays in commonUtils; Logistics' integration guide records only these boundaries.

Comic sanitization now names the existing sequential phases. No eager whole-cleanup
plan changes which earlier deletions/moves remain after a later failure. Quality
60/35, the 2,400-pixel comic height cap, the strict 75-percent retention threshold,
forced retention, animation/multipage exceptions, alpha handling, padding thresholds,
ComicInfo rebuilding and archive publication remain unchanged. The compression
orchestrator, ComicInfo implementation, statistics and archive publication modules
were not rewritten. The code diff and extracted statement bodies were reviewed,
then generated fixtures compared against baseline `f55417a556f8a328ce6a91c029758b4c204e9c22`.

Validation performed on the macOS host:

- Desktop: all 175 isolated files covered, 1,602 tests with six platform skips.
  The full run exposed one retired private speech-field assertion; its corrected
  file reran with all 28 tests passing. No desktop production regression remained.
- Mobile host: all 162 isolated files passed, 1,159 tests with two platform skips.
- commonUtils: a final complete run passed all 173 isolated files, 1,110 tests
  with three platform skips. Existing desktop and mobile dependencies were made
  available to the test process without changing either environment. Follow-ups
  updated stale speech/index test-owner references, isolated default-storage
  fixtures from host overrides and retained optional dependencies in child tests.
- Comics: 80 cleanup/failure cases matched outcomes, remaining paths/bytes,
  operation order and application diagnostics; 24 oriented/color/grayscale/alpha/
  ICC JPEG/WebP cases produced identical encoded bytes; 32 complete plain/AES
  compression runs matched extraction, sanitized, staged and final member manifests.
- Clean committed-source payload staging and packaged startup passed, including
  document restoration, provider Markdown and file operations. Lint, architecture,
  toolchain, documentation layout, indexed-source hygiene and diff checks passed.

The broad mobile run also exposed missing hidden-file metadata in the existing
optimized collection listing. The listing now matches the base provider without
extra filesystem reads; parity/performance coverage includes an actual hidden file.
The README's mobile overview is shorter, and current developer guides include
workflow ownership traces and repeatable comparison commands.

Raw comparison reports and suite logs remain under ignored `test-results/`.
No native build, simulator/device interaction, deployment or push is claimed by
these host results. No test app was installed. Root ignore rules, private resources,
external feature ownership, the reserved Misc destination and the single Ally Tools
acknowledgement were preserved. Changes were committed locally in reviewable steps.
