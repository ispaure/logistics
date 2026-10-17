# Folder Hub on mobile

## File browser locations and actions

The file browser keeps your current folder, selection, list/tile mode, search, sort and browse
history when you visit Documents or Settings. Local and remote browsers give most
of the screen to the listing. Tap a local file to open it, or a folder to browse
it. Search stays visible; **Sort** reveals sorting and list/tile options. The
**↑ Parent folder** control beside the folder status goes up one level in local
and remote browsing on iOS and Android, stopping at the current storage root.
**•••** beside an item selects that item and opens its commands without opening
its contents. Rename, Move, New folder and archive-password entry have focused
screens. **Details** shows metadata and bounded previews.
Folders containing up to 500 items scroll in one list, in both List and Tiles.
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

**Folder Hub** separates folders into **rclone**, **Local** and **Network shares**
tabs above the credential selector. Each tab shows only its own folder tree.
**rclone** opens by default and keeps managed Local/LocalCrypt copies alongside their
online folders. Its **Credential** selector defaults to **All**; choose a credential
ZIP to filter its folders. Returning from another source resets it to **All**.
**Local** browses ordinary files: on iOS, **All files** opens the `Logisticks` shared
folder and other subfolders beside `Local`, excluding the managed `Local` folder.
On Android it browses the ordinary collection folder. **Network shares** contains
SMB/Mac connections added through **Add share…**, including their managed offline
copies. SMB remotes imported inside credential ZIPs stay with their package under
**rclone**. Local and Network shares hide the credential selector. **Transfers** appears only
on **rclone**; **Add share…** appears only on **Network shares**. **Local** has
no action toolbar. The source tabs use a rounded strip with a highlighted
selection. Compact folder rows have separate copy icons and an overflow menu;
a legend below the tree names Local, LocalCrypt and Remote. Loading status and
progress appear only while a folder is opening or an error needs attention.
Each folder row shows icons beside its name for the available copies: a drive
for **Local**, a lock for **LocalCrypt**, and a cloud for **Remote**. Multiple
icons mean multiple copies are available. LocalCrypt means the device copy is
encrypted. Screen readers announce the copy types. Group-only headings have no
storage icons.
Dash-separated names form expanded levels (for example Server → Lib → ComicRack);
triangles collapse or expand parent levels. Its action page reflects the copies available. **Browse Local** opens readable files on this device, **Browse LocalCrypt** opens
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
