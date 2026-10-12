# IDE architecture and implementation plan

## Audit and ownership

The existing TextEditor already consumes commonUtils CodeEdit, EditorViews,
SyntaxHighlighter (Pygments), SearchPanel and persistence.text. These supply line
numbers, undo, indentation, pairing, folding, line commands, encoding/BOM/newline
preservation and conflict-checked atomic saves. No editor relocation is needed.
TextEditor document/service/session objects own standalone windows and recovery;
IDE owns project-scoped documents instead, without importing that feature.

GitPage and IDEPage retain their application-level panes in shared Workspace
containers. IDE project tabs use WorkspacePolicy, including detached local creation
and full-width headers. Each project is a QMainWindow menu source; its internal
QTabWidgets use commonUtils ScopedTabBar with the editor splitter as their boundary.
Internal file gestures never enter the OS-window docking controller. MainWindow's can_close/prepare_close/idle protocol
remains the shutdown boundary. Shared SearchPanel and ResultWorker require owner
retention until completion.

The full FileBrowser includes previews, indexing and application activation.
Reuse its BrowserFileSystemModel (lazy QFileSystemModel, shared File/Directory
objects and registry), wrapped in an IDE-scoped tree with exclusions. Avoid a
second browser or recursive UI-thread scan. Historical fileUtils/dirUtils imports
no longer exist in this checkout; use filesystem packages. File snapshots must
be refreshed after mutations.

ProjectFilter extends the shared ByteSortModel and sorts the name column ascending,
retaining folder-first natural ordering, dynamic updates and filesystem-index
mapping while applying project exclusions and the visible filename filter.

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

GitPage delegates validated working-file opens through an application-owned
callback. MainWindow routes to the enabled IDE page's open_registered_file,
which chooses the deepest resolved registered root, reopens its workspace and
uses normal open_path document reuse. A false result falls back to Text Editor.
The callback looks up the current page at invocation, including feature changes;
Git and IDE do not import each other's document services. Detached projects retain
their existing workspace. Git's existing filesystem watcher refreshes IDE saves.
Diff and merge workflows remain owned by Git.
File status, History and Search file double-clicks share RepositoryView.edit_file;
historical entries supply their repository-relative path to open the current
working file, while selection retains the historical preview. Folder rows have
no file activation, and missing or out-of-repository files fail validation.

IDE is an independent lazy PageContribution (`ide.workspace`). ProjectStore keeps
UUID registrations and all project layouts in one version-1 atomic workspace JSON
beside Logistics preferences. It checks the previous bytes before publication to
reject competing instance writes (this is not a cross-process lock). Corrupt or
unsupported stores are retained. Store write failures are reported in the page;
they do not trap the application in an endless shutdown wait after document close
choices have completed.

ProjectWorkspace owns one canonical file registration per resolved path. Each
registration points to a representative EditorDocument view; all views share a
DocumentBuffer containing the QTextDocument, disk snapshot and one highlighter.
The text document is parented to the buffer, not to a disposable tab. Closing the
representative promotes a remaining view and reattaches highlighting. A departing
editor is explicitly detached from the shared Qt layout before deferred deletion.
This ownership boundary is covered by editing after actual native destruction of
the original view, not merely checking that a tab disappeared.

Split right creates another view in a new group. Ordinary opens prefer an existing
view in the active group. Each group contains at most one view per file. Group
merges and moves collapse redundant views without discarding shared edits. The
last view close asks about unsaved work; project/application close prompts once
per buffer. Save As changes the shared snapshot/path and every tab title. Undo,
folding and modified state are shared; cursor, selection and scrolling are local.
Internal groups are QTabWidgets with project-confined tab bars. Browser mutations refuse to rename or
delete paths containing an open document or pending open; only empty directory
deletion is available. The shared model owns lazy loading and rename validation.

ResultWorker requests are serialized per project; a process-wide lock serializes
Jedi's caches across projects. GUI inputs are copied before dispatch. Analysis
results validate source identity, revision, cursor and active view. Search and
quick-open scans have exclusions, limits and cooperative cancellation. Jedi cannot
be forcibly interrupted; owners are retained until it returns. SearchPanel keeps
its own cooperative worker lifecycle. No project code is executed by IDE itself;
Jedi may start its configured Python environment for introspection.

State captures project order, active project/group/files, tab order, splitter sizes,
per-view cursor/scroll locations and tree expansion/filter/selection. Repeated
paths in different group records restore separate views of one buffer; existing
version-1 stores remain compatible. Missing file
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
| Shared documents | The later shared-view implementation resolves this gap; see the current contracts above. |
| Responsiveness | Save/reload and filesystem metadata probes remain synchronous; slow/network storage can stall the GUI. A busy workspace vetoes close and requires retry. |
| Relocated roots | Root settings change browsing/analysis, but do not rebase absolute document paths. Missing registrations are retained. |
| Browser mutations | Open files must be closed before rename/delete; recursive deletion is unavailable. Confined drag and menu moves are available. |
| Intelligence | Manual documentation and completion; no automatic hover, diagnostics, unsaved imported-module overlays or Git handoff. These were optional productivity choices. |
| Highlighting | Blade mixed-language support remains limited for multiline constructs. |
| Persistence | Byte comparison detects intervening instance saves but is not a cross-process transaction; simultaneous writers can still race. |
| Validation | Native Windows/Linux interactions remain unverified. |

Second-pass validation: 14 focused IDE tests pass on macOS with offscreen Qt,
including four new regression workflows and expanded stale-result coverage. Ruff
and diff whitespace checks pass. The earlier full-suite counts above are the
initial implementation's validation, not a claim that all suites were rerun after
this review. No commonUtils implementation changes were required in this pass.

## Shared-view implementation and reuse review

The shared-view update adds four workflow tests covering bidirectional editing,
shared undo/redo and modified indicators, independent cursor/scroll restoration,
closing and destroying the original view, Save As propagation, external conflicts,
reload, duplicate merging and one close prompt per modified buffer, plus navigation from the secondary view. All 18 IDE
tests pass on macOS/offscreen Qt. The 34 standalone Text Editor tests and three
shared CodeEdit tests also pass. Ruff and diff whitespace checks pass. Native Windows/Linux checks remain outstanding.

The documentation audit updated the user guide, this architecture contract, the
feature overview and root capability row. It also corrected the analysis limit
(characters rather than bytes), identified disk-only project search and clarified
the limits of simultaneous configuration writes. Earlier validation sections are
historical and do not imply a new full-suite run.

The three follow-up refactors are now implemented:

1. IDE and standalone EditorViews use commonUtils' shared CodeEdit attachment and
   detachment APIs. Their lifecycle contracts are documented in that repository's
   code-editor API guide; project paths and close policy remain in Logistics.
2. IDE rebinds the existing shared highlighter when the original view closes,
   instead of destroying/recreating it. Its theme timer has highlighter ownership.
3. IDE Navigation.place_view centralizes cursor clamping, 1-based line/code-point
   column conversion to Qt UTF-16 offsets, and scroll placement. navigate_to applies
   locations through open_path's completion callback to the exact opened view.
   Definitions, project search, history, go-to-line, split creation and session
   restoration use these helpers, removing the extra queued positioning jobs.

Text snapshot encoding and conflict-checked writes already live in commonUtils;
do not create another persistence abstraction. Standalone TextEditor's document
service also owns recovery and window policy, so reusing that whole service for IDE
would couple distinct workflows. A future async IO refactor should reuse only its
worker/snapshot boundary, while retaining each feature's close and recovery policy.
The refactors preserve the documented user workflows and version-1 saved state.
Regression coverage includes detach/reattach without duplicate folding hooks,
highlighter rebinding through native view destruction and palette changes, and
queued navigation with non-BMP characters into distinct target groups.

Refactor validation on macOS/offscreen Qt: 19 IDE tests, 34 standalone Text Editor
tests and 26 shared code-editor/component tests pass (79 total). Ruff and diff
whitespace checks pass. Native Windows/Linux and other commonUtils consumers were
not validated in this pass. Unrelated workspace/menu edits remain outside these
commits.

## UI refinement — 2026-10-11

ProjectWorkspace menus route through the existing workspace menu publisher. IDEPage
creates projects in the requesting container and retains registrations across closes.
Every project remains a single workspace pane, including its browser and editor
groups. Internal drops move the existing EditorDocument or merge redundant views;
empty columns are pruned, while closing a group moves files into a remaining group.
There is a three-column cap and no external/cross-project file-tab transfer path.
Confined gestures are observed across child-widget event receivers until release
or cancellation, so a destination editor cannot strand the source's drag state.
The shared component owns that gesture routing; IDE continues to own drop
validation, column placement and document lifetimes. Regression tests exercise
repeated two-column side drops through both source and destination receivers,
header/center merges, split recreation, Escape/outside cancellation and the cap,
with unsaved buffers, cursors and undo history retained.
Drag-completion validation on macOS: all 36 IDE tests in six isolated modules,
eight shared scoped-tab tests, and four shared workspace test modules passed.
The 12 focused IDE/scoped-tab tests also passed under native Cocoa. The gesture
matrix covers 48 side drops across three window widths and both event receivers,
plus 24 QTest press/move/release side drops, merges and cancellation. Native
Windows/Linux pointer behavior remains unverified.
Project close snapshots layout before dock destruction and honors unsaved-close vetoes.
Application shutdown covers projects in every detached container. Session restore
reopens projects in the main container; detached OS-window geometry is not persisted.

Tests cover zero/one/two/three projects, equal widths, local detached creation,
minimum panel widths, group moves/merges, unsaved state, close vetoes and menu routing.
Platform and full-suite results are recorded in the UI refinement validation report.

## Modifier navigation feedback

IDE EditorDocument views own a transient hyperlink overlay and an 80-ms pointer/
modifier poll while hovered. Qt ControlModifier represents Command on macOS and
Ctrl elsewhere. Only Python/stub views expose the hand cursor and request target
analysis. The overlay uses ExtraSelection, preserving shared editor selections
and document formatting; standalone CodeEdit/Text Editor behavior is unchanged.
Navigation uses the existing serialized worker queue, coalesces pending hovers per
view, and validates source path/revision, hover range, visibility and project
configuration before showing a blue underline for targets with existing files.
Missing intelligence silently leaves the symbol unstyled. Leaving, hiding, editing
or releasing the modifier clears feedback; closing stops the view timer.

Validation: 24 IDE tests (including hover feedback and stale-result coverage) and
34 standalone Text Editor tests pass on macOS with offscreen Qt. Ruff and diff
whitespace checks pass. Native Windows/Linux pointer interaction remains untested.

## Usage navigation

Modifier-click dispatches a `navigate` analysis snapshot. Jedi's public get_names
API and the declaration-line prefix identify function/class declaration names
at the clicked line/column (imported names retain definition navigation); those
request get_references instead of jumping back to themselves. Calls keep normal
definition navigation, and F12 remains explicit definition navigation. Shift+F12,
Navigate → Find usages and modifier+Shift-click explicitly request usages.
References use Jedi's project scope, omit definition/binding names and builtins,
filter results to the resolved project root and configured exclusions, deduplicate
and cap at 200. This is a result limit, not a scan/time limit; Jedi can stop early
and cannot be forcibly interrupted. Imported aliases/dynamic references may be
incomplete. The current buffer is a snapshot; other modules use saved content.
An editor-anchored usage popup is shown even for one usage; selection uses existing history and
UTF-16-aware navigation. The same revision/caret/view/project checks protect late
results and popup selection. Hover feedback still uses definition resolution and
does not run project reference searches. Standalone Text Editor is unchanged.

Usage-navigation validation: all 27 IDE tests pass on macOS/offscreen Qt. The
focused three-test usage suite also passes after refining import-name detection;
coverage includes cross-file calls, unrelated same-name functions, exclusions,
unused declarations, the actual modifier-click picker, Back, and stale edits.
Ruff and whitespace checks pass. Native Windows/Linux remains untested.

## Embedded Markdown tabs

IDE dispatches `.md`/`.markdown` opens to its MarkdownDocument adapter around
commonUtils MarkdownViewer. Other files retain EditorDocument. MarkdownBuffer
owns the source QTextDocument independently of tab lifetime; formatted changes
synchronize to that source immediately, and other views refresh their presentation.
The shared rich editor itself and its interactive controls remain in commonUtils;
project identity, file operations, conflict checks, watcher registration and close
policy remain in IDE. Standard shortcuts route through project menus, while
Markdown-specific formatting shortcuts remain local. Local document links request
project opens rather than replacing a tab's identity. Native destruction of a
Markdown view detaches its source document and stops speech/diagram work; project
shutdown also stops those services. Navigation/persisted positions use source
UTF-16 offsets. Rich undo stacks are per view; source undo is shared.

Focused regression coverage checks mixed code/Markdown tabs, untouched CRLF saves,
formatted split synchronization, source editing after native view destruction,
external conflicts, close vetoes, link routing, Save As identity and reload.

## Usage popup presentation

UsagePopup is a parent-owned Qt.Popup frame, shown without exec or dialog window
chrome. Its flat table displays filename, line and a bounded code preview, plus
project scope, count and a local text filter. Preview reads run in the analysis
worker, are cached per file for the request, skip files over 1 MiB and use the
current buffer snapshot for the source file. Preview text is plain text; it cannot
render HTML from project files. Rows retain exact paths/line/code-point columns
for existing navigation. Escape/outside clicks dismiss, Enter/single-click opens,
and edits, origin destruction, owner hiding or app deactivation dismiss stale UI.
Placement clamps to the application/screen intersection near the source caret.
The existing analysis cap and semantic limits remain unchanged; no project code
is executed for previews.

Popup validation: 37 IDE tests pass on macOS/offscreen Qt; the final focused
five-test usage suite passes, including outside-click/Escape dismissal, filtering,
Enter navigation, stale edits, and bounded/unsaved source previews. A rendered
dark-palette popup was inspected for column layout, selection and truncation.
Ruff and whitespace checks pass. Native Windows/Linux popup behavior remains
unverified.

## Editor markers and IDE autosave

Logistics `features.editor_changes.ChangeMarkers` owns immutable background diff
requests, revision/snapshot validation and two-second baseline refresh for IDE and
Text Editor. It lazily uses Git's read-only `editor_baseline` provider, independent
of page activation and repository registrations, and falls back to the document's
saved snapshot when unavailable. Jobs retain Python values only; Qt owners may
close while reads finish. One pending job per controller and two worker threads
bound concurrency. Shared gutter APIs are documented in commonUtils.

IDE owns one AutoSave per DocumentBuffer, including Markdown buffers. Project
metadata stores off/after_delay/focus_change (default after_delay, 1000 ms). Snapshot
encoding and conflict-checked publication run on the workspace's retained worker
queue. A revision check prevents completion from clearing newer edits. Active
writes veto final-buffer close, manual save and reload; workspace shutdown already
waits for its worker queue. Modal save/close choices suppress autosave. Failures
pause that buffer until an explicit save/reload succeeds and remain in a dedicated
notice. Split views do not duplicate writes. Manual save/reload IO remains
synchronous; autosave provides no crash checkpoint or cross-process writer lock.

Validation on macOS/offscreen Qt: all 40 existing IDE tests and 36 standalone
Text Editor tests passed, along with seven new baseline/autosave cases. The
commonUtils suite ran 792 tests across 108 isolated modules with three skips and
no failures, including marker rendering.
Visual inspection confirmed separate marker, folding and line-number lanes.
Native Windows/Linux interaction and other commonUtils consumers remain untested.

### Gutter review and actions

The follow-up `editor_hunks.HunkReview` uses the host's retained worker queue for
baseline validation and Git jobs. Gutter hits use the current published snapshot
and document revision; review actions revalidate live buffer identity/text. Revert
rechecks the Git index (or saved snapshot) and replaces just the selected range
through one QTextCursor edit block, converting offsets to UTF-16 for Qt. IDE's
normal autosave policy applies to the resulting edit.

Staging first verifies that the full buffer matches disk, loads a complete Git
hunk and shows its exact patch (which may group nearby markers). The explicit stage
action delegates to Repository.apply_hunk, preserving its status, attribute,
regular-file and stale-patch validation. Staging never writes the working file.
GUI completion callbacks reject destroyed views and stale buffers; jobs remain
owned by each host's existing worker lifecycle. Git UI activation/registration is
not involved. Untracked and otherwise unsupported hunk operations stay in the
Git feature's file workflows.

Document destruction cancels queued gutter futures and signals the Git runner to
stop active reads. No Qt objects enter the background executor.

Hunk-action validation on macOS/offscreen Qt: six new hunk/lifecycle tests and the
seven baseline/autosave tests passed. The existing Git suite passed 121 tests
across seven isolated modules; standalone Text Editor passed 36 tests across three
modules after worker integration. Visual inspection covered the review dialog.
