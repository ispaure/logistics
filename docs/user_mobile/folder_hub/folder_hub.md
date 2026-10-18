# Folder Hub on mobile

## Notes Library

Select a Local, LocalCrypt or Remote location, then open its actions page (the
page with Push/Pull). **Open Notes Library** appears when that location's root
contains an actual `.obsidian` directory. It opens under **Documents**, with a
hamburger for the folder/page hierarchy, like Settings documentation. The old
crystal button is no longer in the file browser.

Expand a folder to load its immediate children, then select a `.md` or `.markdown`
note. Back/Forward revisit notes; Up shows the parent folder. The speaker opens
Read aloud with the same playback and 15-second controls as other Markdown
readers. The preview is read-only; **Open in editor** uses the selected storage.

Remote Notes Libraries have **no search field or recursive index**: opening
one lists only its root, expanding a folder lists just that folder, and opening
a note reads only that note. Local/LocalCrypt libraries offer **Filter loaded
notes**, which filters names already displayed without scanning other folders.

Notes are limited to 2 MiB, configuration/hidden files are excluded and links
stay within the selected library. Private previews stay in memory and are
retired when credentials change. Libraries are session-only Documents entries;
they do not restore decrypted paths or note names after a restart. This reader
does not run Obsidian plugins.

## File browser locations and actions

**Local File Browser** uses source tabs rather than a storage dropdown.
**On this device** opens the managed Local collection. On iOS, **Shared with
Files** opens files beside that collection in the app's shared Files directory;
the collection itself is accessed through the other tab. The shared tab appears
only when that storage location is available. Opening LocalCrypt shows its
selected source as an additional tab. Folder actions are under **…**; the back
control returns to the parent folder or Folder Hub. **Cloud File Browser** uses
the same directory, search and listing controls.

The file browser keeps your current folder, selection, list/tile mode, search, sort and browse
history when you visit Documents or Settings. Local and remote browsers give most
of the screen to the listing. Tap a local file to open it, or a folder to browse
it. The top bar shows the current directory name as plain text beside its storage
and lock icons, with no item count. Tap the magnifying glass on the right to
reveal search; close it with **×** to clear the filter and hide the field.
The top bar has no Sort control. The
rows show filenames rather than full paths, shortening long names in the middle.
File sizes remain available in **Details** instead of beside every filename. The
**↑ Parent folder** control beside the folder status goes up one level in local
and remote browsing on iOS and Android. At the current storage root it becomes
**Back to Folder Hub**. Beside the path, a drive identifies on-device storage and
a cloud identifies online storage. Encrypted folders additionally show the same
combined folder-and-lock icon as Folder Hub: an open blue padlock after successful
unlocked browsing, or an orange closed padlock with chains when locked.
These indicators describe the folder currently open, including when a remote
also has an on-device copy.
**•••** beside an item selects that item and opens its commands without opening
its contents. Rename, Move, New folder and archive-password entry have focused
screens. **Details** shows metadata and bounded previews.
Folders show up to 40 items per page, in both List and Tiles, so large folders
open promptly while thumbnails load in the background.
Larger listings show **Previous** and **Next** above the items, keeping paging
controls clear of the bottom destination bar.
Files opened from this browser stay in the Folder Hub navigation stack. Native Back
returns to the same folder, search, sorting, selection and scroll position.
Back leaves the reading/editing session open, including unsaved provider text
drafts; reopen it through **Open documents** to continue. Files opened from
Books & Comics or Open documents keep their document navigation instead.
Connection import, reload, remember and forget remain in Settings.

Use **Pin current folder** to add an ordinary local or remote folder to Folder Hub.
Remote pins identify the connection, not just its display name; a missing or
changed connection reports unavailable instead of opening another provider.
Encrypted folder paths cannot be pinned for restoration. Remove pin removes only
the shortcut. Malformed or concurrently changed pin records are preserved.

Managed folders use the reviewed Pull/Push workflow. Pull refreshes the selected
local destination; Push updates the remote. Both can replace or delete destination
files, and cancellation leaves any already completed changes in place.

## Folder Hub and Local / LocalCrypt sync

**Folder Hub** opens on **Local**, followed by **Cloud** and **Home Server**
tabs. Local includes ordinary folders and downloaded Local/LocalCrypt copies of
rclone folders. Remote-only folders appear under Cloud once credentials load.
Tap a folder under **Local** to browse its device copy; tap it under **Cloud**
to browse its online copy, including the mapped subfolder for a partial pull.
The **•••** menu keeps the same available browse, Push/Pull and folder-management
actions on both tabs. The Cloud **Credential** selector defaults to **All**; choose a credential
ZIP to filter its folders. Returning from another source resets it to **All**.
The remote names and credential filters come from loaded configurations and retained
password-protected ZIP metadata. Locked entries ask for their ZIP password when opened;
populating this tab does not ping online services. On iPad, all windows use the
same loaded credential packages. Browsing an online folder still requires a connection.
Mobile folder and file lists hide `.DS_Store` and `Thumbs.db` metadata files.
Home Server's saved and session network-share packages never appear in the Cloud
Credential dropdown. Loaded ZIPs remain in the dropdown even if they currently have no
visible folders; refreshing the hub also refreshes the package choices.
Credential labels omit `.zip` (including uppercase `.ZIP`). Duplicate labels use
a number, such as **Personal (2)**. Loaded-package changes refresh a visible hub
automatically, including changes made in another iPad window.
**Local** browses ordinary files: on iOS, **All files** opens the `Logisticks` shared
folder and other subfolders beside `Local`, excluding the managed `Local` folder.
On Android it browses the ordinary collection folder. **Home Server** contains
SMB/Mac connections added through **Add share…**, including their managed offline
copies. SMB remotes imported inside credential ZIPs stay with their package under
**Cloud**. Local and Home Server hide the credential selector. **Transfers** appears on **Cloud** only while a transfer is active or a stopped
transfer needs attention; **Add share…** appears only on **Home Server**. **Local** has
no action toolbar. The source tabs use a rounded strip with a highlighted
selection. Compact folder rows share one rounded surface per top-level branch,
with an overflow menu for each folder. Loading status and
progress appear only while a folder is opening or an error needs attention.
Each encrypted folder has a combined folder-and-lock icon before its name:
blue with an open padlock when its credentials are available, orange with a
closed padlock and a short pair of chain links when locked. The unlocked padlock's
raised shackle has a clear gap above its body. Sibling folders can have different states. The
blue/orange colors, distinct padlock shapes and Locked/Unlocked legend avoid
relying on red/green differences. Android monochrome mode retains the distinct
shapes in black. Ordinary folders use a plain folder icon. Screen readers announce
the copy type and individual lock state. Group headings describe structure,
not a shared credential state.
Dash-separated names form expanded levels (for example Server → Lib → ComicRack);
group labels are informational and remain expanded. Groups and browsable folders
use the same text size, color and row height. Groups have a muted branch icon
and regular text, including the top level; browsable folders have bold names,
folder icons and **•••**. Each level has a consistent
indent and branch guide. Child
labels and folder icons start to the right of their parent label; there are no
collapse controls. Only folder rows with folder
icons and an actions menu open a folder. Its action page reflects the copies available. **Browse Local** opens readable files on this device, **Browse LocalCrypt** opens
the encrypted device copy, and **Browse Remote** opens the online folder. Only
available copies receive a browse button; each copy is offered once. Existing
mapped Local and LocalCrypt folders retain **Browse Remote** even while their
credentials are locked; opening it prompts for the matching credentials and
returns to the mapped online subfolder. Remote
browsing opens the read-only online file browser, with direct previews and existing offline-copy
actions. Choose folders and start Push/Pull from their Folder Hub action pages.
Existing managed copies remember their storage type and transfer association.
The first pull chooses storage; later transfers reuse it. Folder Hub updates
when you return to it and when transfers or loaded credentials change. It uses
already loaded connections and local folder checks, without repeating native
connection checks or downloading remote contents. There is no manual Refresh
button. Loading or unlocking credentials updates remote names and discovers
existing encrypted copies. If the hub cannot load, **Try again** retries it.

Mobile bundles the existing `Python/configFile.ini`; its `[Folders]` exclusions
control both the remote picker and Folder Hub. Hidden backing remotes remain
loaded for crypt connections. Remote-name exclusions apply to remote entries;
folder suffix exclusions apply to all sources. These names are not hard-coded
in mobile. List and Tiles reuse the shared browser, with separated row/card
backgrounds and explicit sort controls.

Open a remote and choose **Pull…**. A selected folder is the source; otherwise
it uses the currently browsed folder, including the remote root. If a matching
local mapping already exists, Pull reuses that destination. New copies offer
**Local** (readable files) or **LocalCrypt** (original encrypted names and bytes).
Transfer confirmations use rclone path notation: `Remote:` for the configured
remote root and `Remote:folder/subfolder` for a folder within it. “Root” is not
added as a folder name.
LocalCrypt requires a crypt remote with encryption keys. Existing ordinary
folders matching the remote/folder name can be adopted as the Local destination.
Both storage types default to the app's private space. Android can instead place
both on one selected drive (see **Local / LocalCrypt location** below). Crypt storage choices only
appear when a corresponding copy exists; loading credentials does not imply the
folders are downloaded.

**Pull** makes the local destination match the remote source. **Push…** makes the
selected remote destination match local. Both open a detailed review of file
additions, replacements and deletions, based on rclone's dry-run comparison.
Confirming a completed review checks it again before writing; changed results
require another review and confirmation. Files missing from the source are removed
from the destination, within the selected folder. Both operations call the embedded
rclone library's standard Sync routine, with no backup option or new retained
snapshots. Transfers use rclone's normal incremental comparison. LocalCrypt syncs
ciphertext to/from the backing scope; a readable Local copy of a crypt remote uses
rclone's crypt filesystem for automatic encryption/decryption.

**Folder Hub → Transfers** opens **Transfer details**: **From** and **To** folders
for the current or most recent transfer, live progress, completed/known
file counts and transferred/known megabytes (MB), cancellation, active review, and completion or error
messages, wrapped to fit the phone screen. It does not list remotes or offer folder selection. The transfer banner
also opens these details; the remote browser reflects the same progress. If a
remote folder matches several local mappings, Pull opens a focused destination
chooser for those matches.

On Folder Hub itself, the transfer banner appears only on **rclone**, while a
transfer is running or an interrupted/failed transfer needs attention. Successful
completion stays available in **Transfers** without keeping a banner on the Hub.
Local and Network shares never show this banner.

Folder action pages offer **Delete local folder…** and, for managed copies,
**Remove mapping (keep files)**. Delete local folder requires confirmation and
removes only the app-private local folder and everything inside it permanently;
the online folder remains. Confirmation appears without scanning folder contents.
Deletion creates no backup and has no app recovery or undo. The app no longer runs the obsolete snapshot-recovery workflow or automatically
deletes its old backup trees. Those old files remain untouched. Removing a mapping keeps its local files. A missing or changed
connection blocks transfers until you load the matching credential ZIP.

Session-only decoded credentials and ZIP passwords stay in memory. The original
password-protected ZIP is retained with device encryption in private app storage,
with its package/remote associations, so future sessions can ask for its ZIP
password without selecting the file again. Settings autosave never saves decoded
session credentials. Unencrypted ZIPs must be selected again next time.
**Forget saved credentials** removes retained ZIPs and device keys.

Transfers show completed and active file counts, discovered entries, checks and
transferred megabytes (MB, 1 MB = 1,000,000 bytes), shown to two decimal places on
both iOS and Android. Known totals can grow as rclone discovers more files; discovery
uses a steady activity indicator until a byte total is available. A zero completed
file count can mean files are still transferring, rather than no work happening.
New copies use the exact remote name (or selected Local subfolder name), without
a random suffix. Existing copy mappings keep their recorded destination. No automatic suffix
renaming or legacy folder migration runs. LocalCrypt keeps its private account
storage. Conflicting names, including
case-only differences, refuse the pull and preserve existing copies.

Both desktop and mobile preserve empty source folders when the destination
backend supports directories. Managed Sync uses rclone’s normal retry policy
(three attempts and ten low-level retries); mobile progress shows retry attempts.
Fatal and non-retryable errors stop immediately. Cancel also interrupts a retry
wait, including a server-requested Retry-After. Review comparisons use the same
retry policy. A fresh attempt replaces the previous attempt’s comparison rows,
and a failed or cancelled comparison stays incomplete. **Proceed without full
review…** remains available while waiting for a comparison retry.

Transfers support cancellation. An interrupted sync can leave
completed writes/deletions at the destination, just like CLI rclone sync; retry
uses the same recorded location. Mobile runs one transfer at a time and does not
queue another transfer. Existing Local and LocalCrypt folders remain browsable
and readable while a folder transfer runs, including through Documents’ hamburger
menu, configured library shortcuts and Folder Hub. Opening a library keeps its
encrypted provider and account namespace. Locking or replacing credentials still
invalidates those private shortcuts. LocalCrypt listings omit rclone's
incomplete download files; refresh to discover newly completed files. A file that
changes during reading must be reopened. File-management mutations remain blocked
during a transfer. Save or close provider edits before syncing their local files. Transfers
do not promise continued execution while iOS/Android suspends the app. Host tests
verify the UI and embedded rclone tests verify incremental transfers, deletion in
both directions, plain/crypt destinations and absence of new backups. Physical
network and device validation of these changes remains pending.

Ordinary reader selection now survives cold workspace restoration and resumes when
Documents is opened. Closing secondary iPad windows releases their callbacks, widget
registries and writers. The beta simulator vetoed or terminated the process during destruction of
its launch scene, so original-window OS close remains unverified on a physical iPad.

### Keeping your place during delayed opens

If you switch documents or open Settings while a private document is loading,
the completed document stays available in the workspace without replacing your
current view or draft. Select it when you want to continue. A comic password
prompt that finishes after you leave the reader does not take keyboard focus.
Results arriving after their window has been replaced do not update that old view.
