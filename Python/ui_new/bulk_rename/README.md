# Bulk rename

The Logistics bulk rename tool, embedded in the main window to the right of the navigation rail. A standalone window remains available for command-line use. Browse a folder, select candidates,
combine filename rules, inspect the **New name** column, then **Rename selected**.
No files change during scanning or preview. Requires Python 3.10+, PySide6 and a
QApplication; the module launcher creates the application itself.

```sh
# From a consuming project's root, with commonUtils under Python/:
PYTHONPATH=Python python -m ui_new.bulk_rename /path/to/folder
# Or display only explicitly supplied files/folders:
PYTHONPATH=Python python -m ui_new.bulk_rename --paths /path/to/a.jpg /path/to/b.jpg
```

## Using the window

The folder tree keeps the filesystem/drive hierarchy visible as you navigate.
The current folder remains selected alongside its parent folders and siblings;
expanded branches stay open. The navigation tree includes hidden directories so
a directly opened path can always be shown; the **Hidden** file-list filter still
controls which candidates are displayed. Expand a folder to choose a deeper location. The up arrow, path field and **Browse** navigate directories. Double-click a
folder row to enter it. Filters accept filename wildcards or a Python regular
expression. Files are included by default; folders and hidden names/OS hidden attributes are opt-in.
**Subfolders** scans recursively without following directory symlinks. Depth zero
means all levels, one includes immediate child folders. **Apply filter** or
**Refresh** rescans the directory; selecting rows changes only the rename scope.
Scans report permission errors rather than silently claiming complete results.

All initially displayed candidates are selected. Ctrl/Cmd-click or Shift-click
changes the selection, and **Select all / Select none** manage it. Only selected
rows participate in the preview or rename. Fix every displayed error first;
unchanged names require no disk operation. Numbering uses natural full-path order
(`page2` before `page10`), independently of selection click order.

Rules combine in this order:

| Panel | Behavior |
| --- | --- |
| 1 · Regular expression | Python pattern/replacement with `\1` or `\g<name>` groups; optionally include the extension |
| 2 · Name | Keep, replace the entire stem with a fixed name, or remove the stem |
| 3 · Replace | Literal substring replacement, case-sensitive or insensitive, all matches or first only |
| 4 · Case | Keep, lowercase, uppercase, title case, sentence case or swap case |
| 5 · Remove | First/last characters, a range, specific characters, digits, punctuation/symbols, accents, or surrounding whitespace |
| 6 · Move / copy a part | Move or duplicate a character range to another position in the stem |
| 7 · Add | Prefix, positioned insertion and suffix |
| 8 · Date | Add modified/creation/current date with a `strftime` format, separator and day offset |
| 9 · Parent folder | Add one or more parent-folder names with a separator |
| 10 · Numbering | Prefix/suffix/positioned counter, start/step/padding, optionally restart per folder |
| 11 · Extension | Keep, lowercase, uppercase, replace or remove the final file extension |

Positions are zero-based and count Unicode characters. Insertion past the end
appends. A file's final extension is protected until the Extension step unless
regex explicitly includes it; folders treat their entire name as the stem,
including dots. Dotfiles without a suffix keep their entire name. Creation date
is offered only when the filesystem exposes birth time; it never substitutes
metadata-change time on Unix (older Windows Python versions use their creation-time
`st_ctime` field when birth time is unavailable). Date rules change names, not file timestamps.

**Save rules / Load rules** store a plain JSON preset. Loading never executes code;
invalid presets leave existing controls unchanged. **Reset rules** restores the
neutral pipeline. **Preview** reruns the live preview explicitly.

## Applying, cancelling and undo

Scanning, planning and renaming run in background workers using the shared
[OperationProgress](../README.md#background-work-and-downloads) component.
Selection and rule previews update rows together without showing a progress panel
or moving the main layout. While calculating, **Preview** becomes **Cancel preview**
in the same space. Scans and rename/undo operations still show full progress.
Changing a rule supersedes an older preview; Rename stays disabled until the
current preview is ready. Python regex matching cannot be interrupted mid-match;
use sensible patterns for large lists. Cancellation is checked between items.

Each batch rechecks source identity/size/mtime and destination occupancy. Duplicate,
existing, reserved or invalid destinations block the whole batch. Case and Unicode
normalization equivalents are treated as collisions by default, even on a
case-sensitive filesystem. Names are restricted to portable Windows-compatible
basenames. Select a folder or its descendants, **not both in the same batch**.
This version renames in place: it does not copy or move files between folders,
edit attributes/timestamps, run scripts, or inspect EXIF capture dates.

Renames stage to unique sibling names, then publish with no-replace OS primitives.
This supports swaps/cycles and case-only changes without overwriting an existing
file or empty directory. On Windows it uses `os.rename`; macOS uses
`renamex_np(RENAME_EXCL)`; Linux uses `renameat2(RENAME_NOREPLACE)`. A platform or
filesystem without exclusive-rename support fails safely. Files retain their
contents and metadata; directory contents and symlink targets are not rewritten.

A failure or cancellation rolls the batch back. Rollback is never cancelled and
never overwrites externally created files. If recovery is blocked, the status
shows the current staged path and original path so data can be recovered manually;
do not delete these `.bulk-rename-*` entries. This is rollback on handled errors,
not a crash-recovery journal or a filesystem lock. A process/power failure can
leave staged paths, and external concurrent changes can block recovery.

**Undo last rename** reverses the last successful batch in this window. It refuses
when renamed items have since changed or original names have become occupied.
The receipt is in memory and is not retained after closing. Rules remain after
applying, but the tool requires a fresh preview before another rename. Closing a
busy window requests cancellation and waits for work and rollback to finish.

## Embed or launch from a button

Applications with an existing QApplication can use:

```python
from ui_new.bulk_rename import BulkRenameWidget, open_bulk_rename

window = open_bulk_rename('/path/to/library', parent=application_window)
selected_window = open_bulk_rename(paths=selected_paths, parent=application_window)
widget = BulkRenameWidget('/path/to/library', parent=application_window)
layout.addWidget(widget)
widget.renamed.connect(lambda receipt: browser.refresh())
```

`open_bulk_rename()` reveals the retained main-window page when Logistics is running, or retains a standalone window until it is closed. `widget.preview_ready`
signals a `RenamePlan`; `widget.renamed` signals a successful `RenameResult` after applying or undoing a batch.
`selected_paths()`, `load_directory(path)`, `apply()` and `undo()` are available.
An embedding host should honor `widget.can_close()` (false while work is running,
with cancellation requested) and retry closing on `widget.idle` if it initiated
that close. Do not destroy a running widget or its worker.

A file-browser action provider can add the tool without changing library defaults:

```python
from ui_new.bulk_rename import bulk_rename_actions
from commonUtils.ui.file_browser import FileBrowser

browser = FileBrowser('/path/to/library', action_providers=(bulk_rename_actions,))
```

The provider opens only selected paths and refreshes the browser after a successful
rename or undo. It is opt-in; existing browsers keep their current actions. When
a parent is supplied to the standalone window, its normal Close event is deferred
until any rename worker has cancelled and rolled back safely.

## Use the engine without Qt

```python
from pathlib import Path
from commonUtils.filesystem.rename import RenameRules, plan_renames, apply_renames, undo_renames

rules = RenameRules(prefix='Photo_', number_mode='suffix', number_padding=3,
                    extension_mode='lower')
plan = plan_renames(Path('/path/to/photos').glob('*.JPG'), rules)
for entry in plan.entries:
    print(entry.source.name, '→', entry.target.name, entry.error)

if plan.valid and plan.changes:
    result = apply_renames(plan)
    if result.success:
        # Retain result as an optional in-memory undo receipt for the application.
        undo_receipt = result
    else:
        print(result.error, result.recovery)
```

`plan_renames(..., case_sensitive=True)` permits distinct-case names for projects
that explicitly target case-sensitive filesystems. The UI uses the conservative
default. `apply_renames` and `undo_renames` accept `cancelled()` and
`report(done, total, message)` callbacks; do not touch Qt widgets from workers.
Invalid/stale plans raise before disk changes. Failures during a transaction return
`RenameResult(error=..., recovery=...)`; successful results contain changed entries.
`success`, `cancelled`, `error` and `recovery` distinguish all outcomes.

Internals are separated into Qt-independent `renameUtils.py`, rule controls in
`rules.py`, worker/UI coordination in `widget.py`, and public window/lifetime code
in `__init__.py`. The shared engine is documented in
[commonUtils](../../commonUtils/filesystem/rename/README.md). Filtered traversal lives in `commonUtils.filesystem.traversal`; transformations accept explicit `RenameMetadata` for folders and file dates without reading the filesystem.

## Main-window hosting

Logistics keeps one Bulk Rename destination. Browser requests replace its candidate
selection while retaining rules and filters; they do not create more tabs or windows.
The latest request wins during scanning/preview; an active rename or undo finishes
before the new selection loads. Closing Logistics cooperatively stops the worker.
`open_bulk_rename` uses the registered main-window host when available and otherwise
opens the standalone window. Pass `standalone=True` to explicitly bypass hosting.
