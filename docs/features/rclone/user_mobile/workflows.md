# Remote transfers on mobile

## Pull and push managed folders

In **Workspaces**, use an online folder's **••• → Pull…** to create or refresh
its on-device copy. Use a managed copy's **••• → Push…** to update the remote.
Both use rclone Sync.
Destination files and empty folders can be replaced or deleted without a backup.
Rclone removes destination-only files after transfers succeed. Replacements
free the old file's space as each new copy takes its place.
One transfer runs at a time. Existing local copies stay available for browsing.
Files copied to the destination by another tool can appear as replacements
if their modification times differ. Without a shared checksum, a timestamp
difference can trigger a full copy even if the file contents are identical.
A readable Pull to an Android FAT or exFAT card accepts matching file sizes
and modification times within one second. Up to ten files can stage in
parallel as available space permits, with a 16 MiB free-space margin.
Review another Pull after resolving a space error.

Tap the **Transfers** icon next to **Server** in Workspaces. The overview
shows the active transfer above interrupted downloads and completed transfers.
Tap the active card for its source, destination, MB/s, and the progress of
each file currently copying. Scroll to see all active files. On Android, a
file with a known size shows its progress bar next to the copied-size text
when the panel has room. The file and byte
totals can grow while rclone compares more of the source with the destination.
Percentages use the work found so far. Removal counters show attempts.
Resumable downloads show **Verified on disk** after copying. A finished
folder is published once it passes verification.

**Back** and **Continue browsing** return to the screen that opened the details.
If you started a transfer in the File Browser, they return to that folder.
**Stop transfer** asks before cancellation. Completed changes remain after
a failure or stop.

Workspaces source tabs and local folders stay usable during a transfer.
Opening an online workspace that shares the connection can wait until the
transfer ends. Its status page offers **View transfers**.

When a managed sync or download runs for at least 30 seconds and you are away
from its progress view, an in-app banner can open the transfer details.
For a failed or incomplete transfer, review what changed before retrying.
Short jobs and cancellations report their outcome in **Transfers**.

Turn on **Settings → Workspaces → Background transfer notifications** to get
generic system notifications while the app is in the background. Android and iOS
apply their own permissions and notification settings. If a result is ready and
system delivery is unavailable, Logistics shows the banner when you return.
The sync shortcut also keeps the latest eligible result available. Notification
text omits filenames, paths, connection names and error output. Unlock a
protected connection in Logistics to review its details. Android and iOS can
suspend or stop the app. A notification does not grant background execution
time, and interrupted downloads may require recovery.

### Choose storage on the first pull

For a new copy from a session-only crypt remote, the **Use an encrypted copy
(recommended)?** prompt offers **Yes** to keep the encrypted names and bytes
in LocalCrypt or **No** for a decrypted Local copy.
Both persist on disk. New copies from saved credentials or non-crypt remotes
use Local. Later pulls keep the existing copy's location and storage type.
If several mappings match, choose the intended copy before reviewing the
transfer. See [unlock and use a LocalCrypt copy](localcrypt.md).

### Review file changes

Check the totals for additions, replacements, deletions and empty folders.
Filter by change type, search or page through the paths. Choose **Start push**
or **Start pull** and confirm. A changed comparison needs another
confirmation. **Skip preview and start** begins sync without waiting for the
comparison to finish. Storage access and filesystem link checks still apply.
The transfer can replace or delete more files than the preview lists. Back
cancels review before sync starts.

## Download a file or folder

Use **••• → Download locally…** on a remote file or folder. Choose **On My
Phone / On My Tablet**, an available local copy or an unlocked LocalCrypt
location. Choose the destination folder and an unused name, then **Download
here**. Confirm when choosing a decrypted destination. The action downloads
only that selection and creates no recurring mapping. LocalCrypt writes
encrypted names and bytes. Use transfer details to follow or cancel the
download. The destination listing updates after the item is saved. You can
keep browsing the folder without reopening it.

## Transfer history and interrupted downloads

Open **Workspaces → Transfers**. The panel shows the current transfer,
up to 60 recent completed transfers recorded by the app, and interrupted
downloads with a verified checkpoint. A stopped download can appear here after you relaunch.
Choose **Resume** to check the saved bytes and fetch any remainder, or
**Discard** to remove that job and its verified partial data. If the app
can no longer verify the destination folder, you can remove the saved entry
from Transfers and leave the partial data in place. The destination listing
refreshes when the verified item is published.

Unlock the original connection to see its interrupted downloads. Completed
transfers from a password-protected session-only connection also stay hidden
while it is locked. **Clear history…** clears the visible completed history
without deleting completed files or interrupted downloads.

Single-file recovery applies to files of at least 8 MiB when the source can
provide verifiable byte ranges. Files of 100 GB or larger use the same range
mechanism and require room for the remaining bytes. A changed source or partial
needs inspection before recovery.

A selected folder can also resume to ordinary on-device storage when all its
files support verified ranges. Up to ten files can copy in parallel. If a
download stops, Logistics keeps the verified progress of each file in staging.
To copy one file at a time and keep resume available, turn off **Parallel folder
downloads** in **Settings → rclone**. The setting applies when you start or
resume a download. The complete folder becomes visible after verification. A leftover
`.download-…` staging folder from a one-shot download has no resume checkpoint.

A crypt source can resume into ordinary storage or into its own LocalCrypt
destination. A destination that needs a fresh encryption stream, or a server
without a usable content version, offers **Download from byte zero?** before
starting the full copy.

## Restore access to a managed copy

Forgetting a package preserves its downloaded files. A replacement ZIP can
have a different name or password. Reopening LocalCrypt requires matching
crypt settings. Push and Pull also require the original destination account.
See [credential packages](connections.md#locked-credentials-and-workspaces).
