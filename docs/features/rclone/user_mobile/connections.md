# Remote connections on mobile

## Remote files and credential ZIPs

1. Open **Settings → Workspaces → rclone connections… → Import credential ZIP…**
   and select **Choose credential ZIP…**. An unencrypted ZIP continues directly.
   For an encrypted ZIP, enter its password and tap **Unlock**. A failed password
   keeps the ZIP selected for retry.
2. Choose **Session-Only** to keep decoded credentials in memory until lock or
   exit, or **Persistent credential storage** to restore them after restart.
   Cancel leaves credentials unchanged.
3. Select a remote and **Browse folder**, or choose **Workspaces → Cloud** and
   use a folder’s **••• → Browse Remote**. Tap a supported file for read-only preview.

The ZIP supports plain, ZipCrypto and WinZip AES packages with one
`[Remote name]` and `type` per TXT entry. Limits are 1 MiB per ZIP, 64 entries
and 256 KiB per TXT. Duplicate remote names within a ZIP and unsafe paths are
rejected. Import/unlock works offline and keeps the source ZIP intact. If
credentials are busy, stop the active request and retry. **Advanced &
troubleshooting → Check rclone engine** runs an offline diagnostic.

Embedded rclone supports existing settings for Google Drive, Dropbox, OneDrive,
S3, WebDAV and SMB, plus one crypt layer over a supported remote. WebDAV and
custom S3 endpoints require HTTPS with certificate verification. Use a separate
form for [direct SMB shares](localcrypt.md#smb-and-mac-shared-folders).

**Session-Only** retains password-protected ZIPs under device encryption for
future unlocking. Re-select unencrypted ZIPs after restart. **Persistent**
protects decoded settings and refreshed tokens in an AES-256-GCM vault with an
Android Keystore or device-only iOS Keychain key, outside backup. ZIP passwords
stay in memory. Saved connections restore in the background. If restoration
fails, unlock the device and choose **Reload saved credentials**, or forget and
reimport. Session-only token refreshes may require a fresh package after exit.

The online browser keeps previews in memory. EPUBs and CBZ/ZIP comics use up to
128 MiB per archive and 256 MiB across open books/comics. Close a reader to free
its cache or reopen it for a fresh snapshot. If an inner ZIP needs a password,
the closest `[LogisticsZIP]` section in a parent `remoteConfig.ini`
supplies `archive_password`. A missing or empty key there stops inheritance.
Use the password form if needed.

**Cancel** requests a stop. Another online request can show **Cancel current
request**; local browsing remains available. Browsing has a two-minute deadline
and cancellation may wait for an upstream call. Use [Download locally…](workflows.md#mobile-folder-navigation)
for a selected copy, or [LocalCrypt](localcrypt.md#localcrypt-encrypted-offline-reading)
for managed encrypted copies.

### Locked credentials and Workspaces

Open a retained package under **Credential Packages** or tap a locked Cloud
folder and enter its ZIP password. **Session → Lock session** unloads active
rclone and SMB connections and keeps retained packages and local copies. Save
or discard private edits before locking.

**Forget this credential package** removes its credentials and encrypted
open/recent lists. **Advanced & troubleshooting → Forget all saved credentials**
removes all packages and their caches while preserving downloaded files.
If removal fails, unlock the device and retry. If locking cannot be confirmed,
restart the app before retrying.

### Multiple credential packages on Android and iOS

Choose storage separately for each ZIP. Up to 32 packages can stay loaded, with
up to 64 remotes each. A filename identifies its package. Reloading that file
only replaces that package’s active remotes. Matching remote names across
packages get qualifiers and keep their own account identities. Use **All** or a
credential group in Workspaces. **Show Legacy** controls Legacy entries.

Reloading saved credentials preserves active session packages. Importing a
previously saved filename as Session-Only keeps its older saved copy. Use
**Forget this credential package** to remove both. Password-protected session
packages keep encrypted open/recent paths under the ZIP password.

## Folder search scope

Remote and Home Server searches filter the current folder. Local and LocalCrypt
include subfolders. Scroll to see more results.

## Resuming a locked session

Enter the named ZIP passwords in turn, or the temporary password for a
passwordless session. The optional [trusted Wi-Fi session resume setting](../../../user_mobile/settings/settings.md#trusted-wi-fi-session-resume)
can skip the foreground-resume prompt on listed networks for already unlocked
session-only credentials. Restart and manual lock still require unlocking.
