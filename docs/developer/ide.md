# IDE architecture and implementation plan

## Audit and ownership

The existing TextEditor already consumes commonUtils CodeEdit, EditorViews,
SyntaxHighlighter (Pygments), SearchPanel and persistence.text. These supply line
numbers, undo, indentation, pairing, folding, line commands, encoding/BOM/newline
preservation and conflict-checked atomic saves. No editor relocation is needed.
TextEditor document/service/session objects own standalone windows and recovery;
IDE owns project-scoped documents instead, without importing that feature.

GitPage retains repository panes in Workspace, which permits detachment. IDE uses
ordinary movable QTabWidgets for project and editor tabs and QSplitters for groups;
internal tabs cannot detach. MainWindow's can_close/prepare_close/idle protocol
remains the shutdown boundary. Shared SearchPanel and ResultWorker require owner
retention until completion.

The full FileBrowser includes previews, indexing and application activation.
Reuse its BrowserFileSystemModel (lazy QFileSystemModel, shared File/Directory
objects and registry), wrapped in an IDE-scoped tree with exclusions. Avoid a
second browser or recursive UI-thread scan. Historical fileUtils/dirUtils imports
no longer exist in this checkout; use filesystem packages. File snapshots must
be refreshed after mutations.

Use Logistics preferences_path for platform conventions and atomic JSON for a
versioned IDE store, outside source trees. UUIDs identify projects. Missing roots
remain registered. Save layout on a debounce and close, not every cursor movement.

Jedi 0.19.2 (MIT, pure Python, Windows/macOS/Linux; parso dependency) provides
project/source-path-aware goto, inference and symbols without an LSP executable
or server lifecycle. Run requests serially on retained background workers; reject
stale document results. Import only on demand and preserve editing when absent.
See https://jedi.readthedocs.io/en/v0.19.2/docs/api.html and
https://pypi.org/project/jedi/0.19.2/. Add to uv manifest/lock; release packaging
already ships synchronized dependencies and the pinned commonUtils checkout.

## Phases and validation

1. Confirm shared editor reuse and regression coverage; add only needed extensions.
2. Add versioned project store, settings and independent lazy feature registration.
3. Add browser, canonical document ownership, up to three non-detachable groups,
   conflict-aware saves, close vetoes and layout restoration.
4. Integrate Jedi, modifier-click, definition/history, quick file and line navigation.
5. Extend shared Pygments detection for Python stubs, PHP and compound Blade names.
6. Add bounded worker-backed file search and symbol navigation using existing tools.
7. Run focused tests and both repository suites; document actual platform coverage.

Each coherent phase is tested/reviewed and committed before continuing. Tests use
isolated stores and temporary source trees, exercising persistence, imports,
shared buffers, close cancellation, external edits and retained worker shutdown.
No changes to commonUtils public interfaces or unrelated feature dependencies are
planned. No source repository configuration directories are created.

## Implemented contracts

IDE is an independent lazy PageContribution (`ide.workspace`). ProjectStore keeps
UUID registrations and all project layouts in one version-1 atomic workspace JSON
beside Logistics preferences. It checks the previous bytes before publication to
reject competing instance writes (this is not a cross-process lock). Corrupt or
unsupported stores are retained. Store write failures are reported in the page;
they do not trap the application in an endless shutdown wait after document close
choices have completed.

ProjectWorkspace owns one canonical EditorDocument per resolved path. Opening an
existing path activates that view; moving tabs reparents the existing widget.
Closing a column migrates its tabs. This deliberately avoids duplicate independent
buffers without introducing multiple views of one file in the initial version.
All internal tabs are ordinary QTabWidgets. Browser mutations refuse to rename or
delete any path containing an open document; only empty directory deletion is
available. The shared model owns lazy filesystem loading and rename validation.

ResultWorker requests are serialized per project; a process-wide lock serializes
Jedi's caches across projects. GUI inputs are copied before dispatch. Analysis
results validate source identity, revision, cursor and active view. Search and
quick-open scans have exclusions, limits and cooperative cancellation. Jedi cannot
be forcibly interrupted; owners are retained until it returns. SearchPanel keeps
its own cooperative worker lifecycle. No project code is executed by IDE itself;
Jedi may start its configured Python environment for introspection.

State captures project order, active project/group/files, tab order, splitter sizes,
file cursor/scroll locations and tree expansion/filter/selection. Missing file
records survive saves. Navigation history stays in memory. Opening the same path
in different projects intentionally creates project-independent buffers; shared
text IO detects conflicting saves. External watchers report changes and saves
always revalidate original disk bytes. Buffers are not crash checkpoints.

Jedi 0.19.2 and parso 0.8.7 are MIT/OS-independent Python dependencies pinned in
uv.lock. Pygments remains 2.19.2. Shared commonUtils changes are limited to language
detection and a Blade overlay delegating PHP/HTML grammar work to Pygments.
Future work should move bounded save/reload IO off the GUI thread, add optional
unsaved-import overlays, and validate native Windows/Linux interaction. Automatic
diagnostics, automatic hover and Git handoff are outside this initial selection.

## Validation record — 2026-10-11

Validated with Python 3.12.2 / PySide6 6.6.2 on macOS 26.6.2 ARM64:

- Logistics: 840 tests across 78 isolated modules; zero failures or skips.
- commonUtils: 662 tests across 90 isolated modules; zero failures, one expected
  case-sensitive-filesystem skip on this volume.
- Release tooling: 10 tests passed. Historical comic compression parity passed.
- Repository Ruff checks passed. Offscreen visual inspection covered three editor
  groups, file tree, Python/TOML/Blade colors and full-height layout. Palette tests
  cover light and dark syntax rendering.
- Dedicated IDE tests cover serialization, malformed/conflicting stores, source and
  interpreter paths, imported definitions, modifier-click and back/forward,
  stale results, search cancellation/exclusions/binary files, canonical buffers,
  the three-group cap, cancelled closes, independent project restoration, missing
  files, split sizes, external writes/deletions and own-save watcher notifications.

The first broad runs exposed shared-index contention and a native Bulk Rename
fixture cleanup crash. The regression runner now gives each process a private
index and isolates both repositories' test modules. The Bulk Rename fixture
retires its window/models before removing its temporary sources; it also passed
three consecutive focused reruns. Final full-suite reruns passed after these
repairs. The generic regression runner's release-tooling tests still pass without
commonUtils on the import path.

Commands: `Python/tests/run_regressions.py Python/tests --isolate-modules` and
`Python/tests/run_regressions.py Python/commonUtils/tests --isolate-modules`, using
the project interpreter with `PYTHONPATH=Python` and `QT_QPA_PLATFORM=offscreen`.
The platform runner invokes both suites plus compression parity.

Windows/Linux native desktop behavior has not been tested here. These checks do
not establish debugger, diagnostics, crash recovery, or full dynamic Python/Blade
analysis support. Concurrent unrelated File Browser/Folder Hub/workspace changes
were present in the shared checkout during validation and were not staged in IDE
commits.

Implementation commits in Logistics: `af1e1d5`, `5037a3a`, `1c2d860`, `8acbbd4`,
`d180dd7`, `13f7532`, `a902793`, `3ccb91b`, `c39b5cb`, `0485a04`, `542bb9d`,
`a2b5784`, `990c129`. This validation record is a separate documentation commit.
Shared commonUtils commits: `7fc93d1` (PHP/Blade support) and `dc134af` (PHP/HTML
state across lines), with the latter pinned by Logistics.

## Second review — 2026-10-11

A requirement-by-requirement source review and adversarial workflow tests found
defects not exercised by the initial suite. This pass fixes:

- Back/forward branching after returning from a definition: new jumps replace
  the old forward branch and preserve the new destination.
- Restoration dropping unreadable file records and losing the group/cursor of
  temporarily missing files. These records now retain their placement.
- Browser rename/delete racing with queued opens, including during modal
  confirmation. Both open buffers and pending reads protect affected paths.
- Browser exclusions accepting `.` and thereby filtering out its own root.
- Pending tree expansion/selection being lost before directories become available;
  selection changes now also trigger persistence.
- Reveal opening only a containing folder: IDE now uses shared desktop reveal.
- Completion callback exceptions preventing worker cleanup and queue progress.
- Analysis accepting results from an obsolete project source-path/interpreter
  configuration, or after changes during a target/completion dialog.
- Scan limits counting only files: empty directory trees now consume the budget.

The implementation covers project registration, independent projects, persistent
layouts, one-to-three groups, safe close prompts, shared editing/highlighting,
Python definition/import navigation, history, file/line/symbol navigation, basic
completion/documentation and bounded project search. It does **not** implement
every preferred or optional capability in the mandate:

| Area | Remaining limit |
| --- | --- |
| Shared documents | One canonical editor widget per file; simultaneous views of the same file are absent. This meets conflict avoidance but not the preferred multiple-view design. |
| Responsiveness | Save/reload and filesystem metadata probes remain synchronous; slow/network storage can stall the GUI. A busy workspace vetoes close and requires retry. |
| Relocated roots | Root settings change browsing/analysis, but do not rebase absolute document paths. Missing registrations are retained. |
| Browser mutations | Open files must be closed before rename/delete; recursive deletion and drag between groups are absent. Menu moves are available. |
| Intelligence | Manual documentation and completion; no automatic hover, diagnostics, unsaved imported-module overlays or Git handoff. These were optional productivity choices. |
| Highlighting | Blade mixed-language support remains limited for multiline constructs. |
| Persistence | Byte comparison detects intervening instance saves but is not a cross-process transaction; simultaneous writers can still race. |
| Validation | Native Windows/Linux interactions remain unverified. |

Second-pass validation: 14 focused IDE tests pass on macOS with offscreen Qt,
including four new regression workflows and expanded stale-result coverage. Ruff
and diff whitespace checks pass. The earlier full-suite counts above are the
initial implementation's validation, not a claim that all suites were rerun after
this review. No commonUtils implementation changes were required in this pass.
