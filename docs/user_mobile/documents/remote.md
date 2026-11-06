# Remote and offline files

Configure remote connections from **Settings → Workspaces → rclone connections…**. Browse a
connection from Workspaces or Remote files, then tap a supported document.

## Direct reading

Tap a file to open it from the current folder. Folder search filters that folder only.
Direct opening requires a connection that supports streaming.

- Text, Markdown and INI previews support up to 1 MiB. PNG/JPEG/WebP previews
  support up to 16 MiB.
- EPUB books and CBZ/ZIP comics load into memory within the
  [remote archive limits](../../features/rclone/user_mobile/connections.md#remote-files-and-credential-zips).
- PDFs open in the [Mobile PDF Reader](../../features/pdf/user_mobile/user_mobile.md),
  subject to its size, page and document restrictions.
- Recognized video file extensions can open in the
  [Mobile Video Player](../../features/video/user_mobile/user_mobile.md).
  Playback and seeking depend on the platform's decoder, the file's codecs,
  the provider's range support and network throughput. See the player guide
  for the scope of platform and device testing.

Direct readers open the source read-only, with file contents held or buffered
in memory. Reader position can be stored separately according to the reader's
privacy rules. Locking or replacing credentials retires the associated private
reader contents, including for session-only credentials.

When a file is unsupported or exceeds a direct reader limit, make a
[local copy](#offline-folders) and open it yourself. Opening a remote file
never automatically creates an offline copy.

## Offline folders

For one file or folder, use its **••• → Download locally…** menu. Choose the
destination folder and name, then **Download here**. Existing names are rejected;
an ordinary destination needs confirmation because its decrypted contents remain
readable after locking the connection. See the
[remote workflow](../../features/rclone/user_mobile/workflows.md#mobile-folder-navigation).

Use Workspaces's managed Pull workflow to keep files in a Local or LocalCrypt
folder. Review the proposed transfer before applying it. Existing offline copies
remain readable and exportable when the remote is unavailable.

A retained book/comic import, a managed folder and a temporary remote preview are
stored separately. Retained imports are private reading copies. From a retained
reader, **Show cached copy in folder** locates its import when the source path
is unavailable.

[Back to documents](documents.md).
