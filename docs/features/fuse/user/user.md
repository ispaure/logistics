# Open a mounted remote folder

FUSE lets rclone expose a remote as a local folder. It requires a loaded rclone
config and the platform's filesystem support.

## Open a mount

1. Load credentials using the [rclone guide](../../rclone/user/user.md).
2. Select the remote on **Workspaces**.
3. Choose **Open Mount Folder** in its FUSE section.
4. If asked, download the required rclone executable or platform driver installer.
   Complete driver installation, then retry the mount action.

| Platform | Filesystem support |
| --- | --- |
| macOS | macFUSE; a pinned installer can be downloaded |
| Windows | WinFsp; a pinned installer can be downloaded |
| Linux | FUSE device plus `fusermount`/`fusermount3`, installed through your distribution |

Opening a folder source alone does not mount or contact its remotes. Mounts are
created on demand under `~/Server/NetworkMount/<config-id>/<remote>` by default.
The config ID is derived from the credential config's resolved path. Moving the
config therefore changes its mount location.

## If a mount fails

Read the reported error and check the credential config, connectivity and installed
filesystem support. On Unix, an unresponsive mount is unmounted before retrying;
a failed unmount stops recovery. Automatic stale-mount recovery on Windows is not
supported. A nonempty or linked mount destination is refused rather than cleared.

Different credential configs have separate mount locations even when remote names
match. This separation applies to mounts; rclone Push/Pull still uses the same
local folder for same-named remotes. Ordinary transfers can work without FUSE.

## More help

See [Using Logistics](../../../user/user.md) for navigation and settings.

Mount attempts show a progress dialog. Close/cancel waits for the current attempt;
an already completed mount remains mounted. Disabling the feature does not unmount
an existing remote. Changes made through the mounted folder affect its remote
storage; it is not a separate backup copy.
