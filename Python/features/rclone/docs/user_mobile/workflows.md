# Rclone mobile workflows

## Android and iOS prototype

The independent mobile app can import the same TXT-in-ZIP credential format into
an in-memory embedded rclone session, browse supported remotes and preview supported files directly. Managed Local and LocalCrypt folders support repeatable Pull and reviewed
Push with progress while ordinary writing or reading continues. Transfer details
show the transfer's **From** and **To** folders during and after the transfer,
alongside a numeric percentage of known work and transferred/known totals in
megabytes (MB) on both platforms. The transfer banner also shows the percentage.
Progress uses bytes when available, or completed/known file counts otherwise;
unknown totals show activity without a percentage. Totals can grow as rclone
discovers files. Live progress stays below 100% until completion is verified,
and reopening details keeps the current percentage. Both use rclone
Sync: files at the destination can be replaced or deleted, with no retained
backup or rollback. Mobile runs one transfer at a time with no queue; existing
Local and LocalCrypt copies remain browsable and readable during folder transfers,
including Documents and configured library shortcuts. Empty-folder changes
participate in the mobile review and its final recheck.
Progress displays the latest reported totals, without queuing older updates
ahead of browsing when native rendering is busy.
Transfer details include **Back** and stay in the tab from which they were opened;
leaving the screen keeps the transfer running. Progress counters appear on separate
lines with labels for copying, discovery and comparison. Cloud previews requiring
the connection show a dialog while transfers are running, including when opened
from Recent or an open document. Local reader menus remain available.
Mobile does not offer mounts. See the [mobile transfer guide](../../../../../docs/user_mobile/folder_hub/folder_hub.md#workspaces-and-local--localcrypt-sync)
for connection scopes, encrypted storage, cancellation and credential persistence.

### Mobile folder navigation

An entry's three-dot button offers its remote commands in place using the host's
native popup or action sheet. Open folder/preview acts on the selected entry;
archive-capable files also offer **Archive password…**. Only choosing the password
command (or encountering an encrypted archive) opens the password form.

Cloud folders open in **Cloud File Browser**. Open documents and Recent display
cloud or device icons and a connection padlock beside filenames. Recent keeps up
to ten eligible files. For password-protected session-only credential ZIPs, open
and recent filenames and paths are saved in an AES-256 ZIP protected with the same
credential ZIP password. Enter that password to unlock the credential and restore
its entries; files load only when selected. No file contents, unsaved edits or
passwords are stored in the cache. Forgetting credentials also removes these
caches, including other windows' copies. An unencrypted credential ZIP has no
required password and does not enable this cache.

In the mobile Workspaces, tapping a folder opens its preferred available copy.
The adjacent **•••** action button keeps explicit Browse Local/LocalCrypt/Remote,
Pull and Push choices together. Mapped copies show Pull and Push direction.
Delete local folder is separated and styled as destructive, and retains its
confirmation. Transfer notifications use larger touch targets and an accessible
dismiss label. Credential, Local, LocalCrypt, Pull and Push terminology is retained.

### Android collection drive

Android and iOS both offer **Settings → Workspaces → Show Legacy** for Legacy
folder and credential visibility. Android additionally offers **Local / LocalCrypt
location…**: choose one drive for both `<drive>/Logistics/Local` and
`<drive>/Logistics/LocalCrypt`. On Android 11 and newer, All files access is required
for public SD-card folders. Android 7–10 instead offers Logistics' app-owned
folder on each mounted drive, with no storage permission required; Android removes
those app-owned folders on uninstall or clearing app data. Keep a separate backup.
Downloads are copied and verified before switching, with the
source retained as a recovery backup. Credentials and transfer associations stay
internal. A missing card stops collection operations without an internal fallback.
See the [mobile storage guide](../../../../../docs/user_mobile/settings/settings.md#local--localcrypt-location)
for migration, restart and existing-destination behavior.

### Unlock from Home

**Unlock** beside **Your workspace** opens a credential chooser and ZIP password
field for retained credential ZIPs that are present on disk and not already
loaded. Unlocking uses the existing session-only import and returns to Home;
the password is cleared after each attempt and when changing the selection.
Show Legacy applies to this chooser and button availability. Home displays only
the generic Unlock action until you open the chooser.

### Side-by-side mobile credential packages

Android and iOS can keep several ZIP packages loaded together. Each import's
**Save credentials on this device** choice applies to that package: saved
packages persist in the encrypted private vault; session-only packages remain
active in memory without entering that vault. Workspaces exposes their separate
credential groups, and Connections shows their loading modes. Duplicate remote
names receive package qualifiers and preserve their original account identities.
Reloading saved credentials keeps active session packages. See the
[mobile package guide](../../../../../docs/user_mobile/navigation/panels.md#multiple-credential-packages-on-android-and-ios).

### Mobile Workspaces source tabs

On Android and iOS, Workspaces opens on **Local**. The **Cloud** source uses **Credential: All**.
Choose a package to filter its folders and their downloaded Local/LocalCrypt copies.
The **Local** and **Home Server** tabs display separate folder trees and hide the
credential selector. Returning to Cloud selects All again. Directly added SMB/Mac
connections and their copies appear under Home Server; SMB remotes imported
from a credential ZIP remain under Cloud with that package. On iOS, Local browses
files directly in `Logisticks` and subfolders beside the managed `Local` folder.

Cancelling a sync stops that transfer or its comparison. It does not cancel an independent local file operation. Changes already published remain in place.
