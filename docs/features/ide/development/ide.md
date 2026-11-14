# IDE architecture and implementation

Start with the [worked contribution](development.md#try-a-column-guide-change).

## Implemented contracts

`ProjectWorkspace` keeps one buffer per resolved file per project. Splits share source, undo and modified state. Cursor, selection and scroll belong to views. Detach the closing editor before Qt deletes it. Prompt once per buffer on close. Opens retain requested group and cursor, fall back to a surviving group and place the cursor before callbacks. Restore applies positions after queued opens and retains missing paths. See [checkpoint admission](development.md#workspace-checkpoint-admission).

Git validates the working path before routing. IDE chooses the deepest registered root. Text Editor can serve as fallback. Historical Git previews remain selected.

## Tree, search and navigation

`ui/browser.py` wraps the shared lazy model. Rename blocks pending opens, autosave, cross-project ownership and collisions. It retargets open descendants, snapshots and watchers. Delete allows closed files and empty folders. `ui/git_status.py` overlays dirty buffers and clears stale data on failure. Project splits stay inside their workspace and cap at three columns.

`ui/find_files.py` searches bounded snapshots, including live buffers, and rejects stale search/preview generations. Keep worker retirement on close. `analysis.py` serializes Jedi calls. Publish only for the current revision, caret, project and view. Usage navigation caps at 200 project results. Editing remains available without Jedi.

## Markdown, markers and autosave

Markdown splits share source and source undo. Formatted undo is per-view. Positions use source UTF-16 offsets. Local links carry view modes. See the [shared embedding contract](../../../../Python/commonUtils/docs/development/reference/ui/markdown/markdown.md#internal-ownership-and-embedding-contracts).

Markers use a verified Git index or saved baseline. Hunk revert is undoable. Staging requires buffer/disk agreement and reviewed complete Git hunks. Autosave captures a snapshot and keeps newer changes dirty. Active writes block final close, manual save and reload. Explicit save or reload resumes autosave after failure.

## Validation

Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/ide/test_ide_find_files.py
```

Expect live-buffer navigation, retry, stale-result suppression and close cancellation. For other changes, use `Python/tests/ide/test_ide_browser.py`, `test_ide_markdown.py`, `test_ide_links.py`, `test_ide_usages.py` or `test_ide_drag.py`. Shared markers and autosave use `Python/tests/editing/test_editor_changes.py`.
