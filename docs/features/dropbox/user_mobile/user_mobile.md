# Dropbox on mobile

The desktop Dropbox feature detects folders from an installed Dropbox client
and reviews conflicting copies. That source picker and cleanup dialog are not
implemented in the Android or iOS app.

To access a Dropbox account through a configured rclone remote, use
[rclone mobile connections](../../rclone/user_mobile/connections.md). This uses
rclone credentials and remote browsing; it does not discover the Dropbox app’s
local account folders or run the desktop conflict cleanup. For managed offline
copies and reviewed Push/Pull, see
[mobile transfers](../../rclone/user_mobile/workflows.md).

For local Dropbox conflict maintenance on a computer, see the
[desktop guide](../user/user.md).
