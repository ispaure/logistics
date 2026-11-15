# Remote and offline files

Add a [credential ZIP](../../features/rclone/user_mobile/connections.md#remote-files-and-credential-zips)
or an [SMB share](../../features/rclone/user_mobile/connections.md#smb-and-mac-shared-folders),
then open it from Workspaces.

## Direct reading

Tap a supported file on a streaming connection. Readers open it read-only in
memory. Text, Markdown, and INI support up to 1 MiB, and PNG, JPEG, and WebP
support up to 16 MiB. The remote EPUB and CBZ/ZIP preview cache holds up to
128 MiB total, with a 128 MiB limit per archive. Close a reader to free its
cache or reopen it to refresh its snapshot. Separate limits apply to
[PDF](../../features/pdf/user_mobile/user_mobile.md) and
[video](../../features/video/user_mobile/user_mobile.md). Locking or replacing
credentials closes the associated private readers.

For a password-protected archive, the closest `[LogisticsZIP]` section in a
parent `remoteConfig.ini` supplies `archive_password`. A missing or empty key
in that section stops inheritance. Enter the archive password when prompted.

## Offline folders

Use [Download locally…](../../features/rclone/user_mobile/workflows.md#download-a-file-or-folder)
for a one-time copy or [Pull…](../../features/rclone/user_mobile/workflows.md#pull-and-push-managed-folders)
for a managed folder you can sync again. Offline copies remain available when
the remote is down. To find a retained book or comic import when its source is
missing, use **Show cached copy in folder**.
