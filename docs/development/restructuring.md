# Architecture restructuring assessment

[Developer index](development.md) · [Current code map](code-map.md)

Assessment: October 16, 2026. This proposal records the initial local source tree;
the implementation status below distinguishes completed local work from plans.
The goal is to make ownership predictable for a new programmer while retaining
the existing feature and platform boundaries.

## Local implementation status

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

Shell and infrastructure naming has been reassessed: keep `ui_new` and the
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
    README.md           # implementation and test pointers
    user_docs/
        README.md       # canonical user guide
        index.md        # in-app compatibility link
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
| `Python/logisticsmobile/files_ui.py` (~908 lines, active local edits) | Contains file mutations, editor Open/Save As selection and comic batch entry points | Extract editor picker state and callbacks as one owned workflow; keep privacy checks, provider identity and cancellation explicit |
| `Python/logisticsmobile/app.py` (~938 lines) | Composes many UI mixins and owns startup plus document operations | Keep startup as the composition root; introduce owned controllers incrementally, following the explicit services already used by `reader_host.py` |
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
3. Extract the mobile editor picker after the active Folder Hub work settles.
   Update `Mobile/tools.py` in the same change; exercise host tests, packaging
   checks and native Open/Save As behavior across Local/LocalCrypt providers.
4. Reduce mobile host inheritance one workflow at a time. Preserve multi-window
   writer ownership, cancellation, navigation generations and private content
   cleanup. A file move alone does not establish those contracts.
5. Reassess shell and infrastructure names after those boundaries are clearer.
   `ui_new` is misleading but a global rename has less immediate value than
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

rclone mobile adapters no longer import `logisticsmobile`. Provider readers, document limits and native archive facades have neutral service owners. `MobileHostUI` declares presentation hooks; `logisticsmobile/feature_hosts.py` supplies them. The app composes provider presentation rather than inheriting it through the rclone feature.

### 3. Mobile workflow composition

The app now composes Chat, Cloud, Transfers, Folder Hub, Home/Documents, Locations and Storage controllers. Each controller enumerates its host dependencies and owned fields; compatibility accessors delegate to that owner without broad attribute forwarding. Transfer/review cancellation is separate from file/cloud cancellation and global Cancel dispatches to both. Reader/session managers and host/provider document lifecycle retain their existing composition.
