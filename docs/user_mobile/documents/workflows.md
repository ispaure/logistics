# Document workflows

## Receive files from another app

On iPhone or iPad, choose **Share → Logisticks**, wait for the receiving result,
then tap **Done**. Open Logisticks and browse **Workspaces → Local → Received Files**.
**Browse All Files** also shows **Received Files** beside **Local**. In Apple's
Files app the same folder is **On My iPhone/iPad → Logisticks → Received Files**.
The share extension saves attachments while the main app is closed; the main app
publishes complete handoffs into Received Files when opened.

On Android, share one or more files to **Logisticks**, wait for the result, then
tap **Open Logisticks**. Find them under **Workspaces → Local → Received Files**,
**Browse All Files → Received Files**, or the **Received Files** browser location.
With a selected collection drive, the folder is `<drive>/Logistics/Received Files`,
beside `Local` and `LocalCrypt`. With app internal storage selected, it remains
private to the app. Received Files follows the collection drive; when that drive
is unavailable, completed incoming handoffs wait in app storage until it returns.

The app uses the name **Received Files** on both platforms. On iOS this avoids
the system-owned `Documents/Inbox`, which apps cannot write to. Existing legacy
Inbox contents are copied and verified into Received Files, with the originals
retained. If Received Files already contains items, the legacy tree is kept in a
**Previous Inbox** subfolder (numbered when needed), preserving both sets of files.

Files are copied; the originals stay in the sending app. Existing received files
are preserved and duplicate names receive a numbered suffix. Unsupported or
unreadable attachments show a failure result; share those files again. Cancel
stops remaining work and retains files already received. This first receiving
flow lands in ordinary, unencrypted Received Files storage; use the app's file actions to
organize files afterward. Select a received file and choose **Move…**, browse a
writable destination, optionally create a folder or edit the name, then tap
**Move here**. Existing destination files are preserved; moving encrypted files
to ordinary storage requires confirmation. It does not choose an encrypted destination inside
the share sheet. Developer iOS builds require the app and extension's matching
App Group provisioning; see [mobile preparation](../../development/mobile-preparation.md#incoming-files-and-inbox).

Move and Rename keep open text documents and their unsaved edits. Moving a
folder also updates its open text documents. The operation moves the saved
file; your next **Save** writes the draft at the new location. A conflict or an
external change preserves your draft and reports the problem. Close an affected
non-text/read-only reader, or a document open in another window, before moving
it. Changing between plain text and Markdown by renaming also requires closing
the document first. If a move finishes but its editor cannot reopen the result,
keep the draft and use **Save As** after inspecting the destination.

## Document workflow

The app opens on **Home**, a landing page with Open/New actions and five recent
files. **See all in Documents** opens the full document workspace. The house icon is the first native destination, before
**Workspaces**, **Documents**, **Chat** and **Settings**. **Workspaces** separates ordinary Local files, Cloud and Home Server into source tabs, with available copies grouped under their owning source.
If folder discovery fails while credentials change, Workspaces shows an error
with **Refresh**, **Browse local files** and **Connections…**. Retry there after
the connection is ready; restarting the app is unnecessary.
Tap a folder to browse its preferred available copy directly. The **•••** button
beside a folder opens its Browse Local/LocalCrypt/Remote, Pull, Push and management
actions. The main Browse action is prominent; Delete local folder is separated
and uses destructive styling. Pull/Push direction is shown for mapped copies.
Deletion still requires confirmation, and Push retains its existing review. Local browsing uses app-managed files rather than
the entire device filesystem. Choose **New document** from Home. Enter a file
name and select **Plain text (.txt)** or **Markdown (.md)**, then tap
**Choose location…**. The selected extension is added when needed. Choose the
destination folder in Local, All files, Received Files or an unlocked LocalCrypt
location, then tap **Create document**. New documents start empty in that browsable
folder; LocalCrypt stores them encrypted. No private app-storage destination is
offered. Cloud locations remain read-only; use reviewed Push to upload changes.
**Cancel** before creation creates nothing.
**Open file** from Home or Documents opens a browser. Use the folder arrow to go
up; at the root, Back returns to the hub. Android Back first clears search or
retraces visited folders, then returns to the hub.
Books and comics are available through Workspaces or Documents’ **Open Books & Comics library**;
Chat has its own bottom navigation button between Documents and Settings. Native tab
controls adapt to the Apple layout; Android uses bottom navigation in compact
windows and a rail at 600 dp or wider. Switching destinations retains each
screen. **Workspaces** returns to the folder list and **All documents** returns
from the editor to the Documents hub.

Back returns through screens within the current destination. It does not switch
tabs or close a document. iOS uses its native navigation stack and Back control;
Android uses the lifecycle-owned AndroidX Back dispatcher. At a destination root,
Android yields Back to the system. Existing save/checkpoint failures block a
Back action that would leave the screen.

The Documents hamburger lists configured Comics Library folders. Documents lists
open, recent and other saved documents; Home provides Open/New actions.

Choose a document from **All open** in Documents or **Recent** on its main page,
or use **Actions → New document**. Edit its name in the name field and
its contents in the text area. For a document created in a chosen folder, **Save**
writes edits to that file; LocalCrypt saves stay encrypted.
Text, source files and Markdown share the native source editor. Markdown can
show a live formatted preview while you edit. See [Text and Markdown](documents.md#text-and-markdown).

History retains ten recent files. Home shows up to five, including open files;
**Currently open** identifies an existing session and selecting it resumes that
session without reloading its file. Documents lists open files once in **All open**,
with the active one first and a Close button beside each. Its **Recent** section
shows closed entries. **Saved documents** includes other saved text and Markdown
files, including files older than Recent. Search filters these three lists by name.
Reopening a file from Home or Recent shows a small activity bar and an
**Opening file…** status below the current view. Cloud files show
**Opening cloud file…** while credentials are checked and any required download
finishes. The indicator clears when opening finishes, fails or is cancelled.
Home and document lists show names and useful status badges without a separate
file-type subheader. **Unsaved changes** and **Draft** badges mark pending edits. **Recovered draft**
marks edits restored from recovery; saving clears these badges.

Each open text/Markdown document owns its editor and draft. **New**, opening a
stored document, and successful imports add it to **Documents → All open**;
opening the same stored identity again activates it. Documents with the same name
remain separate. Switch using All open or Recent. Closing a document keeps
its stored data; the ten most recent eligible files can be reopened from Recent. Disk, cloud and
padlock icons beside names in Open and Recent show each source and
connection lock state. Local files and files using saved credentials retain ordinary history entries.
Password-protected session-only credential ZIPs instead protect their open and
recent entries in a separate AES-256 ZIP with the same password. Unlocking the
matching credential restores those list entries; selecting one loads its file on
demand. The cache contains no document contents or unsaved edits. Forgetting the
credential deletes its encrypted lists in every window.
**Close** removes an item from that list without deleting its stored document.
To remove an app-stored text or Markdown document completely, open its three-dot
**Document actions** menu and choose **Delete document…**. This is also available
in Markdown preview. Confirm the warning to remove its saved content, recovery
copy and Recent entry, including any unsaved changes. Cancel keeps the document.
Other app windows must be closed first.
Closing an edited document opens a native popup with **Save**, **Quit without
saving**, and **Cancel**. Save writes the changes and closes the document;
Cancel keeps the exact screen and edits. Quit without saving discards edits
without deleting the saved file. Discard resets recovery to the current saved
file without overwriting external changes or recreating a deleted file.
A failed save or conflict keeps the document open; use **Save a copy** to preserve
both versions. The same choices apply to private documents and metadata edits.
The document's three-dot menu omits New, Open from Files, Import and Close;
use Home to create/open files and the document's **×** to close it.
**Delete document…** is red and opens a native destructive confirmation with
**Delete** and **Cancel**.
**Close saved documents on restart** is enabled
by default in Settings. On restart, saved text and reader sessions leave All open,
except the last active document when **Restore last document** is enabled;
stored files and reading progress remain available. Unsaved text,
conflicts and unreadable recovery entries stay in the open list. Turn this setting
off to retain all ordinary open items at the next launch. There is a maximum of
32 open items. An empty workspace stays empty until you create or open a file.
**Restore last document** opens and displays the last active ordinary text document,
EPUB or comic at startup, with its saved reading position. Turning it off starts
on Home and prevents automatic EPUB/comic reopening.
You can still explicitly reopen those readers from Open with their saved
progress. Session-only documents, including documents loaded using session-only
credentials, are excluded from automatic restoration. Native cursor/selection and scroll offsets are recorded for text views.
Opening an item from the open/stored list also resumes its Edit or Preview mode.
Back to the editor selects Edit for that document.
If a restored item is unavailable, **Try again** retries it and **Remove from
open documents** removes only its open entry. Stored files are preserved.

On regular-width Apple layouts, native split navigation keeps the document list
beside its detail view. Android shows both at 640 dp or wider and uses the
compact route stack below that threshold. Layout changes retain the same editor
and session. The editor keeps its name, text, status, Save and Preview visible;
**Actions** opens a native Apple button menu or Android popup for New, Import,
Open from Files, Save a copy, Save As, Export and Close.

**Save As** uses the file browser: select a storage location, tap folders to
navigate, and use Back or search to find the destination. The filename and
**Save here** action stay below the list. **New folder** creates and opens a
folder without changing the filename. Tapping an existing file copies its name
without saving; a search result also selects its containing folder. Saving to an existing filename asks for confirmation before
replacement; cancelling preserves the draft and destination screen. If that file
changes while confirmation is open, replacement fails and preserves its contents.
For a bare name such as `Notes`, Save As keeps the source extension (`Notes.md`
for a Markdown source); a draft without a supported extension uses `.txt`.
The resolved filename appears above the destination. An explicit supported
extension is kept; invalid names or unsupported extensions keep the draft open
for correction. Local files are plaintext; LocalCrypt destinations remain encrypted.

When the keyboard leaves little room, the picker focuses on the filename and
completion controls. The chosen destination remains in the form, and errors can
be scrolled into view. Dismissing the keyboard restores the same folder listing.

**Preview** renders common Markdown offline: tables, headings, nested bulleted
and numbered lists, quotes, bold/italic/strikethrough text, rules, line breaks and
inline/fenced code. Wide tables and code blocks scroll horizontally inside the
page. Raw HTML is escaped, links are inert, and scripts/images/network resources
are blocked. Documentation additionally supports local page links and heading anchors.
Rendered HTML is limited to 2 MiB. **Back to editor** returns to the same draft.

**Export…** opens a destination picker and exports the current draft as a copy,
retaining its encoding and line endings. It does not save over the original
imported document or mark the private draft saved. Android uses a new document
request; iOS uses an export-copy picker. Cancelling preserves the document.

**Import…** opens Android's document-provider picker or iOS's document picker.
Logistics reads the selected document into a private copy. Editing or saving that
copy does not change the source file. Imports are limited to 1 MiB of text;
unsupported/binary data and unavailable permissions produce an error. Files with
UTF-8 or recognized Unicode byte-order marks retain their encoding and original
line-ending style when saved.

Draft contents and valid name changes are checkpointed during editing. Reopening
the app restores saved documents and available unsaved drafts. A malformed
recovery record is preserved and reported. If a private stored file changed or
disappeared while a draft existed, normal saving refuses to overwrite it.
**Save a copy** preserves the recovered text as another private document.

The prototype's controls have 44-point layout targets and use native
platform text fields, selection and keyboard behavior. The draft is also
checkpointed when the main window loses focus and during a normal exit. These
hooks supplement checkpoints made while editing; forced termination does not
require an exit callback to have occurred.

External sharing and editing the original provider document are not
implemented. EPUB/comics use the private library described below. Native picker grants, keyboards and suspension need testing
on devices before treating this prototype as a supported mobile product. See
[build and validation instructions](../../development/mobile-launchers.md).
