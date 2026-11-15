# Choose a location, save confidently and recover

Before editing, check where the document lives. If you open an ordinary file
from [File Browser](files-and-documents.md) or mobile **On My Phone / On My
Tablet**, saving a folder-backed document updates that file. A file opened
from a remote or Cloud browser is a read-only preview. To edit it, first
make a copy on your device.

## Choose the source that matches your task

If you just need one editable file, download it. If you plan to work on
several files and send changes back together, use a managed copy from
Workspaces. A **Local** copy keeps readable files on your device after you
lock its credentials. A **LocalCrypt** copy keeps the files encrypted and
requires the matching credentials to open them. Saving there keeps the
contents encrypted. Save or discard private drafts before locking because
ordinary recovery does not keep those drafts.

See the [desktop folder guide](files-and-documents.md#find-a-configured-integration)
or [mobile remote and offline guide](../user_mobile/documents/remote.md) to
find those locations in the app.

## Know when you are making a copy

Importing or receiving a shared attachment creates a new file in Logistics.
The source remains in the sending app. **Export** writes a separate copy.
**Save As** lets you choose a new storage location and name for the current
document. Check the editor guide for which file stays open afterward. In
Notebooks, **Save As** opens the resulting file in the editor, while
**Export .rmdoc** writes a copy you can share.

Moving private content to ordinary storage decrypts the destination. Read
the confirmation before completing the move. Saving a private document in
LocalCrypt keeps it subject to private Recent, history and recovery rules.
For details about private reading positions and history, see [reader
history](reader-history.md).

## Review transfers before changing the remote

**Pull** uses the selected online folder as its source and updates the
offline copy. **Push** uses the managed local folder as the source and
updates the online folder. Finish your edits, then check both endpoints in
the review. Same-named Local and LocalCrypt copies can point to different
locations. Both sync directions can replace or remove files from the
destination.

If a transfer stops, check its status and the affected files before retrying.
Completed changes may still be present. Keep the original and your draft
until you verify the result. See [desktop
transfers](../features/rclone/user/user.md#transfer-files) or [mobile
transfers](../features/rclone/user_mobile/workflows.md) to review and run
the transfer.

## Recover without overwriting the version you need

| If this happens | What to do |
| --- | --- |
| Save reports an external change | Keep the draft open. Inspect the current file, then use Save As or export to preserve a second version. |
| A save completed and the editor failed to reopen | Inspect the destination before retrying. Keep the draft and the visible error. |
| The file appears in its folder and search misses it | Check the search scope, index progress and errors. Refresh the index where offered. |
| A LocalCrypt file disappears after locking | Unlock the matching credentials and reopen the file. |
| An incoming share is unavailable on Android | Check whether the selected drive is connected. Completed handoffs can wait for it. |
| A remote preview offers no Save | Download an editable copy, or use a managed copy and review Push to publish the changes. |

Keep the app open while protecting an unsaved draft. If you report a problem,
include the platform, build, location type, operation and error without
sharing credentials or private content.

Return to [Using Logistics on desktop](user.md) or follow the [mobile
document workflows](../user_mobile/documents/workflows.md) to save, move
or recover an individual document.
