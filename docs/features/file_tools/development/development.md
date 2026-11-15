# File Tools development

File Tools adds bounded inspection and cleanup actions to the desktop browser.
Scanning produces reviewable results; deletion is a separate operation that
revalidates the selected files.

## Trace a filename scan

In File Browser, choose **List Weird Characters… → Scan files** for a disposable
folder containing `note-é.txt`. `ui/dialogs.py:WeirdCharactersDialog._show_results`
presents the matches from `filesystem.py`, which checks full paths and skips
directory links. The fixtures verify the Unicode result and preserved files:

```sh
python3 dev.py test desktop --exact-file Python/tests/files/test_file_tools.py
```

## Reviewed deletion boundary

`DeletePycDialog` passes the scanned snapshot to `cleanup_pyc_files` only after confirmation (**No** by default). Scope changes invalidate review. The older `delete_pyc_files` helper deletes immediately. Scan and cleanup enforce `maintenance.ini` protected roots. Cleanup rechecks scope, symlink parents and file identity before unlink. New files stay outside the snapshot. Concurrent changes can still race the unlink. Cancellation stops between files. Rescan after partial failure. See [desktop workflows](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
