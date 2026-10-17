# Rclone mobile workflows

## Android and iOS prototype

The independent mobile app can import the same TXT-in-ZIP credential format into
an in-memory embedded rclone session, browse supported remotes and preview supported files directly. Managed Local and LocalCrypt folders support repeatable Pull and reviewed
Push with progress while ordinary writing or reading continues. Transfer details
show the transfer's **From** and **To** folders during and after the transfer,
alongside transferred and known totals in megabytes (MB) on both platforms. Both use rclone
Sync: files at the destination can be replaced or deleted, with no retained
backup or rollback. Mobile runs one transfer at a time with no queue; existing
Local and LocalCrypt copies remain browsable and readable during folder transfers,
including Documents and configured library shortcuts. Empty-folder changes
participate in the mobile review and its final recheck.
Progress displays the latest reported totals, without queuing older updates
ahead of browsing when native rendering is busy.
Mobile does not offer mounts. See the [mobile transfer guide](../../../../../docs/user_mobile/folder_hub/folder_hub.md#folder-hub-and-local--localcrypt-sync)
for connection scopes, encrypted storage, cancellation and credential persistence.

### Mobile folder navigation

In the mobile Folder Hub, tapping a folder opens its preferred available copy.
The adjacent **•••** action button keeps explicit Browse Local/LocalCrypt/Remote,
Pull and Push choices together. Mapped copies show Pull and Push direction.
Delete local folder is separated and styled as destructive, and retains its
confirmation. Transfer notifications use larger touch targets and an accessible
dismiss label. Credential, Local, LocalCrypt, Pull and Push terminology is retained.

### Android collection drive

Android and iOS both offer **Settings → Folder Hub → Show Legacy** for Legacy
folder and credential visibility. Android additionally offers **Local / LocalCrypt
location…**: choose one drive for both `<drive>/Logistics/Local` and
`<drive>/Logistics/LocalCrypt`. Android All files access is required for public
SD-card folders. Downloads are copied and verified before switching, with the
source retained as a recovery backup. Credentials and transfer associations stay
internal. A missing card stops collection operations without an internal fallback.
See the [mobile storage guide](../../../../../docs/user_mobile/settings/settings.md#local--localcrypt-location)
for migration, restart and existing-destination behavior.

### Side-by-side mobile credential packages

Android and iOS can keep several ZIP packages loaded together. Each import's
**Save credentials on this device** choice applies to that package: saved
packages persist in the encrypted private vault; session-only packages remain
active in memory without entering that vault. Folder Hub exposes their separate
credential groups, and Connections shows their loading modes. Duplicate remote
names receive package qualifiers and preserve their original account identities.
Reloading saved credentials keeps active session packages. See the
[mobile package guide](../../../../../docs/user_mobile/navigation/panels.md#multiple-credential-packages-on-android-and-ios).

### Mobile Folder Hub source tabs

On Android and iOS, Folder Hub opens the **rclone** source with **Credential: All**.
Choose a package to filter its folders and their downloaded Local/LocalCrypt copies.
The **Local** and **Network shares** tabs display separate folder trees and hide the
credential selector. Returning to rclone selects All again. Directly added SMB/Mac
connections and their copies appear under Network shares; SMB remotes imported
from a credential ZIP remain under rclone with that package. On iOS, Local browses
files directly in `Logisticks` and subfolders beside the managed `Local` folder.
