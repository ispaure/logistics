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
