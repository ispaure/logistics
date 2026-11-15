# Remote transfers on mobile

## Pull and push managed folders

In **Workspaces**, use an online folder's **••• → Pull…** to create or refresh
its on-device copy. Use a managed copy's **••• → Push…** to update the remote.
Both use rclone Sync.
Destination files and empty folders can be replaced or deleted without a backup.
One transfer runs at a time. Existing local copies stay available for browsing.

Tap the sync progress ring on a main tab to reopen details. **Scan → Transfer →
Verify** shows the phase. The endpoint strip shows **From** and **To** paths.
Percentages use known bytes or file counts. Removal counts describe attempts.
Completion appears after verification. **Continue browsing** keeps the job
active. **Stop transfer** asks before cancellation. Completed changes remain
after a failure or stop.

### Choose storage on the first pull

For a new copy from a session-only crypt remote, the **Use an encrypted copy
(recommended)?** prompt offers **Yes** to keep the encrypted names and bytes
in LocalCrypt or **No** for a decrypted Local copy.
Both persist on disk. New copies from saved credentials or non-crypt remotes
use Local. Later pulls keep the existing copy's location and storage type.
If several mappings match, choose the intended copy before reviewing the
transfer. See [unlock and use a LocalCrypt copy](localcrypt.md).

### Review file changes

Check **New files**, **Updated files**, **Delete from destination** and any
**Local cleanup**. Use search and pages to inspect paths. Choose **Push N
changes** or **Pull N changes** and confirm. A changed comparison needs another
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
encrypted names and bytes. Use transfer details to follow or cancel the download.

## Restore access to a managed copy

Forgetting a package preserves its downloaded files. A replacement ZIP can
have a different name or password. Reopening LocalCrypt requires matching
crypt settings. Push and Pull also require the original destination account.
See [credential packages](connections.md#locked-credentials-and-workspaces).
