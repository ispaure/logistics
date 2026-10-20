# Bulk rename integration

[User guide: rules, preview, apply and recovery](../user/user.md).

```sh
# From a consuming project's root, with commonUtils under Python/:
PYTHONPATH=Python python -m ui_new.bulk_rename /path/to/folder
# Or display only explicitly supplied files/folders:
PYTHONPATH=Python python -m ui_new.bulk_rename --paths /path/to/a.jpg /path/to/b.jpg
```

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
The folder tree retains its filesystem root while revealing the current folder.
Reveal explicitly fetches unloaded folder contents, including empty folders that
Qt does not expand, and retries queued row insertion/layout until the selected
row has stable visible geometry. Already-populated ancestors need not emit a
fresh load notification. Later notifications do not reopen user-collapsed branches.
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
[commonUtils](https://github.com/ispaure/commonUtils/blob/main/filesystem/rename/README.md). Filtered traversal lives in `commonUtils.filesystem.traversal`; transformations accept explicit `RenameMetadata` for folders and file dates without reading the filesystem.

## Main-window hosting

Logistics keeps one Bulk Rename destination. Browser requests replace its candidate
selection while retaining rules and filters; they do not create more tabs or windows.
The latest request wins during scanning/preview; an active rename or undo finishes
before the new selection loads. Closing Logistics cooperatively stops the worker.
`open_bulk_rename` uses the registered main-window host when available and otherwise
opens the standalone window. Pass `standalone=True` to explicitly bypass hosting.

Rule groups use independent vertical stacks, up to six columns selected by the
available width. Packing uses group size hints; paired numeric fields and
checkboxes reduce row count. Controls retain their identities and values during
reflow. The browser/rules splitter initially gives the rules more vertical space;
narrow windows keep a scroll area. Rename planning/apply behavior is unchanged.
