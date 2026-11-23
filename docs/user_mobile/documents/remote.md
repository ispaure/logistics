# Remote and offline files

When a file is online, you can open it to read or put a separate copy on the
device to edit. For example, you can preview a Markdown file on a NAS from
**Workspaces**, download it to keep a one-time copy, or pull its folder as a
managed copy if you want to sync changes back later.

To reach the online file, add a [credential
ZIP](../../features/rclone/user_mobile/connections.md#remote-files-and-credential-zips)
for **Cloud → Rclone Remotes**, or add an [SMB
share](../../features/rclone/user_mobile/connections.md#smb-and-mac-shared-folders)
through **Server**.

## Direct reading

On a streaming connection, tap a supported file to open a read-only view of
it. The preview uses the connection and leaves the online file in place.
Reopen the reader to refresh the snapshot. Locking or replacing credentials
closes associated private readers.

Text, Markdown and INI previews accept up to 1 MiB. PNG, JPEG and WebP accept
up to 16 MiB. The remote EPUB and CBZ/ZIP preview cache allows 128 MiB per
archive and 128 MiB total. Close a reader to free its cache. Separate limits
apply to [PDF](../../features/pdf/user_mobile/user_mobile.md) and
[video](../../features/video/user_mobile/user_mobile.md).

For a password-protected archive, the closest parent folder with a
`[LogisticsZIP]` section in `remoteConfig.ini` supplies `archive_password`.
A missing or empty key in that section stops inheritance. Enter the archive
password when prompted.

## Offline folders

Use [Download locally…](../../features/rclone/user_mobile/workflows.md#download-a-file-or-folder)
for a one-time copy. For a whole folder you plan to sync again, use
[Pull…](../../features/rclone/user_mobile/workflows.md#pull-and-push-managed-folders)
to create or update a managed copy. Once the transfer completes, the
saved files are on the device and can be used while the server is down.

Open **Local → Rclone Copies** and choose the copy you want to browse.
A **Local Copy** keeps readable files on the device. An **Encrypted Copy**
uses **LocalCrypt** and requires the matching credential to open or edit.
**Save** in an encrypted copy keeps the file encrypted. Moving or exporting
the contents to ordinary storage makes a readable copy there. See
[using LocalCrypt](../../features/rclone/user_mobile/localcrypt.md) for
unlocking, saving and the limits on private recovery.

Saving an edit in a managed copy changes the device copy. To publish the
change, review **Push…** with that folder as the source. A sync can replace
destination files and delete destination items that are absent from the source.
The [transfer guide](../../features/rclone/user_mobile/workflows.md) shows
how to check both paths and read the proposed changes.

If you once imported a book or comic and its original is missing, use
**Show cached copy in folder** to find the retained import.
