# Remote and offline files

Add a connection in **Settings → Workspaces → rclone connections…**, then open
it from Workspaces or Remote files.

## Direct reading

Tap a supported file on a streaming connection. Readers open it read-only in
memory. Text, Markdown, and INI support up to 1 MiB, and PNG, JPEG, and WebP
support up to 16 MiB. Size and format limits also apply to
[EPUB and comic archives](../../features/rclone/user_mobile/connections.md#remote-files-and-credential-zips),
[PDF](../../features/pdf/user_mobile/user_mobile.md), and
[video](../../features/video/user_mobile/user_mobile.md). Locking or replacing
credentials closes the associated private readers.

## Offline folders

Choose **••• → Download locally…**, then select a folder and name and tap
**Download here**. Pick an unused name. Ordinary destinations require confirmation
because decrypted files remain readable after you lock the connection.
For a managed Local or LocalCrypt folder, use **Pull** in Workspaces and review
the transfer before applying. Offline copies remain available when the remote
is down. To find a retained book or comic import when its source is missing,
use **Show cached copy in folder**.
See [remote workflows](../../features/rclone/user_mobile/workflows.md#mobile-folder-navigation)
or [Documents and readers](documents.md).
