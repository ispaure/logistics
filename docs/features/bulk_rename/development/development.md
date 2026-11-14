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

`widget.py` accepts only the current preview generation. The [commonUtils engine](../../../development/architecture/commonutils-integration.md) validates apply and undo. Report stale sources or occupied destinations. On rollback failure, preserve and report staged and original paths. Undo covers the last successful batch in the current session. See [recovery](../user/user.md#applying-cancelling-and-undo) and [mobile availability](../user_mobile/user_mobile.md).
