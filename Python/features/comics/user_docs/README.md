# Read and manage comics

Browse comic libraries, read CBZs, edit metadata, convert CBRs and compress comic
pages. Comic tools belong to **Books & Comics** in Settings. Enabling that feature
also enables its Images dependency.

## Open a library

Select a configured comics folder on **Folder Hub** and choose **Open Comics Library…**.
To define its library tabs, place `remoteConfig.ini` at the collection root:

```ini
[LogisticsComics]
libraries = Comics,Mangas,Artbooks
```

Names refer to immediate child folders. **All** browses the collection root.
Missing libraries are disabled. You can also browse any folder through
**Debug → Open File Browser…**; that window provides comic actions without library
tabs or collection indexing.

## Read and edit

Readers opened from the main app appear in **Open documents**. Metadata editors
open in separate popup windows.
Use **Detach** to move the same view into a separate window and **Bring back** to
return it; switching sidebar destinations retains the open views.

- Double-click a CBZ to open the built-in reader. Use the page buttons or arrow
  keys; hold an arrow key or a page button to turn every 225 ms. Nearby pages are
  preloaded in the background. Holding stops at the first/last page; a fresh press
  is required to move into another comic. Home/End jump to the first/last page.
  Held navigation waits for each displayed page before continuing. Scroll down/up over the page to move forward/
  backward; small trackpad deltas accumulate and a cooldown limits rapid jumps.
  F11 toggles full screen.
- **File → Open comic…** and **Open recent** open CBZs only. EPUBs use their own
  reader. Both readers share the same fullscreen button; Escape exits fullscreen
  and preserves a previously maximized window.
- **Navigate → Go to page…** (Ctrl+G, Command+G on macOS) jumps directly to a page.
  The footer shows the current page/spread and a slider for quick seeking.
- Use Previous/Next File for neighboring CBZs. Reading direction follows comic
  metadata; the page-layout button or **View → Page layout** lets you choose
  Automatic, Single page or Two pages. Menu page turns follow the same spread
  boundaries as the buttons and keyboard.
- Right-click comics or folders and choose **Books & Comics → Edit metadata…**. Multiple
  selections edit only fields you explicitly change. Apply saves without closing;
  OK saves and closes. Cancel discards unapplied edits.
- The File Information and Comic Metadata panels show details of your selection.
  Both panels are always available when a comic is selected.
- Right-click files/folders for Rename, Bulk Rename and Cut/Copy. Paste is available
  on folders or empty browser space. F2 or a slow second click renames inline;
  standard clipboard shortcuts work in every view. Existing items are preserved
  when pasted names collide.

Readers do not modify page images. Applied metadata changes stay saved after Cancel.

## Edit metadata across a collection

Select the comics, or select folders to include their comics recursively, then
choose **Edit metadata…**. Only fields you explicitly change are written; leaving
a mixed field alone preserves each book's value. Changing a mixed list field
replaces that field in every selected comic rather than adding one value to each
book's existing list. Clear a field to remove it. List fields accept comma-separated
values or one value per line; suggestion lists also let you choose existing values.

Apply/OK writes metadata inside each CBZ without changing page images. A successful
save stays applied if you later cancel the dialog. Batch saves are not one transaction:
if a later file fails, earlier successful saves remain. Review failures before retrying;
there is no metadata Undo or automatic original-file backup. Files changed by another
application must be reloaded before saving. ComicRack-only fields such as Series
complete and Proposed Values are disabled; this editor does not update its database.

## Library suggestions and reading state

Opening a Comics Library indexes collection metadata in the background to offer
consistent authors, tags, publishers and other supported field suggestions. The
catalog covers the collection root even when a library tab shows one subfolder.
It stores a disposable `LogisticsComicsData/metadata.json` inside the collection root;
large collections take longer to scan. Encrypted comics are excluded from this
persistent suggestion cache. If the cache cannot be written, session suggestions
remain usable; indexing errors do not prevent manual metadata entry. Refreshing
the library updates changed/deleted entries without overwriting pending edits.

Comics remember the last successfully displayed page when you close the reader or
restart the app. Opening the same comic, including through **Open recent**, resumes
there. Previous/Next File still starts at the appropriate end of the neighboring
comic. Disable `remember_position_bool` under **Settings → Books & Comics** to stop
saving/restoring positions in new readers, for both comics and EPUBs.

Comic positions live in the commonUtils cache's `Comics` folder (on macOS,
`~/Library/Application Support/commonUtils/Cache/Comics/`). These small files store
the page number and image entry name, not page images or passwords. Symbolic links
to the same file share history; moving a comic starts a separate history. Reopen a
comic after an external archive edit so the reader uses its current contents.
The saved image name is used if it still exists; otherwise the saved page number
is limited to the current page count. EPUB reading history belongs to the
separate [Books reader](../../books/user_docs/README.md#keep-your-place).

## Compress or convert

Right-click CBZs/folders and choose **Books & Comics → Compress Comics…**, or use the
folder's **Compress CBZ…** action. Review recursion and page-retention options.
Compression replaces each successful original only after checking its output.
Normally, an encoded page is kept only if it is under 75% of the original size;
animated/multipage originals are preserved. Already marked compressed comics are
skipped in batches. Compression can change page names, image format and page metadata.

CBR conversion and other batch tools are available in the detected comics folder
and Debug workflows. CBR conversion needs a compatible installed RAR extractor;
the original CBR is deleted only after successful conversion.

**Cancel after current comic** finishes and verifies the current comic, then leaves
remaining comics untouched. Errors are reported per comic; other comics can succeed.
Keep a backup before applying bulk image or metadata changes.

## Password-protected comics

Opening a locked CBZ asks for its password if no usable configured password exists.
Successful unlocks are kept only for this session. Background previews never ask
for passwords; a locked preview is expected until the comic is unlocked.

To encrypt plain comics in place, add this to a nearby/ancestor `remoteConfig.ini`:

```ini
[LogisticsZIP]
archive_password = your-password
```

Right-click and choose **Books & Comics → Encrypt unencrypted comics…**. The action appears
only when a selected item has an ancestor INI with that section. The dialog scans
automatically. Every plain comic needs a nonempty configured password before
starting; encrypted comics are skipped. Encryption preserves decrypted page bytes.
Compression of protected comics requires the configured password and does not prompt.
Member names remain visible without the password.

To package comics inside a separate outer ZIP, use [Archives](../../archives/user_docs/README.md).

## More help

See [Using Logistics](../../../../USER_GUIDE.md) for navigation and settings.

## Compression decisions and collection maintenance

Comic compression uses color/grayscale WebP quality 60/35 and a 2400-pixel height
cap without upscaling. **Always keep compressed images** bypasses the savings
threshold and can increase size; it cannot be combined with preserving animated
and multipage originals. Disabling that preservation allows first-frame conversion.
Unlike standalone Images, encoded comic pages do not preserve transparency.

Compression removes recognized unwanted sidecars and can flatten supported wrapper
folders or normalize numeric page names. When page images change, ComicInfo page
records are rebuilt: old per-page bookmarks, DoublePage flags and page types are
not preserved. Book-level metadata remains. Metadata-only edits preserve page bytes
and page records. A batch compression marker prevents automatic recompression even
if your desired settings later change.

For collection tools offered through Folder Hub/Debug, review the target before
organization or author/series changes. Organization copies before removing its
source and stops on the first failure; this differs from compression, which can
continue past failed comics. There is no collection-wide Undo. If an action fails,
read its item-level results before retrying the remaining files.

Comics remember the last successfully displayed page by default, using its image
filename to keep the same page after reordering where possible. File Browser tile
covers show that saved position as **45/205** at the top-right. Unread comics have
no badge. The badge updates as reading position is saved, without changing the
archive; disabling Remember Position hides it. Older saved positions also work
once the cover is loaded.

## Mobile development builds

The independent native app has private EPUB and PNG/JPEG CBZ/ZIP reading,
chapter/page progress and bookmarks. It has a smaller format/UI scope than this
desktop guide. See the [mobile guide](../../../logisticsmobile/user_docs/README.md)
for imports, limits and current validation status.


## Metadata inside LocalCrypt

Desktop LocalCrypt provides **Edit comic metadata…**. Mobile encrypted offline
copies provide **Edit metadata…** in the private reader. Saves preserve page bytes,
page metadata and the inner ZIP password, and update only the encrypted local
copy. No plaintext backup or persistent metadata draft is created. Mobile retains
unsaved fields in memory until saved or explicitly discarded; saving does not
upload the comic. See the [mobile LocalCrypt guide](../../../logisticsmobile/user_docs/README.md#localcrypt-encrypted-offline-reading).

On desktop, **Edit comic metadata…** in LocalCrypt uses all selected comics and
folders. Folder selections include nested CBZs and ZIP archives with comic image
pages; unrelated files and ZIPs without images are ignored. Overlapping folder/file
selections edit each comic once. The scan is limited to 10,000 entries. Inner ZIP
passwords for batch editing come from the copy's nearest `remoteConfig.ini`.
Batch editing reports locked comics it cannot open; it does not silently
change their passwords. Saves preserve page bytes, untouched metadata and the inner
ZIP password, and update the encrypted local copy until you explicitly Push.
After a desktop metadata save, the LocalCrypt browser refreshes the selected
comic's information panel. After a Pull, use **Refresh folder** to reload an
already-open browser. Pull can replace local metadata with the remote version;
Push saved local edits first if you want them on the remote.

Comic readers and metadata windows opened from private storage begin their titles with **🕵️ Private -**. Ordinary comic windows keep their existing titles.

Desktop file unlocks validate before closing the password prompt. If the password
is wrong, the same prompt shows an error, clears the field and keeps focus there
for another attempt. This applies to ordinary comics and inner passwords in
LocalCrypt copies; Cancel keeps the current comic open.

Desktop **Open comic…**, including the New Document launcher, uses the shared Local/LocalCrypt file picker with a CBZ filter. A LocalCrypt choice opens a separate private reader; opening a local comic from a private reader creates an ordinary reader.


Ordinary Android/iOS CBZ/ZIP library imports stream archives without a 256 MiB
whole-file or expanded-total cap. Reading loads one page at a time through a
shared revision-checked archive source; PNG/JPEG page and header-count limits
remain. The [mobile guide](../../../logisticsmobile/user_docs/README.md) lists the
current format limits and shared navigation controls.

## Native mobile library

To inspect retained imports, open **Settings → Books & Comics → Saved books &
comics…**. The page shows the file count, total archive/reading-record size and
per-import sizes, including closed imports. **Delete local copy…** removes the
import and its reading records after confirmation, leaving its original source
unchanged. Closing a comic in Open documents only closes the reader. Imported
copies are private app data on iOS and do not appear in Files.

On iOS and Android, **Books & Comics** lists library folders configured by
`remoteConfig.ini` in Local and unlocked LocalCrypt copies, using the same
`[LogisticsComics] libraries` names as desktop. Tap a library folder to browse its
contents. Imported books/comics appear in their own section beneath configured library folders.

**Books & Comics → Import…** accepts standalone
password-protected AES/ZipCrypto CBZ/ZIP comics. Unlock with the comic’s ZIP password;
rclone credentials are unnecessary. See the [mobile reading guide](../../../logisticsmobile/user_docs/README.md#books-and-comics)
for password retries and supported page formats. There is no separate comic
relock action; configured INI archive passwords continue to unlock folder reads.
Rclone crypt credential locking is a separate connection operation.

Mobile Local and LocalCrypt comics use the same fit/zoom/swipe and reading-mode
controls, with Previous/Next available when controls are visible. LocalCrypt
readers expose page navigation without bookmark controls. Readers opened from Files return to the
same folder through Back, including after visiting reader tools.

Mobile imports, provider-backed readers and ordinary browser covers ignore macOS
resource-fork image entries and use the same natural page order. Unsupported
image formats fail explicitly instead of silently disappearing from the comic.

Choose **Appearance → Comic page layout** in an imported reader, or **Appearance…**
in a provider reader, for Single, Automatic or Two pages. Portrait page
pairs respect manga visual order; landscape and ComicInfo DoublePage pages remain
single. Automatic is the mobile default: a reading area wider than tall shows two
portrait pages; a taller or square area shows one. Existing explicit Single or Two
pages choices remain available. ComicInfo `Manga=YesAndRightToLeft` places the
earlier page on the right; left-to-right comics place it on the left.
Comic appearance shows only page layout. EPUB font, spacing, text width, margins
and theme controls do not appear in comics, and applying comic layout leaves
those preferences unchanged. Comic menus omit read-aloud, chapter search and
bookmarks; **Comic pages…** in an imported reader opens the page selector.
Imported, Local, LocalCrypt and remote comics use the same menu names and order,
page selector and appearance form. Read-only remote previews omit metadata
editing. Previous/Next comic use `|≪` / `≫|` buttons above the image when controls
are visible, separate from the page arrows and slider below. File buttons disable
when unavailable and hide in fullscreen. Switching comics preserves the controls'
visibility. Neither file switching nor All documents appears in the overflow menu.
**Close comic** closes the reader without deleting a saved copy.
**… → Info…** shows only the opened comic's path: the saved file path for an
import, `remote:path` for a remote preview, or the logical LocalCrypt location
for a folder-backed encrypted file. Imported copies show their current stored
path; their original import location is not reconstructed.
Previous/Next and swipes advance past the displayed spread. Imported and provider
readers show a page slider between the arrows when reading controls are visible;
drag and release it to jump directly to a page. Manga places Next on the left and
Previous on the right, with slider progress running from right to left.
Automatic layouts reevaluate when the viewport changes. Single and Two-page
views also refit to the available width after rotation. Resizing waits while a
spread is zoomed; fitting it allows the pending layout update.

In fullscreen comics on iOS and Android, hold a thumb on the page for about
400 ms to show a 2× magnifying bubble. The bubble enlarges the page beneath
its center and grows larger on tablet screens. The bubble sits close
to the thumb with a slight overlap. Keep holding and drag to move
the bubble. Near a screen edge, keep dragging toward the edge to inspect the
outermost pixels even after the bubble stops moving. Release to dismiss. The page stays still while the bubble is open. A second
finger cancels the bubble so pinch zoom remains available. The bubble is disabled
when reading controls are visible and is cleared on page changes or leaving the
reader. It works on single pages and spreads, including Local/LocalCrypt comics.

Two-page spreads use one continuous zoom/pan surface. Pinch to zoom both pages
together, then drag across the gutter to inspect either page. Page proportions and
manga order are preserved. **Fit comic page** returns the whole spread to fit size.
Swipes turn pages only at fit size; while zoomed, dragging pans the spread.
Rotating while zoomed retains the current spread until you fit it. A failed page
decode or spread composition keeps the displayed spread and its zoom. Private
spreads stay in memory and are cleared on suspend/close; returning starts fitted.

Imported reader menus include First/Last page and Previous/Next comic. The page
selector also supports direct jumps. Neighboring imported comics use natural
filename order. Provider Previous/Next comic works within the current managed
folder; standalone encrypted-copy UUID storage has no sibling-folder route.

Ordinary imported comics now have **Edit metadata…**. In the catalogue, select
imported comic rows and choose **Edit selected comics metadata…** for a batch.
Only checked fields are written; checking an empty field explicitly clears it.
Mixed fields are kept unless checked. All selections are validated before writing.
Successful files stay saved if another file fails. **Cancel after current comic**
finishes the current verified save and leaves remaining items untouched. Failures
and unprocessed files are counted, and form values remain available for retry.

Metadata updates preserve page bytes and the external import source. Standalone
password-protected imports remain readable, but metadata rewriting needs a native
archive writer and is not enabled. Provider-backed encrypted metadata editing
retains its existing ciphertext transaction. Mobile compression, CBR conversion,
organization and provider-wide catalogue indexing remain outstanding. Imported
catalogue suggestions and recursive LocalCrypt batches are described below.


### Mobile collection search and folder batches

The imported catalogue searches filenames and indexed metadata, including title,
author, tags, series and publisher. Indexing runs in the background and the status
shows how many imports have been checked. Every ordinary import is eligible; the
former first-200 limit has been removed. Metadata fields contribute their first
4,096 characters. The catalogue shows 50 results at a time; use **Previous results**
and **Next results** to browse, or search across the entire indexed collection.
Selections remain checked when changing pages or searching.

The disposable index is stored locally, reuses unchanged archive revisions across
launches and updates after metadata saves. **Refresh** retries unreadable entries,
updates changed imports and removes deleted imports. Interrupted scans retain
completed work and continue on the next refresh. Filename search remains available
while metadata is loading. Protected imports do not contribute metadata or
suggestions, even if their archive password was remembered elsewhere. Private
provider documents never enter this ordinary-import index.

Imported single-comic and batch metadata forms offer existing author/tag/publisher
and other supported suggestions. Choosing a suggestion is an explicit edit; opening
a form does not change mixed values or select fields for publication. List-field
suggestions append without duplicates. Only checked batch fields are written.

In **Files → Actions**, choose **Edit comics in this folder…** for an ordinary local
folder. The selected folder (or current folder when no folder is selected) includes
nested CBZ/ZIP comics. Review the form and check fields before **Apply selected
fields**. Scans are bounded to 200 comics, 10,000 entries and 16 folder levels.
All selected files and patches are checked before the first write; changed or
unsupported archives stop preflight. After writing starts, files publish
independently. **Cancel after current comic** leaves completed saves in place and
remaining files untouched. Errors before publication keep the original contents;
already published saves are not rolled back. Reopen the batch if a saved revision
cannot be refreshed. Repeated Apply
is blocked while a batch is running. Page/resource bytes remain unchanged.

The same action works in an unlocked **LocalCrypt** managed folder. It reads one
archive at a time and retains only metadata snapshots, bounded to 8 MiB in total.
Saves use verified ciphertext staging; page/resource bytes remain unchanged, and
the cloud original is not changed until a separate Push. Inner password-protected
archives use the folder's configured archive password when available. A wrong or
missing password stops batch preparation before any file is written.

Private batch forms have no recovery file. Leaving the form, backgrounding the app,
memory cleanup or replacing/locking credentials closes the batch and clears fields
and suggestions. Reopen the folder to continue. Closing also cancels pending work
before publication; an already published save remains saved. Other windows must be
closed before opening a private batch. Private suggestions are drawn only from the
current batch and are never added to the ordinary imported index.

Encrypted standalone imports still require a native archive writer. Private remote
trees must first have a managed LocalCrypt copy; this action does not recursively
rewrite a live remote tree. Unapplied forms are memory-only.

On iPhone Duo with a partially open vertical fold, comics use a page on each
side of the physical center seam. Portrait pages retain their proportions and
meet at the seam even when their shapes differ; manga keeps its right-to-left
order. A final unpaired portrait page stays on its reading side. A landscape
image remains a single page spanning the available display. Fully opening the
device restores the selected page-layout preference. This applies to imported
comics and Local/LocalCrypt/remote comics. Zooming retains the current view until
returning to fit size, when posture changes can reflow it.

### iOS edge-to-edge reading

Fullscreen comics hide the system status indicators as well as app navigation.
The image canvas uses the full window, including the former status-indicator strip.
On a partially folded Duo, the page join stays at the physical crease; equal-shaped
pages have equal available space without shrinking the left page to match a reserved
right-hand strip. Source aspect ratios and built-in page borders remain unchanged.
Tap the page to restore controls and normal safe areas. Android retains its immersive
system-bar behavior. Ordinary and private comics share this presentation.
