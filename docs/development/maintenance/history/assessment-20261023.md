# Readability assessment snapshot — October 23, 2026

Historical snapshot: Logistics `4f78de7d`, commonUtils `2cd0516`.
The proposals and counts below precede the sequential implementation; consult
[current status](../remaining-work-audit.md) before treating a finding as open.

## Assessment

The next substantial improvement is clearer state and dependency ownership, not
another round of package renames or extracting every long method. Shared resource
contracts, isolated tests, feature-owned adapters, archive rewriting, document
sessions and cooperative shutdown already provide useful foundations. Recent
construction/Save/opening extractions are complete and are not new backlog items.

The largest remaining maintenance costs are:

1. Application/workspace owners whose readers need to understand many mutable
   fields and callback paths before changing one workflow.
2. Transactional index, tab-transfer and installation paths where preparation,
   publication and rollback remain interleaved.
3. Presentation builders and renderers with several independent responsibilities.
4. Tooling that scans generated files, has incomplete dependency coverage, or
   requires a manually assembled shared-library test matrix.
5. Current owner references buried among long historical maintenance records.

These are maintenance findings and proposed work units, not newly proven defects.
Fresh full host-test runs plus environment-specific rechecks leave no unresolved
failure in the executed groups. Native acceptance remains separate. A numeric
whole-system quality score would overstate what this audit establishes.

## Scope and measurement

Every tracked Python file in both repositories was inventoried and AST-parsed.
The pass measured module/function/class spans, direct state assignments, branching
indicators, imports, exact function-body duplication and test/tooling distribution.
Detailed source inspection concentrated on the ranked owners below, their callers,
existing tests, source manifests and architecture policies. This is repository-wide
structural coverage plus targeted behavioral/source review, not a claim that every
line or possible runtime path was manually verified.

| Repository / category | Python files | Physical lines | Nonblank lines |
| --- | ---: | ---: | ---: |
| commonUtils production | 328 | 42,846 | 37,898 |
| commonUtils tests/support | 201 | 23,981 | 21,978 |
| Logistics production | 661 | 85,290 | 75,528 |
| Logistics tooling | 42 | 4,431 | 4,007 |
| Logistics tests/native validation/support | 471 | 77,546 | 72,059 |

Counts use each repository's Git index, without traversing the commonUtils
submodule twice or the ignored Ally Tools link. Generated payloads, deployment
workspaces, virtual environments, caches and downloaded toolchains are excluded.
Python figures do not measure embedded JavaScript, native Java/Objective-C code,
assets or shell scripts. Those surfaces received integration/manifest and selected
adapter review, not comprehensive native execution. No parse errors were found.

There are 23 shared and 57 Logistics/tooling functions spanning at least 80 lines;
eight and 20 respectively span at least 100. These are inspection candidates,
not limits to enforce. The branch count is a syntactic indicator, not cyclomatic
complexity or a correctness measure. Exact normalized AST bodies of at least
12 source lines yielded no duplicate groups; this does not rule out conceptual
or near duplication.

## Ranked shared-library work

P1 means the next substantial engineering work; P2 means useful follow-up once
its tests and owning boundary are clear. Neither label asserts a user-facing bug.
Source links resolve through Logistics' existing submodule checkout.

| ID / priority | Evidence and remaining cost | Bounded improvement | Required preservation evidence |
| --- | --- | --- | --- |
| C1 / P1 | [Index reconciliation](../../../../Python/commonUtils/filesystem/index/reconcile.py) combines ancestor/generation selection, changed-target classification, partial/full repair queues and transaction publication in the 136-line `reconcile_existing`. It mutates private [cache state](../../../../Python/commonUtils/filesystem/index/store.py) across those phases. | Name target selection and repair phases inside the existing index owner; make the active operation's inputs/state explicit. Keep one transaction owner and existing writer lock. | Existing index tests, especially partial retries, cancellation rollback, excluded paths, reader snapshots, folder totals and watcher-driven repairs; unchanged database/schema/checkpoint semantics. |
| C2 / P1 | [FileBrowser](../../../../Python/commonUtils/ui/file_browser/__init__.py) still spans 677 lines/48 direct methods despite existing assembly/views/indexing helpers. Network policy, watch sets, queued reconciliation, details and shutdown share fields across owners. | Clarify the indexing/watch-policy state transitions and the preview retirement contract. Prefer completing those existing owners over adding another general browser manager. | Network-to-local restoration, queued notifications after navigation, failed-folder watch removal, close while busy, thumbnails and details against real host notifications. Preserve the established stop/busy return contract. |
| C3 / P1 | [Workspace adoption](../../../../Python/commonUtils/ui/workspaces/workspace.py) has an 85-line transactional `adopt`; [header refresh](../../../../Python/commonUtils/ui/workspaces/presentation.py) has 87 lines of visibility, geometry and active-tab reconciliation. | Make capture/transfer/rollback explicit; independently simplify header decisions. A small transfer snapshot is justified only if it removes repeated capture/restore bookkeeping. | Cross-window/detached transfers, failure rollback, vetoes, active tab, tab order, geometry, owner signals and deferred close. Keep the existing workspace/presentation owners. |
| C4 / P2 | [Markdown presentation](../../../../Python/commonUtils/ui/markdown/presentation.py) has a 123-line `style_document`; [document conversion](../../../../Python/commonUtils/ui/markdown/document.py) also mixes block traversal and format interpretation. | Separate block classification from applying callout/code/image/heading formats, one domain at a time. Do not conflate native formatting with authored-source editing. | Exact source, undo history, rich/source round trips, callout boundaries, Unicode positions, links/images and theme/font changes. Constructor extraction is already complete. |
| C5 / P2 | [Layered settings](../../../../Python/commonUtils/ui/settings/layered_settings.py) has a 114-line `_build` that selects schema controls, applies style validation, wires edits/resets and creates previews. | Use clear per-field construction/binding phases, preserving the existing schema and editor. Avoid a new generic form framework. | Inheritance, sparse overrides, reset, invalid/unknown values, concurrent file edits, font preview and no-op saves in the existing configuration tests. |
| C6 / P2 | [INI patching](../../../../Python/commonUtils/formats/iniType.py) interleaves parsing, text-location discovery, continuation/comment preservation and validation in `updated_text`; [rename transformation](../../../../Python/commonUtils/filesystem/rename/__init__.py) has a dense rule chain. | Give the parsing/planning stages explicit names and narrow internal value types where useful. Keep transform order and publication separate. | Existing INI/bulk-rename tests plus ambiguous formatting, comments, line endings, collisions, exclusions and cancellation. Do not replace the preservation algorithms merely to shorten them. |
| C7 / P2, platform-gated | [Native navigation](../../../../Python/commonUtils/ui/native/navigation.py) is 616 lines and [image canvas](../../../../Python/commonUtils/ui/native/image_canvas.py) 456; their Apple factories embed classes, native allocation, callbacks and restoration. [Native speech](../../../../Python/commonUtils/ui/native/speech.py) has comparable backend setup responsibilities. | First document/test paired install/dispose and callback ownership, then separate backend construction from runtime events if useful. Add platform acceptance before moving native classes. | Device rotation, IME/chrome restoration, pinch/pan/magnifier gestures, voice interruption, repeated install/dispose and late callbacks. Toga dummy and fake Java/UIKit tests do not establish these behaviors. |
| C8 / P2, compatibility-sensitive | [Perforce file workflows](../../../../Python/commonUtils/integrations/wrappers/perforce/p4_file.py) retain mutable status fields, prompts and command decisions; legacy filesystem/command facades retain wildcard imports and compatibility exports. | Improve decision readability and explicit imports in small verified units. Consider injectable presentation only where an actual headless use requires it. | Existing Perforce/command/link tests and consumer namespace/signature checks. Preserve Perforce consumer/build architecture, public field names, callback order and interactive/silent semantics. Do not remove facade exports based on unused-import reports. |

## Ranked Logistics work

| ID / priority | Evidence and remaining cost | Bounded improvement | Required preservation evidence |
| --- | --- | --- | --- |
| L1 / P1 | [Mobile app](../../../../Python/mobile/app.py) is 1,268 lines/95 direct methods. It is both a composition root and the owner of managed-document creation, selection, checkpoint/recovery, import/export, preview and settings reactions. | Complete the managed-document workflow boundary using existing document/workspace owners. Keep startup, owner factories and scene publication in the app. Remove forwarding only after reviewing all composed descriptors and native callbacks. | Recovery conflicts, repeated checkpoints, multiple windows, restore, unsaved drafts, import/export scope balance, backgrounding and close vetoes. Keep persisted workspace/document formats unchanged. |
| L2 / P1 | [Workspace navigation](../../../../Python/mobile/workspace_navigation.py) is 905 lines, containing native toolbar/menu helpers, `WorkspaceNavigation`, `WorkspaceFrame` and `FileDrawer`. Drawer listing and pane transitions are different lifetimes in one module. | Clarify the frame/drawer contract first. A separate cohesive drawer implementation may help once the interface is explicit; do not scatter individual navigation methods into tiny files. | Pane ownership, selected route, drawer history, paired readers, rotation/hinges, background listing, credentials and stale-row rejection. Any file move must update the curated mobile manifest. |
| L3 / P1 | [Provider UI](../../../../Python/mobile/provider_ui.py), [provider view](../../../../Python/mobile/provider_view.py) and [library reading](../../../../Python/mobile/reader_ui.py) still communicate through dynamic fields. Provider views use a `SimpleNamespace`, bulk publication and descriptor exceptions; `display_book_page` is 106 lines of format and publication decisions. | Define the unpublished-view/adoption contract and test failure ownership of partially constructed controls. Then separate remaining format-specific publication stages using the existing Books/Comics/Markdown controllers. | Prepared/acquired source ownership, partial build failures, old-reader retirement, metadata drafts, cancellation, stale epochs, private state and scene selection. A possible disposal gap is a review target, not a confirmed leak. Recent opening/session extractions are complete. |
| L4 / P1 | [Files UI](../../../../Python/mobile/files_ui.py) has a 124-line `show_files`; [folder hub](../../../../Python/mobile/folder_hub.py) has a 100-line source-discovery decision tree; [hub presentation](../../../../Python/mobile/folder_hub_ui.py) spans 657 lines. | Make source/root descriptors and presentation construction easier to trace while retaining `FolderListing` and `FileOperations` as the operation owners. | Local/LocalCrypt/remote roots, remembered credentials, unavailable mounts, folder pins, search, navigation during loading and large-folder rendering. No relocation into commonUtils of application credential policy. |
| L5 / P1 | [Mobile chat](../../../../Python/features/lm/mobile/ui.py) spans 724 lines; `show_chat` is 146 lines and the owner assigns 61 distinct direct fields. [Desktop LM](../../../../Python/features/lm/ui/page.py) spans 755 lines. | Separate initial control assembly, conversation-list projection and transcript publication inside existing session/controllers. Narrow captured generation/current-conversation inputs instead of adding a second chat state owner. | Drafts typed during generation, cancel/partial output, leases, context selection, transcript load/scroll, export and session-only keys. Desktop tool-enabled and mobile text-only policies should remain distinct. |
| L6 / P1 | [Desktop folders](../../../../Python/desktop/pages/folders.py) spans 738 lines; [IDE workspace](../../../../Python/features/ide/ui/workspace.py) 660; [Git repository view](../../../../Python/features/git/ui/repository_view.py) 646. Discovery, credentials, pane/view lifetime and queued results are substantial owners. | Work on one owner at a time: folder discovery-to-browser mounting; IDE captured open/recovery jobs; Git snapshot-to-control projection. Preserve their current feature/service boundaries. | Closing/replacing while busy, stale callbacks, source unlock, retargeted buffers, recovery and automatic Git refresh. Keep generic services free of feature-specific UI policy. |
| L7 / P1 | [Cloud UI](../../../../Python/features/rclone/mobile/cloud_ui.py) spans 709 lines/53 direct methods; [push validation](../../../../Python/features/rclone/transfers/push_policy.py) and [collection switching](../../../../Python/features/rclone/mobile/storage_location.py) retain dense policy/verification flows. | Clarify presentation, captured account state, operation preparation and final publication within existing Cloud/Transfer/Storage owners. Keep independent cancellation and privacy lifetimes distinct. | Reviewed transfer approval, changed credentials, remote/local separation, interrupted copy verification, lost permission/card, active-location erase refusal and original-file preservation. The collection prompt/progress extraction is complete. |
| L8 / P2 | [Text-editor command construction](../../../../Python/features/text_editor/ui/editing.py) is 150 lines; [settings refresh](../../../../Python/desktop/pages/settings.py) 93; [Bulk Rename widget](../../../../Python/desktop/bulk_rename/widget.py) 672 lines. | Use named command/control groups and separate view projection from decisions. Start with construction, without rewriting the editor/rule engine. | Shortcuts, wheel/selection behavior, settings scope/inheritance, saved-byte baselines and rename previews. Keep `DestinationRail.tools_menu` and its reserved Misc glyph. Save/Save As cleanup is already complete. |
| L9 / P2 | Logistics' [Blender add-on library](../../../../Python/features/blender/addons/library.py) has a 138-line `_apply` combining selection resolution, fallback, staged payload verification, backup, installation and rollback; its [page](../../../../Python/features/blender/ui/page.py) has dense choice rendering. | Make resolution/staging and transactional apply boundaries explicit, retaining one lock/rollback owner. This is Logistics integration code, not permission to refactor the Blue Hole repository. | Managed-path containment, unchanged packages, edited archives, fallback, cancellation, preferences/environment rollback and existing Blender-library fixtures. Real Blender validation remains an additional gate. |
| L10 / P2, incremental | Secondary features have substantially smaller owned modules and dedicated fixture tests. Git's 716-line [repository backend](../../../../Python/features/git/repository.py) and rclone's [LocalCrypt backend](../../../../Python/features/rclone/localcrypt/backend.py) are large but cohesive domain owners. | Prefer focused naming/error/result-type cleanup when changing a real workflow. Check unused locals/imports and stale scaffolding owner by owner. Do not split a cohesive backend or rename legacy paths just to reduce file size. | Existing Git, LocalCrypt, aviation, Flight Sim, Calibre, FUSE, Minecraft, Plex, smart-home and downloader contracts; live external services/hardware are separate acceptance. |

## Cross-cutting work

| ID / priority | Finding | Action and completion condition |
| --- | --- | --- |
| T1 / P1 | The configured lint invocation includes 4,028 files; 2,325 are outside the tracked Python inventory. Examples include ignored `.deploy-workspaces` copies and downloaded `.tools/go` sources, plus the project TOML. Thus its scope depends on local build residue. | Explicitly exclude generated/deployment/toolchain trees while still checking new application source. Add a scope regression with a disposable generated tree. Check tracked commonUtils separately and preserve optional-link exclusion. |
| T2 / P1 | `dev.py test` exposes desktop/mobile but no shared-library matrix. Desktop lacks Toga; the mobile environment lacks Qt. Localhost, filesystem watchers and WebEngine also need capabilities unavailable in a restricted sandbox. | Add one documented shared/matrix entry point with explicit environment/capability requirements and per-file results. Extend existing owner test selections where sparse (for example the archives owner currently selects only feature-registry tests). Do not turn blocked tests into passing skips. |
| T3 / P1 | [Architecture checks](../../../../Scripts/architecture.py) correctly guard approved feature-to-host/cross-feature edges, but portable checks cover an enumerated list of eight modules. They do not prove every shared core module or dynamically composed callback is presentation-independent. | Expand portable-module/import-safety coverage by owner and test the policy itself. Add narrow stdlib `Protocol`/typed records where dynamic service contracts currently obscure required fields; use the [existing resource contracts](../../../../Python/commonUtils/runtime/resources/provider.py) as precedent. Do not introduce a blanket type-checking migration or dependency framework. |
| T4 / P2 | Configured Ruff rules are correctness-only (`E9`, `F63`, `F7`, `F82`). A tracked-only exploratory `F401/F811/F841` pass reports 343/2/29 diagnostics; re-exports and intentional bindings explain some. Duplicate `SettingsLabel` imports in the mobile settings categories/navigation are concrete examples. | Review by owner, distinguish exports/side effects from dead imports, then enable a narrow additional rule for cleaned scopes. No repository-wide `--fix` sweep or facade deletion. These optional diagnostics are not configured-gate failures. |
| T5 / P1 | The old audit, progress, readability and mobile-runtime pages have 585, 1,923, 418 and 1,267 lines at this snapshot. Historical findings sometimes describe already completed migrations. | Keep this page as the current backlog; make owner guides the current contracts. Consolidate duplicated chronology and split only genuinely independent systemic guides, preserving wiki landing links and historical evidence. Update owner/test/manifest references as part of each work unit. |

## Subsystem disposition

This table records areas that were included without manufacturing a refactor for
every directory. Ranked items above identify work, not an instruction to rewrite
all code in that owner.

| Area | Current disposition |
| --- | --- |
| Shared filesystem/index/storage | Index transaction/state clarity is high value; native links and Windows-specific behavior need platform contracts before API cleanup. Existing root fingerprints include device/inode data: do not repeat the old claim that no identity exists. Disconnected-volume retention remains a separate policy question, not an authorized behavior change. |
| Shared formats, configuration and persistence | Preserve byte/text/INI and optimistic-conflict contracts. INI/schema presentation is the readability target; existing atomic publication should remain the mechanism. |
| Shared archives and resource/search operations | Existing provider protocols, capability checks, archive rewrite and bounded streams already have useful ownership. Keep format/application policy with consumers. Long validation functions alone do not justify a new generic pipeline. |
| Shared processes, diagnostics and integrations | ProcessSupervisor and explicit diagnostic presenters are completed ownership improvements. Perforce/legacy API readability is compatibility-sensitive; preserve the established architecture. |
| Shared Qt/browser/editor/Markdown/workspaces | Prioritize C2–C5. Constructors recently extracted should not be counted again as unfinished work. Core code-editor mechanics remain cohesive; folding/diff parsing needs grammar/round-trip evidence before restructuring. |
| Shared native/browser/speech | Recycled/paginated renderers already share worker lifetime. Native backend install/dispose contracts and real-device evidence precede further platform restructuring. |
| Logistics desktop shell/services/registry | Feature activation, contribution catalog and preference owners already exist. Preserve their lazy initialization and registration order. Refine host contracts and the large folder/IDE/Git owners; no wholesale shell rewrite. |
| Logistics reading/editing/collections | Feature-owned Books/Comics/PDF/Text Editor adapters and common archive machinery are established. Remaining work is captured view state, publication and presentation readability, not moving every reader into commonUtils. |
| Logistics cloud/transfers/credentials | Keep reviewed mutation policy, credential ownership, private bytes and per-operation cancellation explicit. Existing storage/transfer services remain the mutation owners. |
| Logistics secondary integrations | Existing tests cover aviation, Flight Sim, Calibre, FUSE, Minecraft, Plex, smart-home and YouTube workflows. Inspect local abstractions when changing behavior; no broad unification or speculative package renames. |
| Build/deployment/native validation | Recent build/deployment package organization is complete. Remaining systemic needs are deterministic tooling scope, test-matrix selection and native acceptance, not another move of build helpers. |
| Documentation/packaging | Root wiki ownership and curated mobile manifests are established. Current-versus-historical navigation, owner test selection and per-change manifest checks need upkeep. Root README Ally Tools acknowledgement remains exactly within the repository rule. |

## Dependency and duplication interpretation

A graph including deferred imports produces six shared and 27 Logistics strongly
connected groups; the large groups largely reflect lazy activation and facade
relationships. Restricting the graph to syntactically eager imports yields two
shared groups (command facade and Qt facade) and none in Logistics. These are
static candidates, not demonstrated import-time errors: conditional execution,
package initialization and dynamic imports prevent either graph from proving
runtime acyclicity. Keep lazy namespace/import tests; inspect actual edges before
moving modules. Do not “fix” every conservative cycle with forwarding shims.

Dynamic descriptors remain a readability cost even though they improve state
ownership: `HostAttribute`, `OwnedAttribute`, `StateAttribute`, composed workflow
method/field lists and provider Markdown descriptors require readers to trace
several files. Prefer named capability contracts and ownership tests at hot
boundaries. Do not replace them with another universal dynamic manager.

The audit found no basis for a new catch-all utilities layer. Conceptual overlap
between desktop/mobile readers or local/remote providers is not sufficient reason
to merge their cancellation, storage or privacy policies. Broad exception handling
and intentional silent fallbacks also need contract-specific review; their counts
alone are not defects.

## Recommended sequence

1. **Make checks deterministic:** T1/T2 and current backlog navigation (T5).
   A clean checkout and a build-heavy checkout should select the same source gates.
2. **Harden change boundaries before larger extraction:** C1/C3, with focused
   transaction/rollback evidence and explicit captured inputs. No schema changes.
3. **Complete mobile owner contracts:** L1/L2/L3, one retained owner at a time.
   Establish partial-construction failure tests before reorganizing publication.
4. **Simplify visible workflow assembly:** L4/L5/L6, then C4/C5/L8. Prefer cohesive
   same-module phases before introducing files or state objects.
5. **Review mutation-heavy feature flows:** L7/L9 with existing storage/add-on
   transaction fixtures. Preserve approvals, source snapshots and recovery.
6. **Address native and legacy surfaces deliberately:** C6–C8 and owner-scoped
   T3/T4 follow-up, gated by the relevant platforms and consumer contracts.

Each implementation commit should identify one measurable comprehension benefit,
retain public signatures and captured lifecycle inputs, run its owning regression
set, and update only necessary consumers/manifests/docs. Function length is an
inspection tool, not the success criterion. Do not add tests that merely mirror
private helper structure; protect observable state transitions and preservation.

## Fresh verification and limits

Python 3.12.2 is installed in both environments; desktop uses PySide6 6.12.0 and
Ruff 0.14.0, mobile uses Toga dummy 0.5.7. Doctor reports no missing required host
dependencies. Test profiles, providers, repositories and output are disposable.

| Run | Result and interpretation |
| --- | --- |
| Logistics desktop | All 179 test files were attempted. The initial restricted run failed six files. Each passes on an appropriately permitted isolated recheck. Reconciled outer unittest count: 1,694 cases, six native-bridge skips, no unresolved failures. This is a per-file reconciled result, not a single unrestricted all-suite pass. |
| Logistics mobile | All 165 files / 1,185 cases were attempted. Two localhost-dependent files initially failed; all 15 chat and one workflow cases pass on permitted recheck. Two Node/Playwright DOM cases remain skipped. No unresolved failure in the executed groups. |
| Shared Qt/portable matrix | All 184 files / 1,260 cases were attempted in the desktop environment, with 25 skips. Four browser/index files initially failed; their 26/30/12/11 cases pass on permitted recheck. Skips include optional Toga and native Windows/case-sensitive-filesystem requirements. |
| Shared native matrix | 25 files / 108 cases pass in the Toga environment, zero skips/failures. Some overlap with the shared run exists; these counts must not be added as distinct test coverage. |
| Configured gates | Doctor, lint and architecture pass; architecture observes 24 reviewed host adapters and 15 feature edges with zero violations. Toolchain/hygiene and documentation checks are recorded with the final audit commit. Passing lint does not resolve T1/T4. |

An initial mixed shared-suite invocation used the Toga environment, which lacks
Qt, and failed 85 files. That invocation was unsuitable for the mixed suite and
was replaced by the explicit Qt/portable and native runs above; those import
failures are not treated as 85 source regressions. Initial permission failures
in the correct suites involved localhost binds, native watcher behavior and
WebEngine Mach-port registration; all affected files were rechecked successfully.
The desktop count uses each file's outer result, avoiding double-counting the
58-case portable harness printed inside an initial failed assertion.

No native iOS/Android/Boox/Windows/Linux, live Blender, Perforce server, remote
account, real collection mutation, deployment or release was performed. The two
optional DOM cases need Node/Playwright to execute; native-bridge and platform
skips require their actual runtimes. The audit does not claim line coverage,
performance certification, security certification or proof of every close path.
Raw inventories, graphs, optional diagnostics and logs remain under ignored test
results; public documentation does not link to those local-only artifacts.

## Ally Tools and Blue Hole boundary

Both external repositories are compatibility consumers, not additional cleanup
projects. This audit makes no change to them or to commonUtils production code.
Their latest prior compatibility pass is recorded in the progress log; it is not
a newly executed external-consumer test run for this documentation-only audit.

Future adjustments there are limited to what an actual shared change requires:
renamed/moved imports, changed call signatures, binding/namespace updates or
necessary packaging/resource references. Search both consumers before changing a
shared interface, then change and test only the affected integration. Do not
modernize their internals, alter workflows, update vendored code just to chase the
latest shared revision, or make unrelated readability changes. Work remains on the
current development branches; local commits are authorized and pushes are not.
