# File Tools development

File Tools adds path diagnostics and reviewed bytecode cleanup to the desktop
File Browser. See the [user guide](../user/user.md) for the two workflows.

## Try a scan summary change

On Qt desktop, open **File Browser** and right-click a disposable folder
containing a file such as `note-é.txt`. Choose **List Weird Characters…**
and click **Scan files**. The dialog lists the path, matched sequence and
Unicode code points. Enable **File Tools** in **Settings → Features** if the
action is missing.

Try changing `Found` to `Matched` in the summary built by
`WeirdCharactersDialog._show_results` in
`Python/features/file_tools/ui/dialogs.py`. Update the summary assertion in
`test_scan_window_keeps_results_and_unicode_visible`, then run this from the
repository root using the [desktop environment](../../../development/getting-started.md).

```sh
python3 dev.py test desktop --exact-file Python/tests/files/test_file_tools.py
```

Expect the synthetic scan to leave the dialog open with one result, the
`U+00E9` code point and a summary beginning with `Matched 1`. The fixture
file remains present. The same test file checks the folder menu and feature
toggle, reviewed deletion, and cancellation.

## Registration and path matching

`Python/features/file_tools/__init__.py:register` loads the feature declaration
from `ui_contributions.py`. Both actions require a folder selection and pass
the selected roots to their dialogs. The contribution refreshes the browser
when the dialog returns. See the shared
[browser extension contract](../../../development/file-browser.md).

`filesystem.py:scan_weird_characters` matches the original Logistics
`WEIRD_CHARACTERS` set anywhere in the full path, including parent-folder
names. The set includes precomposed and combining representations of some
characters. The scan matches literal sequences and reports code points so
readers can distinguish visually identical names. It reads paths without
following directory links.

## Reviewed deletion boundary

`DeletePycDialog` calls `scan_pyc_files` to capture a read-only snapshot
of regular bytecode files. It passes that snapshot to `cleanup_pyc_files`
after explicit confirmation, with **No** as the default. Changing roots or
recursion invalidates the preview. Preserve this handoff when editing the dialog.
The older `delete_pyc_files` helper uses a separate immediate-delete path.

Both scan and cleanup call `services.folders.safety.require_safe_folder`.
The policy in `Python/maintenance.ini` rejects protected roots and descendants
and rejects recursive scans of their ancestors. Scans deduplicate paths and
skip links. Before unlinking, cleanup rechecks scope, symlink parents and the
file's device, inode, size, nanosecond modification time and mode. A file added
after preview stays outside the snapshot. The identity check catches changes
observed before deletion. Concurrent changes can still race the unlink.

Cleanup continues after an individual failure and reports completed, failed
and unprocessed paths. Cancellation takes effect between files. Completed
deletions stay deleted. Rescan after correcting a failure or changing the scope.

## Platform and validation scope

File Tools supplies desktop browser actions. See
[mobile availability](../user_mobile/user_mobile.md) for Android and iOS.
Use disposable files for cleanup tests, including for link and race scenarios.
