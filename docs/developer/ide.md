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
