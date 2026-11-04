# Bulk rename integration

[User guide: rules, preview, apply and recovery](../user/user.md).

```sh
# From a consuming project's root, with commonUtils under Python/:
PYTHONPATH=Python python -m desktop.bulk_rename /path/to/folder
# Or display only explicitly supplied files/folders:
PYTHONPATH=Python python -m desktop.bulk_rename --paths /path/to/a.jpg /path/to/b.jpg
```

## Embed or launch from a button

Applications with an existing QApplication can use:

```python
from desktop.bulk_rename import BulkRenameWidget, open_bulk_rename

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
fresh load notification. A temporarily missing model index also retains the
reveal retry, including when a new branch arrives after its parent's load signal.
Each retry fetches and expands ancestors from the filesystem root down before
requesting the leaf index, so an unloaded parent cannot stall a missing child.
Later notifications do not reopen user-collapsed branches.
The private `_FolderTree` view owns deferred layout correction, independently of
filesystem scans and rename workers. Queued model sorting and row insertion
preserve a selection that was visible
before the model change. The deferred layout correction scrolls without expanding
branches; a selection already outside the viewport is left alone, preserving
manual scrolling. Hidden/closed widgets do not apply that correction.
Scrolling also accounts for the selected folder's indentation: Qt may otherwise
align the column's left edge after layout and hide a deep folder to the right
of a narrow sidebar even though its selected row remains vertically visible.
An embedding host should honor `widget.can_close()` (false while work is running,
with cancellation requested) and retry closing on `widget.idle` if it initiated
that close. Do not destroy a running widget or its worker.

A file-browser action provider can add the tool without changing library defaults:

```python
from desktop.bulk_rename import bulk_rename_actions
from commonUtils.ui.file_browser import FileBrowser

browser = FileBrowser('/path/to/library', action_providers=(bulk_rename_actions,))
```

The provider opens only selected paths and refreshes the browser after a successful
rename or undo. It is opt-in; existing browsers keep their current actions. When
a parent is supplied to the standalone window, its normal Close event is deferred
until any rename worker has cancelled and rolled back safely.

## Widget composition

`BulkRenameWidget` initializes worker/preview state and timers, then schedules the
initial candidate load. Its private `_build_folder_controls`, `_build_browser_area`
and `_build_action_area` methods assemble the existing controls in the same order.
They remain in the widget owner; there is no extra controller or package layer.
Folder controls own address/filter construction, the browser area owns tree/table
and rule panes, and the action area owns progress/preset/apply controls. Scanning,
preview generations, mutation results and cooperative close stay on the widget.

The action area names rule/preview control construction and preset-menu binding
separately from footer layout. `_show_plan` keeps generation admission, signal and
scroll guards, status and preview publication; `_project_plan_rows` only projects
the admitted plan into retained rows while those guards are held.

## Shared engine boundary

The Logistics widget imports planning, apply and undo from
`commonUtils.filesystem.rename` and candidate traversal from
`commonUtils.filesystem.traversal`. Shared engine APIs and transaction mechanics
belong in commonUtils' own documentation; see the
[commonUtils integration boundary](../../../development/commonutils-integration.md).
Logistics owns rule controls in `rules.py`, worker/UI coordination in `widget.py`,
preview rendering in `preview.py`, menus in `menus.py`, and host/window lifetime
in `__init__.py`. There is no local `renameUtils.py` engine.

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

## Platform and validation scope

This is a Qt desktop integration; it has no Android/iOS registration in
`Python/services/mobile_features.py`. See [mobile availability](../user_mobile/user_mobile.md).

`Python/tests/files/test_bulk_rename_ui.py` covers rule reflow, preset admission,
preview generations and cancellation, selected-path scope, apply/undo, stale
sources, tree reveal and cooperative close. `test_bulk_rename_host.py` covers
retaining one hosted page and replacing its selection while preserving rules.
These are test coverage descriptions, not a new GUI acceptance result. This
documentation audit used source/test review and static checks only; desktop UI
and filesystem transaction tests were not rerun under the release quiet hold.
