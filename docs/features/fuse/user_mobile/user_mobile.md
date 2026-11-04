# FUSE on mobile

The Android and iOS app does not mount rclone remotes as filesystem folders.
macFUSE, WinFsp and the desktop **Open Mount Folder** action apply to desktop
Logistics only.

Use [rclone mobile connections](../../rclone/user_mobile/connections.md) to browse
online files, or [mobile transfers](../../rclone/user_mobile/workflows.md) to
create and update Local or LocalCrypt copies. These workflows use the embedded
rclone bridge and do not require a FUSE driver.

See [desktop mounting](../user/user.md) for supported desktop platforms and
mount prerequisites.
