# Read and manage comics

Browse comic libraries, read CBZs, edit metadata, convert CBRs and compress comic
pages. Comic tools belong to **Books & Comics** in Settings. Enabling that feature
also enables its Images dependency.

## Open a library

Select a configured comics folder on **Known Folders** and choose **Open Comics Library…**.
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

To package comics inside a separate outer ZIP, use [Archives](../../archives/user_docs/index.md).

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
