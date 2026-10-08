# Open a mounted remote folder

FUSE lets rclone expose a remote as a local folder. It requires a loaded rclone
config and the platform's filesystem support.

## Open a mount

1. Load credentials using the [rclone guide](../../rclone/user_docs/index.md).
2. Select the remote on **Folders**.
3. Choose **Open Mount Folder** in its FUSE section.
4. If asked, download the required rclone executable or platform driver installer.
   Complete driver installation, then retry the mount action.

| Platform | Filesystem support |
| --- | --- |
| macOS | macFUSE; a pinned installer can be downloaded |
| Windows | WinFsp; a pinned installer can be downloaded |
| Linux | FUSE device plus `fusermount`/`fusermount3`, installed through your distribution |

Opening a folder source alone does not mount or contact its remotes. Mounts are
created on demand under `~/Server/NetworkMount/<remote>` by default.

## If a mount fails

Read the reported error and check the credential config, connectivity and installed
filesystem support. On Unix, an unresponsive mount is unmounted before retrying;
a failed unmount stops recovery. Automatic stale-mount recovery on Windows is not
supported. A nonempty or linked mount destination is refused rather than cleared.

Remotes with identical names share a mount path even across credential configs.
Make sure the opened mount belongs to the account you intend to use. Ordinary
push/pull transfers can work without FUSE.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
