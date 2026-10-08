# Back up and restore Plex server data

Manage PMS is offered on **Folders** when a local folder has a matching
`<folder>-PMSDATA` rclone remote. Load credentials using [rclone](../../rclone/user_docs/index.md).

## Back up

1. Stop Plex Media Server.
2. Select the paired folder and open **Manage PMS…**.
3. Package the current server data locally.
4. Push the completed package to the paired remote if desired.

## Restore

1. Stop Plex Media Server and keep a backup of the existing installation.
2. Pull the desired package locally if needed.
3. Unpack it through Manage PMS.
4. Check the restored server before removing any recovery copy.

| Platform | Package |
| --- | --- |
| Windows | Split 7-Zip archive plus registry settings; supplied 7-Zip required |
| macOS | ZIP plus server preferences plist |
| Linux | ZIP; filesystem permissions and service ownership may need attention |

Restore retains previous data beside the restored directory as
`Plex Media Server.previous-<id>`. Staging and that copy need extra disk space.
Preferences/registry changes and data replacement are separate operations, so a
failure may leave a partial update. Packaging a running server cannot guarantee a
consistent database backup.

## Compare database copies

**Debug → Plex - Compare Databases…** asks for two database files and compares
supported movie/episode records. Use database copies; this tool does not restore
a live server or synchronize the libraries.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
