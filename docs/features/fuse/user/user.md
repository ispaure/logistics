# Open a mounted remote folder

## Open a mount

Persist [rclone credentials](../../rclone/user/user.md), select the remote in
**Workspaces** and choose **Open Mount Folder**. Install macFUSE on macOS,
WinFsp on Windows, or FUSE with `fusermount`/`fusermount3` on Linux.
Mounts default to `~/Server/NetworkMount/<config-id>/<remote>`.
Edits there affect remote storage.

## If a mount fails

Check connection, credentials and the driver. Nonempty and linked destinations
are refused. Unix retries stale mounts after unmounting successfully.

## More help

See [Using Logistics](../../../user/user.md) and [mobile scope](../user_mobile/user_mobile.md).

## Credential changes and existing mounts

If credentials changed or Logistics restarted with a mount left active, unmount
it using platform tools and retry. Cancelling can leave a completed mount active.
