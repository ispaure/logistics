# Back up and restore Plex server data

Select the local folder and the credential owning its matching **-PMSDATA**
rclone remote in **Workspaces**. Choose **Manage PMS…**. See
[rclone setup](../../rclone/user/user.md) and [mobile availability](../user_mobile/user_mobile.md).

## Back up

Stop Plex Media Server, then package its data locally. Preserve earlier
packages before replacing them. If you Push, check the
[sync direction and deletions](../../rclone/user/user.md#choose-the-sync-scope).
Keep any reported recovery folder until the package is verified or
[recovery](../development/development.md#package-and-restore-behavior) finishes.

## Restore

Stop Plex, keep a backup, Pull the intended package if needed and unpack it in
**Manage PMS…**. Windows needs the supplied 7-Zip for split archives. macOS
packages include preferences, and Linux restores may need ownership or
permissions corrected. Verify Plex before deleting the previous data copy.
Preference or registry changes can succeed separately from data replacement.

## Compare database copies

Use **Debug → Plex - Compare Databases…** to compare two copies. It compares
supported movie and episode records.

## More help

See [Using Logistics](../../../user/user.md).
