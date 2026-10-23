# Read and manage comics

Browse comic libraries, read CBZs, edit metadata, convert CBRs and compress comic
pages. Comic tools belong to **Books & Comics** in Settings. Enabling that feature
also enables its Images dependency.

## Open a library

Select a configured comics folder on **Workspaces** and choose **Open Comics Library…**.
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
  boundaries as the buttons and keyboard. Paired pages touch without an added
  center gutter.
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
separate [Books reader](../../books/user/user.md#keep-your-place).

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

To package comics inside a separate outer ZIP, use [Archives](../../archives/user/user.md).

## More help

See [Using Logistics](../../../user/user.md) for navigation and settings.

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

For collection tools offered through Workspaces/Debug, review the target before
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

See [Comics mobile workflows](../user_mobile/reading.md#mobile-development-builds).

## Metadata inside LocalCrypt

Desktop LocalCrypt provides **Edit comic metadata…**. Mobile encrypted offline
copies provide **Edit metadata…** in the private reader. Saves preserve page bytes,
page metadata and the inner ZIP password, and update only the encrypted local
copy. No plaintext backup or persistent metadata draft is created. Mobile retains
unsaved fields in memory until saved or explicitly discarded; saving does not
upload the comic. See the [mobile LocalCrypt guide](../../rclone/user_mobile/localcrypt.md#localcrypt-encrypted-offline-reading).

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
remain. The [mobile guide](../../../user_mobile/user_mobile.md) lists the
current format limits and shared navigation controls.

## Native mobile library

See [Comics mobile workflows](../user_mobile/reading.md#native-mobile-library).


## Page-turn motion

Page turns use a short slide within the reading area. The toolbar stays still.
Manga reading direction reverses the slide. Layout changes do not animate a turn.
