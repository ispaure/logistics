# Workspaces on mobile

Each workspace is a configured folder or storage location with relevant tools and
actions: browse its files, open a Notes Library, or manage available local,
encrypted and remote copies. Open **Workspaces** from the main navigation, then
use a folder's **Workspace actions** menu for its available commands.
The **Local** source opens without loading cloud connection controls. Selecting
**Cloud** or **Home Server** initializes connections and restores saved credentials.

On tablets and other windows with at least 640 points of usable width,
Workspaces keeps the locations and source controls on the left. Opening a local,
LocalCrypt or remote folder shows its files on the right; workspace actions use
that same right pane. Each pane scrolls independently. Narrow windows use the
full-screen browser and Back returns to Workspaces. Rotating between these
layouts keeps the current browser, source and folder. Rotating repeatedly does
not open a child folder or return to a different panel. iPhone layouts use the
current window safe areas to keep controls clear of notches, the Dynamic Island
and the Home indicator. On a flat Duo, landscape browsing gives roughly one
third of the usable width to Workspaces and two thirds to the file browser.
Android e-ink layouts also favor the browser, including portrait when both panes
fit. Partially folding a Duo makes the system-reserved crease determine the pane
bounds instead; rotating a horizontal crease can stack the panes. The current
folder and retained views survive these changes.

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

**Local File Browser** opens directly on the current folder, without a source
button above it. The folder header has Back (‹), Search and an upper-right
actions menu (circled ellipsis on iOS, vertical dots on Android). On iOS it opens
Logistics’ shared Files directory, showing files and folders saved there alongside
**Local**. Open Local to browse the managed folder; Back
returns to the shared directory. This is the existing
`Local` folder in Apple’s Files app; no files are moved or duplicated. Its root
cannot be renamed, moved or deleted from the outer browser; open it to manage its
contents. Workspaces lists imported folders and downloaded/synced copies
individually, opening each folder directly. **Browse All Files** appears underneath
the folder list and opens the shared directory on iOS.
On Android, it opens the managed Local folder.
When you open a local folder directly from Workspaces, Back from that folder
returns to Workspaces. Inside a subfolder, Back first returns to its parent.
List mode uses compact native rows on both iOS and Android.
LocalCrypt uses the same single folder header, without a second source strip.
Choose another source in Workspaces. Workspace actions are in the header menu;
the back control returns to the parent folder or Workspaces. **Cloud File Browser** uses the same directory, search and listing
controls.

The file browser keeps your current folder, selection, list/tile mode, search, sort and browse
history when you visit Documents or Settings. Local and remote browsers give most
of the screen to the listing. Tap a local file to open it, or a folder to browse
it. The top bar shows the current directory name as plain text,
with no item count or outline, including in Android
e-ink mode. Beneath it, a smaller line shows passive storage and lock icons with
Cloud or On-device and, for encrypted folders, Locked or Unlocked labels.
Opening, download, result and error messages temporarily replace that line; the
indicators return when the message clears. Tap the magnifying glass on the right to
reveal search; close it with **×** to clear the filter and hide the field.
Search and **…** share the title row at the upper right. On iOS they sit in the
native navigation bar; Android keeps them beside the folder name and subtitle.
They remain available after returning up the folder stack.
An entry's three dots show commands in place: a native dropdown anchored to the dots on both Android and iOS. Selecting Rename or Move opens its form;
opening the menu itself keeps you in the listing. Changing folders, refreshing
the listing or locking the browser dismisses old row commands.
The three dots beside a folder in the main Workspaces list also open an anchored
menu, with Browse, Pull, Push and Delete commands as applicable. Transfer review
and deletion confirmation still open after choosing a command.
The listing starts directly below this header. Opening Search adds an input row
beneath the folder name and storage/status line. Folder actions remain in the top bar.
Local file search includes files and folders in every subfolder beneath the
current location. Typing pauses briefly before searching; clearing search restores
the current folder's immediate children.
This control stays beside the folder name in local, remote and drawer browsers,
including when a long folder name is shortened to fit.
List mode uses a native scrolling list on iOS and Android, reusing rows as you
scroll. Every matching item is available without page buttons. Search includes
all available entries, including those you have not scrolled to yet. Local and
LocalCrypt search scans folder and file names throughout the current folder and
its subfolders. Matches appear as they are found; the search status stays visible
while scanning continues and reports partial results or errors. Cloud and Home
Server search filters the currently listed folder. Closing search restores the
current folder listing.
The top bar has no Sort control. The
rows show filenames rather than full paths, shortening long names in the middle.
File sizes remain available in **Details** instead of beside every filename.
On Android, the **‹ Back** control follows the same history as system Back:
clear a search query, close the search field, then return to the previous folder
or opening screen. When a folder was opened directly without a previous visit,
Back falls back to its parent. On wide iOS Workspaces, Back sits above the detail
pane and folder transitions leave the workspace list in place.

Browser Back, Search and paging controls use borderless accent-colored
icons in normal appearance. Android High contrast / E Ink keeps their black
outlines and monochrome icons.

Beneath the folder name, a drive identifies on-device storage and a cloud
identifies online storage. Encrypted folders additionally show the same
combined folder-and-lock icon as Workspaces: an open blue padlock after successful
unlocked browsing, or an orange closed padlock when locked.
These indicators describe the folder currently open, including when a remote
also has an on-device copy.
In List mode, tap the **⋯** button beside an item on either Android or iOS to
select it and open its commands without opening its contents. Tapping the row
still opens it. Android long press and iOS's **Select** swipe action remain
available as shortcuts. Rename, Move, New folder and archive-password entry have focused
screens. **Details** shows metadata and bounded previews.
Folders and search results show all matching items in one scrolling view, in
both List and Tiles. There is no per-page limit or Previous/Next paging.
Files opened from this browser open under **Documents**, which becomes the
selected tab. Tap the **Workspaces** tab/icon to return to the folder you opened
them from, with its search, sorting and selection retained. Documents keeps the
reading/editing session open, including unsaved provider text drafts. Native Back
inside Documents returns through its document screens; Android Back can also
return to the source destination after leaving the reader.
Connection import, reload, remember and forget remain in Settings.

Use **Pin current folder** to add an ordinary local or remote folder to Workspaces.
Remote pins identify the connection, not just its display name; a missing or
changed connection reports unavailable instead of opening another provider.
Encrypted folder paths cannot be pinned for restoration. Remove pin removes only
the shortcut. Malformed or concurrently changed pin records are preserved.

Managed folders use the reviewed Pull/Push workflow. Pull refreshes the selected
local destination; Push updates the remote. Both can replace or delete destination
files, and cancellation leaves any already completed changes in place.

## Workspaces and Local / LocalCrypt sync

**Workspaces** opens on **Local**, followed by **Cloud** and **Home Server**
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
**Local** lists imported folders, downloaded/synced copies and, on iOS, folders
beside `Local` in the `Logisticks` shared directory. **Browse All Files** below the
list opens that directory, including the managed `Local` folder.
On Android it opens the ordinary Local folder. **Home Server** contains
SMB/Mac connections added through **Add share…**, including their managed offline
copies. SMB remotes imported inside credential ZIPs stay with their package under
**Cloud**. Local and Home Server hide the credential selector. **Transfers** appears on **Cloud** only while a transfer is active or a stopped
transfer needs attention. **Add share…** appears on **Home Server** only when no
share is configured; **Add Remote…** appears on **Cloud** only when no remote is
configured and opens connection settings. Saved or locked connections count as
configured, even when filters hide their folders. Further connections can be
added from Settings. **Local** has no action toolbar. The source tabs use a rounded strip with a highlighted
selection. Workspaces and the file browser use matching compact rows, regular
titles, icon spacing and rounded row surfaces, with an overflow menu for each
workspace folder. Loading status and
progress appear only while a folder is opening or an error needs attention.
Android folder and overflow icons sit centered within their touch targets,
leaving room for the row outline. High contrast uses the same icon sizes,
title sizes and content positions as regular appearance across all source tabs.
File-browser lists sit in one rounded group on iOS and Android, with inset dividers between files. The group ends at the final row
for short lists, leaving the surrounding page visible below it. Long lists
scroll inside the available pane. Android High contrast / E Ink adds a black
outline while keeping the same rounded corners and row spacing.
On Android, the hierarchical workspace overview reserves a separate scrollbar
gutter, so scrolling does not paint the thumb over folder outlines or actions.
Each encrypted folder has a combined folder-and-lock icon before its name:
blue with an open padlock when its credentials are available, orange with a
closed padlock when locked. Both solid padlock bodies sit in the center of the
folder; the unlocked shackle swings outward to the right. Sibling folders can have different states. The
blue/orange colors, distinct padlock shapes and Locked/Unlocked legend avoid
relying on red/green differences. Android monochrome mode retains the distinct
shapes in black. Ordinary folders use a plain folder icon in the same blue as unlocked folders. Screen readers announce
the copy type and individual lock state. Group headings describe structure,
not a shared credential state.
Dash-separated names form expanded levels (for example Server → Lib → ComicRack);
group labels are informational and remain expanded. Groups and browsable folders
use the same text size and row height. Groups have plain bold labels
with no icon, including the top level; browsable folders have regular names,
folder icons and **•••**. Each level has a consistent
40-point indent and soft grey branch connectors. Connectors start beneath the
parent heading (or folder icon) and meet the vertical centre of each immediate
child row; the trunk ends at the last child. Child
labels and folder icons start to the right of their parent label; there are no
collapse controls. Only folder rows with folder
icons and an actions menu open a folder. Its anchored actions menu reflects the copies available. **Browse Local** opens readable files on this device, **Browse LocalCrypt** opens
the encrypted device copy, and **Browse Remote** opens the online folder. Only
available copies receive a browse command; each copy is offered once. Existing
mapped Local and LocalCrypt folders retain **Browse Remote** even while their
credentials are locked; opening it prompts for the matching credentials and
returns to the mapped online subfolder. Remote
browsing opens the read-only online file browser, with direct previews and existing offline-copy
actions. Choose folders and start Push/Pull from their Workspaces action pages.
Existing managed copies remember their storage type and transfer association.
For the first pull from a session-only crypt remote, a popup strongly recommends
LocalCrypt and offers a regular Local copy instead. Saved-credential and non-crypt
remotes create Local copies. Later transfers reuse the existing storage type. Workspaces updates
when you return to it and when transfers or loaded credentials change. Switching
back to an unchanged source tab reuses its existing folder rows; folder and
credential changes refresh those rows automatically. Discovery uses
already loaded connections and local folder checks, without repeating native
connection checks or downloading remote contents. There is no manual Refresh
button. Loading or unlocking credentials updates remote names and discovers
existing encrypted copies. If the hub cannot load, **Try again** retries it.

Mobile bundles the existing `Python/configFile.ini`; its `[Folders]` exclusions
control both the remote picker and Workspaces. Hidden backing remotes remain
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

**Workspaces → Transfers** opens **Transfer details**: **From** and **To** folders
for the current or most recent transfer, live progress, completed/known
file counts and transferred/known megabytes (MB), cancellation, active review, and completion or error
messages, wrapped to fit the phone screen. It does not list remotes or offer folder selection. The transfer banner
also opens these details; the remote browser reflects the same progress. If a
remote folder matches several local mappings, Pull opens a focused destination
chooser for those matches.

**Back** and Android's system Back return to the screen where you opened the
details without stopping the transfer. Progress separates files copied, files
found, files compared and megabytes copied onto separate lines. Totals can grow
as more files are found; 100% means the transfer has finished verification.
Local document menus remain available during transfers. Opening a cloud preview
that needs the connection shows a **Transfer in progress** explanation; wait for
completion or open a Local copy.

On Workspaces itself, the transfer banner appears only on **rclone**, while a
transfer is running or an interrupted/failed transfer needs attention. Successful
completion stays available in **Transfers** without keeping a banner on Workspaces.
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
menu, configured library shortcuts and Workspaces. Opening a library keeps its
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

## Local / LocalCrypt location

When changing the Android storage location, a dedicated progress page shows the
source and destination, current folder/file, copied MiB and a percentage for the
folder being copied. Scanning and byte verification use an activity indicator
because their total work is not known yet. A completed copy is followed by final
verification before the new location is saved. Keep Logistics open throughout.
Selecting existing files checks only the collection folder paths and saves the
location, without scanning or hashing their contents. Preparing empty folders
and erasing an unused location also show their current stage. Failures keep the
original location selected and show a retry message; an interrupted erase can
leave some old files deleted.

### Keeping your place during delayed opens

If you switch documents or open Settings while a private document is loading,
the completed document stays available in the workspace without replacing your
current view or draft. Select it when you want to continue. A comic password
prompt that finishes after you leave the reader does not take keyboard focus.
Results arriving after their window has been replaced do not update that old view.
