# Logistics on mobile

## Current feature support

Android and iOS have the same prototype scope. “Implemented” describes code in
the native app; real-device interaction testing is still required.

| Logistics capability | Mobile status |
| --- | --- |
| Plain-text editing | Implemented: create, select, rename, edit and save private documents |
| Hub and navigation | Native Home, Files, Documents and Settings destinations; retained screen per destination |
| Markdown | Text editing and offline basic preview: headings, list items, bold and code blocks |
| Document import | Native picker adapters implemented; actual provider permissions still need device testing |
| Draft recovery | Implemented: checkpoints, restored drafts and conflict-safe save-a-copy |
| Encoding and line endings | Implemented for UTF-8 and recognized Unicode BOMs, with a 1 MiB text limit |
| EPUB and comics | Private library, EPUB chapter navigation and PNG/JPEG/WebP CBZ/ZIP pages, saved progress and bookmarks |
| Preferences / INI settings | Private INI with font size and last-document restore controls; no desktop preference migration |
| Export | Export a copy through the platform destination picker |
| Share or save back to the original document | Not implemented |
| File browser | Shared native list/tile views, thumbnails and file information for app-managed Local/LocalCrypt files and remote browsing |
| Bulk rename, IDE and Git/Perforce UI | Not ported |
| LM chat | Native text conversations, configured server/model, streaming/cancel, private history and Markdown export |
| rclone remote files | Credential ZIP import, ordinary downloads/export, LocalCrypt encrypted offline reading/editing, local folder management and Save As; encrypted saved or session-only credentials |
| Media/image tools, archives and other desktop integrations | Not ported |

## Preferences and storage

Developers can update Logistics on a paired iPhone over Wi-Fi using the
[local deployment workflow](../../../Mobile/README.md#build-and-deploy-to-a-paired-iphone-over-wi-fi).
Its launcher builds, installs in place and opens the app while retaining its
bundle and signing identity. Keep the iPhone unlocked on the same Wi-Fi as the
Mac. Do not uninstall Logistics to fix deployment errors: uninstalling removes
its private documents and preferences.

INI is a usable format on both mobile platforms. Bundled defaults must remain
read-only, while personal overrides belong in the app's private persistent data
directory. The shared settings API accepts explicit default/override paths and
rejects automatic desktop settings paths on mobile. This host uses immutable
in-code defaults and an app-private `preferences.ini`. **Settings** controls the
editor/preview font size and whether the last selected document is restored.
Reads do not create the INI; saving does. Invalid files are preserved and defaults
are used; saving refuses to overwrite them. Reload after repairing or moving such
a file. Concurrent external edits also require reload. Home remains the launch
screen; restoring a document makes it ready under Documents.

Desktop preferences cannot simply be copied wholesale: filesystem paths,
external executable locations and desktop-only options need validation or
platform-specific replacements. Document-provider access is a permission-bearing
platform handle rather than an ordinary path stored in an INI. Preferences
migration and general app-data backup/reset behavior remain separate work.

## Home panels and document search

Home uses icon panels for Files, Documents, Text & Markdown, Books & Comics and
LM Chat. Panels stack on phones and use two or three columns in wider windows.
**Continue** returns to the selected open document, including its Edit/Preview
mode. **New document** creates and displays a separate editor; **Open file…**
opens the existing Local/LocalCrypt file picker. Documents has the same launch
panels plus open and stored document cards. Open cards show document type,
unsaved changes, session-only status and known conflicts. Closing an open card
uses the existing save/discard workflow and keeps its stored file.

The ordinary text/Markdown editor offers **Find** beside Save and Preview.
Search is literal, wraps through the active document, and supports **Match case**,
**Replace** and **Replace all**. Replacement text is literal too. Search controls
belong to each editor, so switching documents keeps their separate queries and
drafts. **Done** hides the controls. Replacements update the draft and use the
same checkpoint and conflict-aware save behavior as typing; press Save to publish
them. Search does not include other files or the separate private reader editor.

## Document workflow

The app opens on **Home**, a landing page with quick access to files, editors,
books/comics and chat. The house icon is the first native destination, before
**Files**, **Documents** and **Settings**. **Files** is a location hub for **On this device** and
**Remote files & LocalCrypt**. Local browsing uses app-managed files rather than
the entire device filesystem. Choose **Documents**, then **Text & Markdown**.
The Documents hub also contains **Books & Comics** and **LM Chat**. Native tab
controls adapt to the Apple layout; Android uses bottom navigation in compact
windows and a rail at 600 dp or wider. Switching destinations retains each
screen. **Locations** returns to the Files hub and **All documents** returns
from the editor to the Documents hub.

Back returns through screens within the current destination. It does not switch
tabs or close a document. iOS uses its native navigation stack and Back control;
Android uses the lifecycle-owned AndroidX Back dispatcher. At a destination root,
Android yields Back to the system. Existing save/checkpoint failures block a
Back action that would leave the screen.

Choose a document from **Open documents** or **Stored documents** in Documents,
or use **Actions → New document**. Edit its name in the name field and
its contents in the text area. **Save** publishes the edited file inside the app.
Text and Markdown use the same plain-text editor.

Each open text/Markdown document owns its editor and draft. **New**, opening a
stored document, and successful imports add it to **Documents → Open documents**;
opening the same stored identity again activates it. Documents with the same name
remain separate. Switch using the open or stored lists. Closing a document keeps
it available in Stored documents.
**Close** removes an item from that list without deleting its stored document.
For an ordinary unsaved document, choose **Save and close**, **Keep draft and
close**, **Discard changes and close**, or **Cancel**. Retained drafts remain in
Stored documents. Discard resets recovery to the current saved file without
overwriting changes made outside the editor or recreating a deleted file. A
failed save or conflict keeps the document open; use **Save a copy** to preserve
both versions. Session-only drafts offer Save, Discard, and Cancel without durable
draft retention. Ordinary open items remain available at the next launch, with a
maximum of 32 open items. Their active selection resumes when **Restore last
document** is enabled; turning it off also prevents automatic EPUB/comic reopening.
You can still explicitly reopen those readers from Open documents with their saved
progress. Private resource restoration remains excluded. Native cursor/selection and scroll offsets are recorded for text views.
Opening an item from the open/stored list also resumes its Edit or Preview mode.
Back to the editor selects Edit for that document.
If a restored item is unavailable, **Try again** retries it and **Remove from
open documents** removes only its open entry. Stored files are preserved.

On regular-width Apple layouts, native split navigation keeps the document list
beside its detail view. Android shows both at 840 dp or wider and uses the
compact route stack below that threshold. Layout changes retain the same editor
and session. The editor keeps its name, text, status, Save and Preview visible;
**Actions** opens a native Apple button menu or Android popup for New, Import,
Open from Files, Save a copy, Save As, Export and Close.

**Preview** renders basic Markdown offline. Raw HTML is escaped, links are inert,
and scripts/images/network resources are blocked. It supports headings, list
items, bold and fenced code, rather than the full desktop Markdown renderer.
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
[build and validation instructions](../../../Mobile/README.md).

## Books and comics

From Documents, choose **Books & Comics** and **Import book/comic…**. EPUB and
CBZ/ZIP imports create private copies; the selected source is never
changed. Choose a library item and **Open selected**. Previous/Next and the
chapter/page selector navigate the book's reading order. EPUB pages scroll in the
native web view; comic images fit the native image area. The EPUB view follows
system light/dark appearance and uses the configured font size.

Standalone password-protected CBZ/ZIP comics support AES and legacy ZipCrypto
on iOS and Android, without rclone or a credential package. Import one through
Files, then enter its ZIP password and choose **Unlock comic**, or press Enter.
A wrong password clears the field and keeps the prompt ready for another attempt.
**Cancel** keeps the imported encrypted copy. The password stays only with the
active reader; **Lock comic** clears the password, decoded-page cache and displayed
pages. Opening after locking or restarting asks again. The library keeps the
original encrypted archive bytes and never writes an extracted/decrypted archive.
ZIP member names remain visible, as they do in ordinary password-protected ZIPs.

Progress remembers the current EPUB chapter or comic page, rather than an exact
scroll position inside a chapter. **Bookmark** / **Unbookmark** toggles that
chapter/page; the bookmark selector returns to saved positions. Comic pages use
natural filename order. Right-to-left manga metadata is identified; single-page
Previous/Next controls still refer to reading-order positions.

Ordinary CBZ/ZIP comics stream into the private library without a fixed archive
or total decompressed-size cap. Reading seeks archive headers and fetches only the
chosen page. Both EPUB and comic archives are limited to 5,000 entries; EPUB
imports retain the 256 MiB archive/expanded-total and 8 MiB per-member limits.
Native comic images must be PNG/JPEG/WebP,
no larger than 8 MiB or 16 megapixels, with each dimension at most 8,192 pixels.
Static lossy, lossless and transparent WebP pages render directly at their original
resolution; archives are preserved. Animated WebP is not supported. Comics with
other page formats are rejected rather than silently skipping pages.
EPUB chapters and rendered HTML are limited to 2 MiB. Small PNG/JPEG/WebP illustrations
(up to 256 KiB each, 1 MiB total) are embedded; unsupported/large illustrations
show an omission label. Raw scripts, forms, embedded objects, source styles and
external resources are removed. Chapter links are inert; use the chapter selector.
DRM, standalone encrypted EPUBs, CBR/RAR and fixed-layout SVG books are not supported.

Imports hash bytes during their streamed copy. The checksum is verified on
opening after a restart; reopening an unchanged file in the same session reuses
a bounded revision-keyed verification cache. Changed files invalidate it, and
individual page reads reject concurrent changes. Re-import a changed private copy as a new entry. Malformed
library records are preserved and reported. Progress/bookmark writes reject stale
records rather than overwriting another change.

## LM chat

Choose **LM Chat** from Documents. Open **Server & generation settings…**, enter your
existing server's API URL (for example `http://192.168.1.10:1234/v1`), optional
session API key, and model ID. **Refresh models** contacts that server explicitly
and fills the model selector. Use the computer's LAN address/hostname when the
server is on a computer: `localhost` on a phone means the phone itself. HTTPS
protects requests and credentials; HTTP sends them unencrypted. TLS verification
is enforced for HTTPS, and redirects are refused. iOS declares the local-network
purpose; physical-device permission behavior still requires validation.

Choose context tokens and maximum reply tokens, then **Save configuration**.
These settings, URL and model persist privately. API keys remain in memory for
this app session and are not written to configuration or conversation fields.
Re-enter a required key after restarting. Opening chat alone makes no request.

**New conversation** starts a private thread. Drafts are checkpointed while typing.
**Send** streams a text reply and preserves partial progress during generation.
**Cancel** stops the connection and retains received text with cancelled status.
Reopening an interrupted streaming record identifies it as interrupted. Failures
retain the user message/partial reply; no automatic retry occurs. The selector
reopens saved conversations. Malformed, oversized or concurrently changed files
are preserved, and saving reports the problem. Export can preserve a current
valid in-memory copy before reopening a conflicting file.

Requests reuse the desktop whole-turn context budget: older completed turns may
be omitted, with their count shown during generation. Server token limits remain
authoritative. Mobile limits are 200 text messages per conversation, a 64 KiB
character draft, 2 MiB per stored record, 256 KiB per reply, 64 KiB per server event
and 1 MiB per request. Reads time out after 15 seconds without data; generation
has a ten-minute upper bound. Models lists are bounded to 128 IDs / 512 KiB.

**Export conversation…** writes UTF-8 Markdown through the platform export-copy
picker, subject to its 1 MiB limit. Conversations use the desktop LM domain/schema,
but mobile currently supports text-only Chat mode: no screenshots, project Code
mode, model tools, folders, or desktop conversation import UI. Model tool calls
are rejected rather than executed.

## Remote files and credential ZIPs

Choose **Remote files & LocalCrypt** from Files. Credential setup is under
**Settings → Remote connections** (also reached through **Manage connections…**
in the remote browser). The native app embeds rclone 1.74.1; no desktop
executable, shell, mount, or separate RC server is required. **Check rclone engine**
performs an offline in-memory read and displays the engine version.

Tap **Choose credential ZIP…** and select your existing Logistics credential
package. Its filename appears under the button. Enter its password, then tap
**Load remotes** beside the password field, or press Return. Leave the password
blank for an unencrypted ZIP. A failed load clears the password and keeps the
selected ZIP ready: correct the password and tap **Load remotes** again without
selecting the file again. After loading, choose a remote and tap **Browse folder**.
The ZIP password is never saved; selecting a ZIP alone does not load credentials
or connect to a remote. TXT entries must each contain one `[Remote name]`
section and rclone settings, including `type`. Plain, ZipCrypto and WinZip AES
packages are readable; importing never extracts files or modifies the source ZIP.
ZIPs are limited to 1 MiB, 64 entries and 256 KiB per TXT entry. Duplicate remote
names, unsafe archive paths and unsupported settings are rejected before replacing
the previously loaded session. Loading a valid package replaces that session's
remote list; it makes no remote connection by itself.

This first mobile adapter includes Google Drive, Dropbox, OneDrive, S3 and WebDAV,
plus the memory backend used by the offline diagnostic. Existing authenticated
settings are required. It accepts a deliberately limited set of backend settings;
local paths, scripts, service-account files, mounts, alias wrappers and
other backends are not currently supported. WebDAV URLs and custom S3 endpoints
must use HTTPS. Certificate verification stays enabled. A single crypt layer over
one supported backing remote is available for [LocalCrypt reading](#localcrypt-encrypted-offline-reading).

Choose a connection and tap **Open remote**. **Connections…** opens credential
setup. Tap folders to open them; **Back** in the browser returns through successful
folder visits. **Locations** returns to local and remote locations. Choose a file
and tap **Copy to device…**, or open a folder and tap **Copy this folder…**.
The copy screen shows the source and a browsable **On this device** destination.
Open a destination folder and tap **Copy here**; no path typing is required.
Existing files are preserved, with a separate copy name when needed.
**Open copied location** opens the result in the local browser and selects a
copied file so **Open file** is immediately available.

The progress bar tracks bytes for the current file when its size is known,
with an animated bar when the size is unavailable. Folder copies also show the
number of completed files. **Cancel** stops the transfer; unsuccessful transfers
do not publish a partial copy. The bar reaches 100% after the copy is published.
Folder copies preserve empty folders and are limited to 10,000 items. Each folder
copy gets a separate name to preserve previous copies and local edits.

Crypt sources show an explicit **unencrypted copy** notice before copying.
**Actions → Encrypted offline copies…** provides encrypted LocalCrypt downloads.
**Actions → Downloaded copies…** retains the older private-download workflow,
including **Download** / **Download decrypted**, opening and system export.
The mobile bridge copies from remote to device; uploads and remote rename/delete
are not implemented. Individual network reads have a 15-second timeout; browsing
has a two-minute deadline and transfers have a 30-minute deadline. Cancellation
may wait for an upstream network call to return.

**Search** searches names in this folder and its subfolders in the background,
up to 10,000 scanned entries and 1,000 displayed results. Sort by name, size or
modified time; folders remain first. Changing folders clears search, and hiding a
selected file clears its copy selection. Failed navigation preserves the prior
listing and history.

Select a private download and choose **Open private copy** to import it into the
text/Markdown editor or EPUB/CBZ library, subject to those readers' existing format
and size limits. Other/bigger files can use **Export private copy…**, through the
system destination picker, streamed without a fixed whole-file size cap. Repeated downloads produce separate private
copies; incomplete copies are excluded from the selector after a restart.

**Save credentials on this device** is enabled by default. Turn it off before
importing to keep credentials only in memory for this app session. A session-only
import leaves any previously saved package unchanged; **Reload saved credentials**
returns to that package. One saved package is supported at a time. Its ZIP filename
appears above the remote selector, so the package and its remote names stay associated.

Saved settings and refreshed OAuth tokens use an AES-256-GCM encrypted private
vault. Android Keystore protects its key, and the files are outside Android backup;
iOS Keychain stores a device-only key available while the device is unlocked, and
the vault folder is excluded from backup. Credentials restore when Remote files
opens, without contacting a remote. The ZIP password is never saved, and neither
mode rewrites the source ZIP. A locked device, missing key or damaged vault stops
restoration; there is no plaintext fallback or silent replacement of saved data.
Unlock the device and reload, or use **Forget saved credentials** before reimporting.

**Forget saved credentials** unloads the active session and removes the saved
ciphertext and its known protected key while preserving private downloads. Private
downloads follow the platform's normal app-data backup policy. Interactive OAuth
account setup remains future work. Session-only token updates are lost on exit;
providers that rotate refresh tokens may require a fresh credential package.

## LocalCrypt encrypted offline reading

Mobile can browse an rclone crypt remote whose direct backing remote is supported
and included in the same credential ZIP. Import/unlock the package in **Remote
files**. Under **Choose remote · tap the name below**, tap the currently displayed
remote name to open the picker and select your crypt remote, then tap
**Browse folder** to see decrypted names. The hint below the picker identifies
available crypt remotes and confirms when a crypt is selected. If it reports
no crypt remote, the loaded ZIP must include both the crypt configuration and
its backing remote configuration; choosing only the backing Dropbox/Drive/etc.
remote does not apply crypt decryption.
Choose a file and **Download encrypted copy**. The app saves the original rclone
ciphertext under its private LocalCrypt storage; it does not save decrypted content
or add a plaintext filename to the copy's record. Filename privacy still depends
on the crypt remote's filename-encryption settings.

Remote browsing and unlocked copies show decrypted names. **Manage local files
and folders** opens a local browser with **Local files** and existing
**LocalCrypt** copies. **List** and **Tiles** use the same shared browsing
model as desktop. Visible PNG/JPEG/WebP images and comic/EPUB covers load in the
background, with a bounded memory cache. Select a file to see its name, size and
modified time, plus available comic/EPUB metadata below the entries.
The storage picker and **Parent folder** are visible directly in the local browser.
Changing storage opens its root. Navigation supports tapping folder entries, **Parent folder** and **Back** through
successful folder/storage visits. **Search** opens a full-width field and searches this folder and its subfolders
in the background; scans stop after 10,000 entries and report incomplete results; sorting supports natural name order, size and modified time in either
direction, with folders first. A failed folder load preserves the previous
listing and history. Searching reads folder listings, without reading file contents. Closing search
restores the current folder listing. Use **Inner
archive password** and browse again when a protected comic or EPUB needs its own
password for covers or metadata. File-name browsing and moves do not need this
inner password. Browse a folder, then create a folder, rename, delete
or move the selected item. For a move, select the destination storage and enter a
relative path including the final file/folder name; its parent folder must exist.
Moving into LocalCrypt encrypts the content and names according to the remote's
settings; moving out creates decrypted Local files. Inner ZIP passwords remain
unchanged. These actions affect app-private local storage, not cloud originals or
arbitrary folders owned by another app.

To organize an older offline encrypted copy, select it on the Remote files screen,
open the manager and choose **Use selected offline encrypted copy**. Choose a
private download similarly with **Use selected private download**. Existing copies
are preserved until their transfer succeeds. Managed crypt files can be read and
edited directly, including their comic/EPUB metadata.

Text/Markdown editors offer **Open** and **Save As** through one storage browser
for app-managed Local files and unlocked LocalCrypt folders. Choose storage, browse
a folder and select a decoded filename, or enter a new name for Save As. Use
**Browse folder** after changing storage or typing a folder. Folder taps, **Back**,
search and sorting use the same shared browser controls as the file manager. There is no separate
decryption action. Drafts opened this way stay in memory, including local exports.
Saving an ordinary document into LocalCrypt removes its active recovery draft;
previously saved plaintext originals are preserved.
A successful Save As preserves the original and switches subsequent saves to the
new file. Save As and moves refuse existing destination names. Deletion is
permanent and asks for confirmation. Cross-storage moves verify the destination
before deleting the source; interrupted cleanup can leave both copies or remaining
source entries. Refresh and inspect them before retrying. Transfers stream their
contents; text editing and saves retain the 1 MiB buffer limit.

Choose **Refresh encrypted copies**, select a copy and **Read encrypted copy**.
Once downloaded, reading works offline while the matching credentials are loaded.
After restarting, reload saved credentials or import the same package again.
Copies with unavailable credentials are shown as locked. Forgetting credentials
preserves ciphertext copies, closes the private reader and removes its displayed
content. **Close private reader** releases the reader's in-memory content.

The private reader/editor is separate from Documents and the book library. It
supports text/Markdown editing, EPUB chapter text, and PNG/JPEG/WebP comic pages in
CBZ/ZIP archives. For a password-protected archive inside LocalCrypt, enter its
password in **Inner ZIP password (if needed)** before opening. Both AES and
traditional ZIP passwords are supported; the password is not saved. Choose a
page/chapter, then **Read selected page**.

Edit text or Markdown and choose **Save encrypted copy** to replace the encrypted
local file. Encoding, BOM and line endings are preserved. Saving does not upload
anything. Failed saves retain your edits. **Close private reader**, credential
changes and app exit keep unsaved edits open until you save or choose **Discard
changes and close**. **Return to private reader/editor** resumes an open editor.
Unsaved edits remain in memory and cannot survive an app crash or forced exit.

The private reader creates no document recovery file, reading-position record,
saved bookmark record, plaintext export or thumbnail cache. Its tools offer
**Bookmark** and a bookmark selector for comics and EPUBs. These bookmarks remain
in memory while switching documents and are cleared when the session closes.
Markdown is edited as source text, with an offline preview. Folder transfers use
the Files folder actions described below.

For a LocalCrypt comic or EPUB, choose **Edit metadata…** in the private reader,
change the fields and choose **Save encrypted metadata**. EPUB fields include title,
authors, language, publisher, tags and description; authors and tags use one value
per line. Comic fields use ComicInfo metadata, including title, series, number,
credits and tags. PageCount is preserved rather than manually changed.

Saving preserves pages, chapters, covers and unrelated metadata. Inner ZIP
passwords remain in effect, and are kept only for the open reader session. Existing
untouched archive entries are copied intact; rewritten protected metadata uses
AES-256 with the same password. No plaintext backup or metadata recovery file is
created. Conflicts, incorrect passwords, cancellation and failed verification keep
the original encrypted copy. Failed saves keep your edits in the form. **Back to
reader** keeps the form draft; **Discard changes and close** explicitly discards it.

Encrypted downloads, moves, reads and metadata rewrites have no fixed whole-file
size cap. Archive headers and individual members are read as needed; metadata
verification streams every member. Text editing is limited to 1 MiB, archive
member reads to 16 MiB, and comic pages to
8 MiB and 16 megapixels. Damaged ciphertext and mismatched crypt settings fail
without producing a plaintext file. The app does not promise secure erasure of
RAM or change the device's normal app-data backup policy. A saved credential vault
protects keys/settings separately from these rclone-encrypted document copies.

If a move saves the verified destination but source cleanup stops, the message
identifies that partial result. Refresh both locations before retrying cleanup;
do not repeat the entire move. A save completed just before cancellation still
counts as saved. If its new revision cannot be read, reopen the saved file before
continuing to edit; the current draft remains available.

Save As keeps the original draft until the saved destination has been reopened
successfully. If reopening fails after a verified save, the message says the file
was saved and retains your draft. Inspect that destination before retrying Save As
with the same name.


Save As keeps the original reader and draft until the new editor has been built
and displayed. A failure to construct or show it does not discard the original
buffer; the destination may already have been saved, so inspect it before retrying.

If another operation changes a newly saved destination before it is reopened,
Save As keeps your original draft and reports the saved-but-not-reopened state.
Inspect the destination before retrying; it is not silently overwritten.


Library items also appear in Documents' open list. Opening an already open book
returns to its existing session. Each book owns its reader; switching books
releases the inactive decoder and rendered content, and reopening resumes stored
reading progress. Closing removes the open session and keeps the imported book.
Password-unlocked comics are excluded from workspace restoration.


### Open provider and private documents

Files opened from local or LocalCrypt folders now have separate entries in
**Documents → Open documents**. Up to four provider items may remain open,
including independent text edits and metadata forms. Opening the same resource
returns to its existing item. Browsing folders or switching destinations keeps
these edits in memory. Ordinary imported documents remain independently open.

Private Close offers **Save and close**, **Discard and close**, and **Cancel**.
Failed saves retain the item and its edits. Credential reload, replacement and
forget check all unsaved provider items before clearing any of them. Save or
explicitly discard private work before a file mutation or credential change.

Provider items are session-only: their titles, paths, content and positions are
excluded from workspace recovery. Reopen/unlock them after process termination.
The four-item and 32 MiB retained-input limits reject a new item without evicting
existing drafts. Inactive comic images and archive caches are released and
recreated on activation. Saving local text updates its local file; LocalCrypt
continues to save encrypted bytes through the existing verified transaction.


### Repeatable folder pulls

Earlier mobile versions offered **Save repeatable folder pull**. New transfers use **Pull…** and the sync engine below. Legacy copy jobs remain readable through their compatibility route. This downloads
a complete local copy and adds a job under **Files → Folder pulls**. **Refresh**
fetches the current remote contents. It never uploads or deletes remote files.

If the local folder is unchanged, Refresh keeps its previous version in a
separate `-previous-…` folder and updates the original local folder. If you edited,
added or removed local files, Refresh keeps that folder untouched and saves the
remote version in a separate folder. The status identifies the resulting folder;
**Open downloaded folder** opens it. Inspect conflicts before moving files yourself.
Previous versions remain available until you explicitly delete them. **Remove
job** removes only the job, preserving every local copy. Failed/interrupted
publication preserves surviving folders and is reconciled before the next retry.

Ordinary jobs can be reopened after launch with the matching connection. Changing
a connection makes its old jobs unavailable. Crypt jobs stay in this app session
and are forgotten when credentials are cleared; their downloaded copies are
explicitly unencrypted. Up to 16 jobs are supported, with 10,000 items per folder.

Reopening a downloaded copy or imported local book now returns to its existing
document/library identity rather than importing another duplicate.

## Files locations and actions

Files keeps your current folder, selection, list/tile mode, search, sort and browse
history when you visit Documents or Settings. Local and remote browsers give most
of the screen to the listing. Tap a local file to open it, or a folder to browse
it. Search stays visible; **Sort** reveals sorting and list/tile options. The
**•••** beside an item selects that item and opens its commands without opening
its contents. Rename, Move, New folder and archive-password entry have focused
screens. **Details** shows metadata and bounded previews.
Files opened from this browser stay in the Files navigation stack. Native Back
returns to the same folder, search, sorting, selection and scroll position.
Back leaves the reading/editing session open, including unsaved provider text
drafts; reopen it through **Open documents** to continue. Files opened from
Books & Comics or Open documents keep their document navigation instead.
Connection import, reload, remember and forget remain in Settings.

Use **Pin current folder** to add an ordinary local or remote folder to Files.
Remote pins identify the connection, not just its display name; a missing or
changed connection reports unavailable instead of opening another provider.
Encrypted folder paths cannot be pinned for restoration. Remove pin removes only
the shortcut. Malformed or concurrently changed pin records are preserved.

Folder pulls can refresh a local folder repeatedly. Local changes produce a
separate incoming snapshot; they are never overwritten by a refresh. Unchanged
folders can update while their previous copies remain available. Removing a job
keeps all local folders. Remote data is never changed by a folder pull.

## Reader and editor presentation (Phase 3 Part 1)

Open EPUB and comic sessions now give content the main area, with compact page
navigation and an Actions menu for contents, bookmarks, appearance and reading
mode. EPUB reading mode hides those controls and keeps a visible Restore controls
button. Comics open with controls hidden and zero page margins; tap the page to
show or hide reading controls. Native navigation bars hide with comic controls
and return when controls are shown or when leaving the reader. EPUB appearance offers supported font sizes, margins and system/light/dark
colors without changing the current chapter. Progress remains chapter/page based.
Fit comic pages remain centered after leaving and reopening a reader or repeatedly
showing and hiding controls; zoomed pages retain bounded pan and zoom behavior.
Fullscreen reclaims the navigation area on both platforms, including Android's
title bar. Transfer banners appear with reading controls and stay hidden during
immersive comic reading; this does not pause transfers in the background.

Comic pages use native pinch zoom and panning on iOS and Android. Fit page resets
zoom; swipe left for the next page and right for the previous page at fit size.
Manga reverses those directions. Swipes stop at the first/last page without an
error. While zoomed, dragging pans the page and does not change pages. Swipes
leave the outer edge available for system navigation. Private comic pages
use the same presentation while their content and position remain session-only.

Text actions offer Preview beside editor in wide windows. The preview stays beside
the editor at widths of at least 1100 points and collapses in narrower windows;
the preference belongs to that document session. Compact Edit/Preview remains
available. Both previews retain the existing offline renderer restrictions.

Simulator/emulator checks exercise zoom, fit, page direction, reading-mode restore,
appearance and session ownership. Physical pinch/Back gestures, screen-reader
interaction and large-text usability still require device evidence.

## Independent iPad windows (Phase 4 Part 1)

On an iPad that supports multiple scenes, Settings offers **New window**.
Each window has its own open documents, active selection, routes and presentation.
A secondary window starts with a separate document. An item already open in
another window cannot gain a second writer; close it there before opening it here.
Ordinary drafts and the selected destination restore with that scene's workspace.
Settings in a secondary window also offers **Close window**; its drafts remain
recoverable and the original window is activated again.

Up to four windows may coexist. Protected content requires one window, and an
open protected session prevents creating another window. Secondary windows offer
ordinary text/Markdown and library reading; Files, transfers, connections and chat
remain in the original window. This keeps private views and connection workers
under one owner. Phone/Duo and Android independent-window controls remain disabled;
Android resizing and split-screen presentation remain available.

System scenes are verified on an iPad simulator. Real-device document pickers,
OS-driven scene eviction, assistive input and physical multitasking still require
separate evidence.

## Folder Hub and Local / LocalCrypt sync

**Files** combines ordinary Local folders, downloaded LocalCrypt copies and loaded
remotes in one name-only selector. A folder such as `Example-Library` appears
once; its action page reflects the copies available. **Browse folder** opens its
local copy when present. **Browse online** opens its loaded remote when both exist.
Existing managed copies remember their storage type and transfer association.
The first pull chooses storage; later transfers reuse it. **Refresh** updates
folder discovery without downloading remote contents.

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
Both storage types belong to the app's private space. Crypt storage choices only
appear when a corresponding copy exists; loading credentials does not imply the
folders are downloaded.

**Pull** makes the local destination match the remote source. **Push…** makes the
selected remote destination match local, after a review showing replacements
and destination-only entries to remove. Files missing from the source are removed
from the destination, within the selected folder. Both operations call the embedded
rclone library's standard Sync routine, with no backup option or new retained
snapshots. Transfers use rclone's normal incremental comparison. LocalCrypt syncs
ciphertext to/from the backing scope; a readable Local copy of a crypt remote uses
rclone's crypt filesystem for automatic encryption/decryption.

**Files → Transfers** shows the destination and offers
**Open**, **Pull**, **Push…**, **Delete local folder…**, and **Remove mapping
(keep files)**. Delete local folder requires confirmation and removes only the
app-private local folder and everything inside it permanently; the online folder
remains. Confirmation appears without scanning the folder contents. Deletion
creates no backup and has no app recovery or undo. Obsolete transfer snapshots
are discarded during deletion or the next transfer; they cannot be opened or
restored. Removing a mapping keeps its local files. A missing or changed connection blocks transfers until you load the
matching credential ZIP.

For session-only connections, `preferences.ini` remembers the ZIP filename and
remote names, without its password or credentials. After restart those remotes
remain discoverable in the Hub; opening one tells you which ZIP to select and
unlock. The ZIP itself must be available through the device picker. Forgetting
credentials also clears these associations. Saved credentials retain the existing
protected-vault behavior.

Transfers show completed and active file counts, discovered entries, checks and
transferred bytes. Known totals can grow as rclone discovers more files; discovery
uses a steady activity indicator until a byte total is available. A zero completed
file count can mean files are still transferring, rather than no work happening.
New copies use the exact remote name (or selected Local subfolder name), without
a random suffix. On the next pull, an older generated suffixed Local folder is
renamed together with its mapping if the destination is free. LocalCrypt keeps its
private account storage and updates its copy label. Conflicting names, including
case-only differences, refuse the pull and preserve existing copies.

Transfers support cancellation. An interrupted sync can leave
completed writes/deletions at the destination, just like CLI rclone sync; retry
uses the same recorded location. Other ordinary documents remain usable while
sync runs. Save or close provider edits before syncing their local files. Transfers
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

## Mobile UI refresh (local development)

Home offers Continue and compact shortcuts to Files, writing and the library.
Documents lists open sessions with their type and unsaved state; tap a name to
resume. Its **•••** menu closes that session through the existing unsaved-change
guard. New, Open, Library and Chat remain available from Documents.

The library is a searchable list of books and comics. Tap a title to open its
reader. Contents/bookmarks and appearance have separate tools, keeping the reading
area clear. An editor's **•••** menu contains less frequent document commands.
Markdown opened from local/provider files offers Preview/Edit without saving the
draft; leaving the view clears the rendered preview and keeps the draft in memory.
Closing or locking private content clears the preview as well as its editor text.

Files starts with a native folder selector. Names have no Local/Remote prefix.
Choosing a folder dismisses the iOS wheel and opens its action page. **Browse
folder** opens the available copy; alternate copies have explicit Browse actions.
Managed copies offer **Pull…** and **Push…**. Folders with a loaded remote offer
Pull to create or associate a copy. Local folders also offer **Delete local
folder…**, with native confirmation; online files are kept. Deletion waits until
transfers finish. **Choose another folder** returns to the selector.
Connections loads credentials; Transfers shows progress and managed-copy options.
Returning through the bottom Files tab refreshes the same complete selector.

Folder rows use one line with an icon/name and a navigation chevron. Files can
show their size and **•••** actions. Opening a folder does not flash a selection
checkmark. Sort and List/Tiles remain in the Sort controls.

Pull always asks for native **OK / Cancel** confirmation before writing local
files. Push first shows its changes, then asks for the same native confirmation
before writing online. Cancel keeps the files unchanged. The popup identifies the
source and destination and warns about replacements/deletions. Changing the
connection or mapping while the popup is open invalidates that operation.
A compact transfer strip remains available while writing or reading. The rclone
Sync behaviour and destructive scope are described in the Folder Hub section above.

Native colours follow the system appearance, and phone lists use vertical scrolling.
iPhones request the tab-bar presentation; iPads retain the adaptive sidebar. These
local UI changes need a freshly built app; the previously released main.07 does
not contain them. Screen-reader and physical touch/keyboard validation remain
separate from the automated checks.

Local file folders remain browsable during a pull: open Files, choose a readable local folder,
and enter folders or go Up while the transfer continues. Remote engine operations
remain serialized. The transfer status strip opens details and can be dismissed
after completion without closing your current document.

While a pull runs, tapping a local text or Markdown file opens its editor and
keeps edits in that document session. Tapping a local CBZ/ZIP comic or EPUB opens
the library reader; paging and returning to an open text draft keep the pull
running. Opening and browsing use separate local work without replacing the
transfer cancellation handle. LocalCrypt operations that need the cloud engine
remain serialized.

Home’s **Browse files** opens the same folder selector each time. Choosing
**All files → Browse folder** refreshes the local root and clears an old
search filter. Local browsing does not wait for a credential restore or an
unrelated cloud request.

### Light and dark appearance

The app follows your device's light/dark appearance. Editor text, document-name
fields, labels, selectors, hints and input outlines remain readable in either
mode. Markdown and EPUB pages use matching text/background colours; a reader's
explicit Light/Dark setting still applies only to its pages. Changing Android's
appearance keeps the current app activity and document drafts intact.

Android file rows use flat, normal-case titles with the same size/actions layout
as iOS. Buttons adapt to phone width so row menus and Save/Find/Preview remain
visible; Back and Sort retain their full captions.

Comic reading controls now share the same layout for Local and LocalCrypt:
tap to reveal controls, use Previous/Next or swipe at fit size, and use Fit to
return to the centered page. LocalCrypt bookmarks remain in memory until close;
ordinary library bookmarks retain their saved behavior.

Contents and appearance screens have their own Back step. A reader opened from
Files returns first to reading and then to the same folder. Each provider document
owns its request and cancellation; cancelling that document does not cancel a
separate pull. Wait for its operation to finish before closing it.
