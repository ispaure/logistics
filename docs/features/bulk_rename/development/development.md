# Bulk rename integration

Bulk Rename separates rule evaluation and preview from applying filesystem
changes. Its desktop host lives under `Python/desktop/bulk_rename/`; shared
rename mechanics remain in commonUtils.

## Follow a rule into the preview

Select a disposable `page2.txt` in **Bulk Rename** and enter `New_` under
**Add → Prefix**. Preview should show `New_page2.txt` while the file stays
unchanged. `preview.py:change_formats` marks changed spans using UTF-16 offsets.
The UI fixtures check those spans, including emoji, and the surrounding controls:

```sh
python3 dev.py test desktop --exact-file Python/tests/files/test_bulk_rename_ui.py
```

## Host and use

The rail and File Browser use the same retained desktop page via `open_bulk_rename(paths=...)`. New requests keep rules and filters. Apply or undo retires before loading a replacement selection. Check `test_bulk_rename_host.py`.

```sh
PYTHONPATH=Python python -m desktop.bulk_rename /path/to/folder
PYTHONPATH=Python python -m desktop.bulk_rename --paths /path/to/a.jpg /path/to/b.jpg
```

On Windows, set `PYTHONPATH` with your shell. Embedders can instantiate `BulkRenameWidget(path, parent=...)` and refresh on `renamed`. Call `can_close()` and retry on `idle` so workers can finish rollback.

`widget.py` handles scan, preview and disk batch results separately. A successful
scan fills the table and schedules a preview. A preview can publish only if its
generation is current. Apply and undo share batch result handling and use the
[commonUtils engine](../../../development/architecture/commonutils-integration.md)
to validate sources and destinations. A successful apply retains the undo receipt
for that batch in the current session; a successful undo clears it. A completed
rollback leaves the existing receipt available. If rollback is incomplete, the
widget clears the receipt and reports the staged and original paths. See
[recovery](../user/user.md#applying-cancelling-and-undo) and
[mobile availability](../user_mobile/user_mobile.md).

After handling the result, the widget starts a queued input replacement without
emitting `idle` between jobs. Otherwise it schedules any pending preview, updates
the actions and emits `idle` before retrying a waiting close.
