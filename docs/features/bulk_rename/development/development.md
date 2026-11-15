# Bulk rename integration

## Try a preview styling change

In desktop **Bulk Rename**, select a disposable `page2.txt` and enter `New_` under **Add → Prefix**. In `Python/desktop/bulk_rename/preview.py:change_formats`, switch bold to underline. Keep UTF-16 offsets and update `test_preview_bolds_changed_spans_and_prioritizes_filename_columns`. Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/files/test_bulk_rename_ui.py
```

Expect `New_page2.txt` with the changed span underlined, including in the emoji fixture. Preview leaves the file in place.

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
