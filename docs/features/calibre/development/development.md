# Calibre library and export development

Calibre launches desktop libraries and mirrors books. See the [desktop guide](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).

## Try an export filename change

On desktop, open **Workspaces → Calibre → Export books… → Review export** with a disposable library (a `metadata.db` marker and author/book folders containing an EPUB and OPF) and empty destination. In `Python/features/calibre/metadata.py:get_metadata_book_name()`, try “Volume” for “Vol.” Update `test_metadata_series_and_existing_volume_are_not_duplicated`. From the checkout root:

```sh
python3 dev.py test desktop --exact-file Python/tests/calibre/test_calibre.py
```

Expect `Series - Title - Volume 5` for index `5.00`, with one volume label if the title already contains it.

## Discovery and publication

`detection.py` scans immediate Local children for `metadata.db`. `launching.py` owns native/Flatpak Linux, bundled Windows and install/launch macOS paths.

`export.py` plans a one-way mirror of existing formats. Review rejects overlapping paths, links and equivalent names. Missing or malformed OPF falls back to a sanitized folder name. Apply rechecks revisions and needs space to stage all changed copies before atomic per-file replacement and pruning, including obsolete files of other extensions. Stage failure preserves the export. Interrupted publication can leave a partial mirror. Reconnect or fix the destination and review again. **Echo EPUBs to BOOX-SD** prefills the mounted path. Mounted export and Calibre launch require local acceptance.
