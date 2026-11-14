# Bulk rename integration

Bulk Rename previews and applies filename changes on Qt desktop. See the
[user guide](../user/user.md) for rules, apply, undo and recovery.

## Try a preview styling change

Open **Bulk Rename** from the desktop navigation rail. Choose a disposable
folder with one file named `page2.txt`, then enter `New_` in **Add → Prefix**.
The proposed name becomes `New_page2.txt`, with the new prefix in bold. Use
the preview to inspect the change before applying it.

To try a different emphasis, switch from bold to underlined text in
`change_formats` in `Python/desktop/bulk_rename/preview.py`. This function
supplies Qt text formats to `RenamePreviewDelegate.paint`. Keep the UTF-16
offset conversion so matches after emoji stay aligned. Update the font
assertion in `test_preview_bolds_changed_spans_and_prioritizes_filename_columns`
to check the underline.

Run this from the repository root using the
[desktop environment](../../../development/setup/getting-started.md).

```sh
python3 dev.py test desktop --exact-file Python/tests/files/test_bulk_rename_ui.py
```

Expect the synthetic preview to mark the changed character after an emoji and
show the prefixed name while leaving the original file in place. The test file
also covers background apply and undo, stale previews, presets, scope and close.

## Main-window hosting

The rail's `bulk_rename` destination is declared in
`Python/desktop/navigation/catalog.py`. `MainWindow._show_bulk_rename` in
`Python/desktop/main_window.py` opens the single retained page.
`Python/desktop/file_browser.py` installs the same tool's
`bulk_rename_actions` provider for File Browser selections. That provider calls
`open_bulk_rename(paths=...)`, which forwards to the registered main-window host.

A new browser request replaces the page's candidates and retains rules and
filters. During scans or previews, the latest request wins. An active apply
or undo finishes before the replacement selection loads. The host regression
uses a real main window with a synthetic selection and checks that the same
page remains active with the new selection, existing rules and filter.

```sh
python3 dev.py test desktop --exact-file Python/tests/files/test_bulk_rename_host.py
```

## Embed or launch from a button

From the Logistics root with its desktop environment active, these commands
open a standalone window for a directory or a supplied selection. On Windows,
set `PYTHONPATH=Python` using the shell's environment syntax before invoking
the module.

```sh
PYTHONPATH=Python python -m desktop.bulk_rename /path/to/folder
PYTHONPATH=Python python -m desktop.bulk_rename --paths /path/to/a.jpg /path/to/b.jpg
```

Applications with an existing QApplication can open the tool or embed
`BulkRenameWidget` in their own layout.

```python
from desktop.bulk_rename import BulkRenameWidget, open_bulk_rename

tool = open_bulk_rename(paths=selected_paths, parent=application_window)
widget = BulkRenameWidget('/path/to/library', parent=application_window)
layout.addWidget(widget)
widget.renamed.connect(lambda receipt: browser.refresh())
```

`open_bulk_rename` returns the hosted widget or a retained standalone window.
Use `standalone=True` to select the latter explicitly. `preview_ready` publishes
a `RenamePlan`, and `renamed` publishes a successful `RenameResult` after apply
or undo. The widget exposes `selected_paths()`, `load_directory(path)`,
`apply()` and `undo()`.

A standalone File Browser can opt in with
`FileBrowser('/path/to/library', action_providers=(bulk_rename_actions,))`,
importing `FileBrowser` from `commonUtils.ui.file_browser` and
`bulk_rename_actions` from `desktop.bulk_rename`. The provider limits candidates
to the selection and refreshes the browser after successful apply or undo.

An embedding host should call `widget.can_close()` before closing. Busy workers
receive a cancellation request. If close is deferred, retry on `widget.idle`.
The standalone window also defers a supplied parent's close while the worker
retires. This lets apply or undo finish rollback before the host is destroyed.

## Widget composition

Under `Python/desktop/bulk_rename/`, `rules.py` owns rule controls, `widget.py`
owns scanning, preview and worker state, `preview.py` owns filename rendering,
and `menus.py` owns the shared window menus. Widget construction separates
folder controls, browser and rule panes, and footer actions. Rule groups pack
into up to six vertical stacks while retaining control identities and values.
The browser/rules splitter starts with more space for rules, and narrow
windows keep a scroll area.

`_show_plan` only admits the current preview generation and owns the signal
and scroll guards. `_project_plan_rows` updates retained rows under those
guards. Keep proposed names as plain text when editing their appearance.

The folder tree retains its filesystem root while revealing the current folder.
Reveal fetches and expands unloaded ancestors root-first, including paths whose
model rows arrive after their parent's load signal. The retry waits for stable
visible geometry, including for empty folders. `_FolderTree` handles deferred
scroll correction for selections that were visible before layout changes,
including horizontally clipped deep rows. Preserve collapsed branches and
manual scrolling when adjusting that correction.

## Shared engine boundary

The widget calls `commonUtils.filesystem.rename` for planning, applying and
undoing batches, and `commonUtils.filesystem.traversal` for candidate discovery.
See the [commonUtils integration boundary](../../../development/architecture/commonutils-integration.md)
for where to change shared APIs. In Logistics, keep the apply action tied to a
fresh preview and show stale-source or occupied-destination errors to the user.

If an external change blocks rollback, retain and report the current staged
path and the original path. The [user recovery guide](../user/user.md#applying-cancelling-and-undo)
explains how to recover the staged file. The undo receipt lasts for the current
session and covers the last successful batch.

## Platform and validation scope

The host and action provider are desktop integrations. See
[mobile availability](../user_mobile/user_mobile.md) for Android and iOS.
