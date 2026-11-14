# IDE architecture and implementation

Use this reference when changing the project tree, editing lifecycle, or
navigation. Start with the [worked contribution](development.md#try-a-column-guide-change)
to find the desktop workspace and run a focused check.

## Implemented contracts

`ProjectWorkspace` registers one buffer per resolved file path within a
project. `DocumentBuffer` owns the QTextDocument, disk snapshot and highlighter.
Split views share edits, undo, folding and modified state. Cursor, selection
and scroll are view-local. When the representative view closes, a surviving
view takes over. Detach the departing editor from the Qt document layout
before deferred deletion. The last view prompts for unsaved work, and
project/application close prompts once per buffer. Save As changes the
shared path, snapshot and tab titles. Two projects can have independent
buffers for the same file. Shared text IO detects conflicting saves.

`open_path` captures the resolved path, requested group, split intent, cursor
position and callback in `_OpenTarget`. `_publish_open` rechecks the requested
group and falls back to a surviving group. It selects or reuses the canonical
view and places the cursor before invoking the callback. Keep pending opens,
decoding retries and unavailable records in the existing worker queue.

`_finish_restore` applies saved editor positions and splitter geometry after
queued opens finish. The checkpoint tracks project order, active project,
tab groups and browser state. Repeated paths across groups restore multiple
views of one buffer. Missing paths retain their layout records. Navigation
history stays in memory. Reopened projects restore in the main container,
and detached-window geometry is outside the checkpoint. See
[checkpoint admission](development.md#workspace-checkpoint-admission) for format
and recovery limits.

Git's `RepositoryView.edit_file` validates the working path before the shell
routes it to the enabled IDE's `open_registered_file`. IDE selects the deepest
registered root and reopens its retained workspace if needed. If IDE cannot
open the file, the shell can fall back to Text Editor. Historical selections
keep their Git preview while activation opens the current working file.

## Project tree and workspace controls

The project tree wraps the shared lazy `BrowserFileSystemModel`. `ProjectFilter`
applies exclusions and filename filters while retaining filesystem index mapping
and folder-first natural ordering. Inline rename uses the shared validation
and filename delegate. It rejects affected pending opens, active autosaves,
other-project ownership and destination document collisions. On success it
retargets snapshots, document maps, watchers and history, including every open
descendant of a renamed folder. Shared text and undo survive. Deletion is
limited to files and empty folders, and rejects open files and pending opens.

`ProjectGitStatus` runs bounded porcelain-v2 reads on an executor and publishes
on the GUI thread. The tree restricts them to the project subtree. Dirty
submodule contents are read separately, with a 16-repository and five-second
budget. Folders keep their normal color when children change. Ignored items
and descendants show olive foregrounds and status tooltips. Modified buffers
overlay the Git snapshot, including in projects outside Git, and clear on
undo, save or close. Status loss or a failed worker submission clears stale
decorations and permits the next refresh. Closing cancels reads.

Shared Workspace containers own project docking and detachment. Internal
`ScopedTabBar` gestures stay within the project's editor splitter and support
up to three columns. Group moves and merges collapse redundant views while
preserving the buffer. Project shutdown snapshots layout before dock destruction
and honors close vetoes across detached containers. See
[desktop architecture](../../../development/architecture/architecture.md) for the shell
close protocol.

## Find in Files

`ui/find_files.py` sends immutable root, options and live-buffer snapshots
to bounded background search. commonUtils owns matching, masks, exclusions
and UTF-16 result offsets. The IDE owns project scope, the popup, preview
and navigation. Search and preview retain separate futures, and generation
checks reject stale results. Debounced input cancels earlier requests.
Worker submission errors appear in the affected status label and allow retry.
Dismissal cancels work. Project shutdown waits for retained jobs to retire.

## Modifier navigation feedback

`ui/documents.py` owns a transient underline overlay and an 80-ms pointer
poll for Python and stub files while hovered. Qt ControlModifier represents
Command on macOS and Ctrl elsewhere. Background navigation coalesces hovers
and verifies source revision, range, visibility and project configuration
before underlining a resolvable target. Leaving, hiding, editing or releasing
the modifier clears the overlay. Closing stops the timer.

## Usage navigation

`analysis.py` lazily uses Jedi, pinned in `uv.lock`, on serialized background
workers. A process-wide lock protects Jedi's caches. Keep editing available
when Jedi is absent. Jedi can start the configured Python environment for
introspection. A running request can finish after cancellation, so
publication checks source identity, revision, caret, project and active view.

Modifier-click on a function or class declaration requests usages. Imports
and calls follow definitions. F12 requests definition explicitly, and
Shift+F12 requests usages. Usages are deduplicated, limited to the project
root and exclusions, and capped at 200 results. Jedi can miss dynamic
references or aliases. The active file uses the current buffer snapshot.
Other modules use saved content.

## Usage popup presentation

`UsagePopup` anchors to the editor caret and clamps to the application and
screen. Rows carry exact paths, lines and code-point columns. Navigation
converts positions for Qt and records Back history. The worker caches plain
text previews per file for the request and skips disk previews over 1 MiB.
The current file's preview comes from its live buffer. Origin edits,
destruction, hiding and app deactivation dismiss stale results. Escape or
an outside click dismisses the popup.

## Embedded Markdown tabs

`MarkdownDocument` wraps the shared MarkdownViewer for `.md` and `.markdown`
files. `MarkdownBuffer` owns the shared source QTextDocument. Formatted
edits synchronize that source and update other views. Source undo is shared
and formatted undo is view-local. Navigation and persisted positions use
source UTF-16 offsets. Local links open another project tab and carry the
origin's Read/Edit and Formatted/Source choices. Project close and native
view destruction stop speech and diagram work. IDE owns project file identity,
watching, close and conflict decisions. See the
[shared Markdown ownership contract](../../../../Python/commonUtils/docs/development/reference/ui/markdown/markdown.md#internal-ownership-and-embedding-contracts).

## Editor markers and IDE autosave

`Python/services/editors/ui/changes.py:ChangeMarkers` compares immutable
background snapshots. It reads the Git index through the configured
executable when available and otherwise uses the saved file snapshot.
Revision and snapshot checks guard GUI publication. A failed submission
reports unavailable markers and permits a later refresh. Shared gutter APIs
belong to commonUtils.

One `AutoSave` per buffer supports Off, After delay (1,000 ms by default)
and Focus change. Source changes restart the debounce. A worker saves a
captured snapshot and completion compares the submitted source text with
the current text, keeping newer edits dirty. Active writes block final-buffer
close, manual save and reload. Modal save/close choices suppress autosave.
After a failure, use an explicit save or reload to resume. Manual save and
reload IO are synchronous. The buffer is not a crash checkpoint.

### Gutter review and actions

The shared `editor_hunks.HunkReview` controller rechecks buffer identity, text
and the Git index or saved snapshot. Revert applies one undoable text edit.
Staging requires the buffer to match disk and shows the complete Git hunk,
which can cover several markers. The explicit stage action delegates to
Git's checked patch application and leaves the working file untouched.
Stale or destroyed views discard completion, and shutdown cancels queued
work and active Git reads. Use the Git workspace for unsupported operations.

## Validation

| Change | Focused fixture |
| --- | --- |
| Canonical buffers, rename, saved settings or open/restore ordering | `Python/tests/ide/test_ide.py` |
| Lazy tree, ignored paths and dirty submodule files | `Python/tests/ide/test_ide_browser.py` |
| Markdown split sync, link routing, CRLF and close conflicts | `Python/tests/ide/test_ide_markdown.py` |
| Definition hover, usage preview and stale results | `Python/tests/ide/test_ide_links.py` and `test_ide_usages.py` |
| Confined drops, cancellation and group limits | `Python/tests/ide/test_ide_drag.py` |
| Autosave, baselines and reviewed hunks | `Python/tests/editing/test_editor_changes.py` |

For Find in Files, run from the repository root:

```sh
python3 dev.py test desktop --exact-file Python/tests/ide/test_ide_find_files.py
```

Expect six passing cases, covering live-buffer navigation, retry after
submission failure, stale search and preview suppression, and close
cancellation. Shared search matching fixtures live in commonUtils'
`tests/browser/test_search.py`. Offscreen tests cover Qt integration and
document state. Native pointer behavior and appearance require desktop
runtime checks.
