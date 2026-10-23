# Ecosystem architecture audit

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
strings. Its current snapshot records:

| Repository | Modules | Internal edges | Potential cyclic groups | Largest group |
| --- | ---: | ---: | ---: | ---: |
| Logistics Python tree | 659 | 1,612 | 27 | 40 |
| commonUtils | 325 | 931 | 7 | 91 |
| Blue Hole | 196 | 597 | 1 | 80 |

These are **potential cycles including deferred imports**, not demonstrated
startup failures. The large shared group includes filesystem/formats plus lazily
opened presentation; Logistics groups include desktop browser/document routing
and mobile presentation; Blue Hole's group spans registration, actions, containers
and preferences. The configured boundary check and consumer import tests pass.
Changing these groups safely requires distinguishing eager initialization from
intentional deferred cross-references; broad graph-driven moves are deferred.

## Before/after assessment of this pass

| Dimension | Baseline evidence | Implemented improvement / remaining limit |
| --- | --- | --- |
| Readability | Shortcut save reimplemented staging; installation error paths obscured recovery state | Shortcut publication delegates to its shared owner; promotion and IDE admission have explicit phases. Large UI construction/filter functions remain. |
| Modularity | Existing feature owners and grouped shared packages already in place | Kept all production modules and entry points recognizable; no package moves or new abstraction layers. This pass does not claim a whole-repository modularity transformation. |
| Testability | Extensive tests existed, but some used default shared storage and optional Toga failed discovery | Regression runner isolates default storage/preferences before discovery; new failure regressions and optional-backend execution cover the changed contracts. Device validation remains separate. |
| Coupling | 25 approved host adapters, 15 cross-feature edges and deferred cyclic groups | No added feature-to-feature edges. Blue Hole and archive extraction consume the existing publication primitive. Large deferred graph groups remain. |
| Duplication | Shortcut writer repeated shared staging/fsync/replace logic | Removed that duplicate and reused shared verified promotion in Blue Hole. No exact repeated production function bodies of 20+ lines found; near-duplicates are not exhaustively eliminated. |
| Consistency | Similar mutation paths had different collision and cleanup behavior | Shared promotion and complete archive extraction use no-replace publication. Invalid IDE state is admitted atomically; shortcut failures restore live state. Atomic publication still is not multi-file locking. |
| Reliability | New tests reproduced overwritten racing files, partial extraction visibility, changed shortcuts after failed save, partial IDE admission and damaged Blender preferences | The reproduced cases pass after fixes, with exact vendor verification and consumer tests. Native Blender, Windows/Linux and actual device behavior remain unverified. |

Measured production/test lines now total Logistics 89,215 / 75,645,
commonUtils 42,363 / 22,250 and Blue Hole 22,814 / 580. Python file counts are
unchanged. Small production-line changes accompanied substantial targeted failure
coverage; line reduction itself was not used as a quality score.

No numeric 7/10 outcome is asserted. This pass provides evidence for incremental
reliability, testability and persistence consistency gains. An ecosystem-wide
score needs an agreed rubric, deeper review of remaining cyclic groups and native
consumer evidence. See the [work log](overnight_progress.md) for executed checks
and precise limits.
