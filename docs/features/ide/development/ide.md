# IDE architecture and implementation

Start with the [project settings walkthrough](development.md#follow-a-project-setting).

## Implemented contracts

`ProjectWorkspace` keeps one buffer per resolved file per project. Splits share source, undo and modified state. Cursor, selection and scroll belong to views. Detach the closing editor before Qt deletes it. Prompt once per buffer on close. Opens retain requested group and cursor, fall back to a surviving group and place the cursor before callbacks.

`ui/workspace.py` decodes the saved layout once at the start of restore. It queues opens with their saved cursor positions, then uses the decoded plan to apply scroll positions, tab selection, and splitter widths against the live groups. Unavailable file records keep their saved data for a future restore. See [checkpoint admission](development.md#workspace-checkpoint-admission).

Git validates the working path before routing. IDE chooses the deepest registered root. Text Editor can serve as fallback. Historical Git previews remain selected.

## Tree, search and navigation

`ui/browser.py` wraps the shared lazy model. Rename blocks pending opens, autosave, cross-project ownership and collisions. It retargets open descendants, snapshots and watchers. Delete allows closed files and empty folders. `ui/git_status.py` overlays dirty buffers and clears stale data on failure. Project splits stay inside their workspace and cap at three columns.
On macOS the browser uses the shared vnode watcher to re-list affected expanded
directories through the existing model. Model indexes, filters and selection
stay in place.

`ui/find_files.py` searches bounded snapshots, including live buffers, and rejects stale search/preview generations. Keep worker retirement on close. `analysis.py` serializes Jedi calls. Publish only for the current revision, caret, project and view. Usage navigation caps at 200 project results. Editing remains available without Jedi.

`search.py` supplies the shared directory cache to `commonUtils.search.files`.
Find in Files reuses saved child names for unchanged folders and enumerates
changed or uncached folders, keeping project exclusions and file masks. It does
not start an index build or wait for background indexing. The database contains
names/metadata, so text matching still reads current files or unsaved buffers.

## Markdown, markers and autosave

Markdown splits share source and source undo. Formatted undo is per-view. Positions use source UTF-16 offsets. Local links carry view modes. See the [shared embedding contract](../../../../Python/commonUtils/docs/development/reference/ui/markdown/markdown.md#internal-ownership-and-embedding-contracts).

Markers use a verified Git index or saved baseline. Hunk revert is undoable. Staging requires buffer/disk agreement and reviewed complete Git hunks. Autosave captures a snapshot and keeps newer changes dirty. Active writes block final close, manual save and reload. Explicit save or reload resumes autosave after failure.

The workspace watches open files and available parent directories. On replacement
or recreation it re-arms the file watch. Worker reads apply only to the same
buffer and baseline. Clean reload preserves each view’s cursor, selection and
scroll where possible. Dirty buffers keep their draft and show a notice.
Manual and delayed saves use the same guarded publication. The writer stages
the draft beside the target, moves the actual disk entry into private staging
and verifies it, then publishes without replacing an entry created by another
writer. If restoration is blocked, staging retains the displaced file and the
conflict reports its path.

## Validation

Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/ide/test_ide_find_files.py
```

Expect live-buffer navigation, shared-index reuse, retry, stale-result suppression and close cancellation. Shared `test_search.py` covers changed-folder fallback, exclusions, links and result limits. For other changes, use `Python/tests/ide/test_ide_browser.py`, `test_ide_markdown.py`, `test_ide_links.py`, `test_ide_usages.py` or `test_ide_drag.py`. Use `Python/tests/ide/test_ide_external_edits.py` for watcher and save-race coverage. Shared markers and autosave use `Python/tests/editing/test_editor_changes.py`.
