# File Tools development

## Try a scan summary change

In desktop File Browser, right-click a disposable folder containing `note-é.txt`. Choose **List Weird Characters… → Scan files**. Change `Found` to `Matched` in `Python/features/file_tools/ui/dialogs.py:WeirdCharactersDialog._show_results` and update the summary assertion. Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/files/test_file_tools.py
```

Expect `Matched 1`, `U+00E9`, and the unchanged fixture file. `filesystem.py` matches literal sequences across the full path and skips directory links.

## Reviewed deletion boundary

`DeletePycDialog` passes the scanned snapshot to `cleanup_pyc_files` only after confirmation (**No** by default). Scope changes invalidate review. The older `delete_pyc_files` helper deletes immediately. Scan and cleanup enforce `maintenance.ini` protected roots. Cleanup rechecks scope, symlink parents and file identity before unlink. New files stay outside the snapshot. Concurrent changes can still race the unlink. Cancellation stops between files. Rescan after partial failure. See [desktop workflows](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
