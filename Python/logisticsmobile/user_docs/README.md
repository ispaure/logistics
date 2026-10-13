# Logistics on mobile

## Current feature support

Android and iOS have the same prototype scope. “Implemented” describes code in
the native app; real-device interaction testing is still required.

| Logistics capability | Mobile status |
| --- | --- |
| Plain-text editing | Implemented: create, select, rename, edit and save private documents |
| Hub and navigation | Implemented: Home, Documents and Settings |
| Markdown | Text editing and offline basic preview: headings, list items, bold and code blocks |
| Document import | Native picker adapters implemented; actual provider permissions still need device testing |
| Draft recovery | Implemented: checkpoints, restored drafts and conflict-safe save-a-copy |
| Encoding and line endings | Implemented for UTF-8 and recognized Unicode BOMs, with a 1 MiB text limit |
| EPUB and comics | Private library, EPUB chapter navigation and PNG/JPEG CBZ/ZIP pages, saved progress and bookmarks |
| Preferences / INI settings | Private INI with font size and last-document restore controls; no desktop preference migration |
| Export | Export a copy through the platform destination picker |
| Share or save back to the original document | Not implemented |
| File browser | Shared native list/tile views, thumbnails and file information for app-managed Local/LocalCrypt files and remote browsing |
| Bulk rename, IDE and Git/Perforce UI | Not ported |
| LM chat | Native text conversations, configured server/model, streaming/cancel, private history and Markdown export |
| rclone remote files | Credential ZIP import, ordinary downloads/export, LocalCrypt encrypted offline reading/editing, local folder management and Save As; encrypted saved or session-only credentials |
| Media/image tools, archives and other desktop integrations | Not ported |

## Preferences and storage

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

## Document workflow

The app opens on Home. Tap **Text & Markdown** or **Documents**. Choose a
document from the top selector, or tap **New**. Edit its name in the name field and
its contents in the text area. **Save** publishes the edited file inside the app.
Text and Markdown use the same plain-text editor.

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

From Home, choose **Books & Comics** and **Import book/comic…**. EPUB and
unencrypted CBZ/ZIP imports create private copies; the selected source is never
changed. Choose a library item and **Open selected**. Previous/Next and the
chapter/page selector navigate the book's reading order. EPUB pages scroll in the
native web view; comic images fit the native image area. The EPUB view follows
system light/dark appearance and uses the configured font size.

Progress remembers the current EPUB chapter or comic page, rather than an exact
scroll position inside a chapter. **Bookmark** / **Unbookmark** toggles that
chapter/page; the bookmark selector returns to saved positions. Comic pages use
natural filename order. Right-to-left manga metadata is identified; single-page
Previous/Next controls still refer to reading-order positions.

Ordinary CBZ/ZIP comics stream into the private library without a fixed archive
or total decompressed-size cap. Reading seeks archive headers and fetches only the
chosen page. Both EPUB and comic archives are limited to 5,000 entries; EPUB
imports retain the 256 MiB archive/expanded-total and 8 MiB per-member limits.
Native comic images must be PNG/JPEG,
no larger than 8 MiB or 16 megapixels, with each dimension at most 8,192 pixels.
Comics with other page formats are rejected rather than silently skipping pages.
EPUB chapters and rendered HTML are limited to 2 MiB. Small PNG/JPEG illustrations
(up to 256 KiB each, 1 MiB total) are embedded; unsupported/large illustrations
show an omission label. Raw scripts, forms, embedded objects, source styles and
external resources are removed. Chapter links are inert; use the chapter selector.
DRM, encrypted archives, CBR/RAR and fixed-layout SVG books are not supported.

Imports hash bytes during their streamed copy. The checksum is verified on
opening after a restart; reopening an unchanged file in the same session reuses
a bounded revision-keyed verification cache. Changed files invalidate it, and
individual page reads reject concurrent changes. Re-import a changed private copy as a new entry. Malformed
library records are preserved and reported. Progress/bookmark writes reject stale
records rather than overwriting another change.

## LM chat

Choose **LM Chat** from Home. Open **Server & generation settings…**, enter your
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

Choose **Remote files** from Home. The native app embeds rclone 1.74.1; no desktop
executable, shell, mount, or separate RC server is required. **Check rclone engine**
performs an offline in-memory read and displays the engine version.

Enter the password, then **Import credential ZIP…** and choose your existing
Logistics credential package. TXT entries must each contain one `[Remote name]`
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

Choose a remote, optionally enter a relative folder, then **Browse folder**.
Tap a folder to open it, or use **Open selected folder** and **Parent folder**.
**Back** returns through successful folder/storage visits in this browser session.
**Search** opens a full-width field and searches names in this folder and its
subfolders, requesting additional remote listings in the background. Scans stop
after 10,000 entries and report incomplete results. Choose a name, size or modified-time sort. Folders stay first. Search resets when
the location changes, and hiding a selected file clears its action selection. A folder
result is limited to 1,000 displayed entries. **Download private copy** reads the
selected file into this app's private Downloads as a stream, without a fixed whole-file size cap. It never uploads,
renames, deletes or synchronizes remote files. **Cancel request** cancels the native
operation; individual network reads have a 15-second timeout and operations have
a two-minute deadline for browsing and a 30-minute deadline for transfers and archive rewrites. Some upstream backends may take until their network call
returns to acknowledge cancellation.

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
files**, select the crypt remote, then **Browse folder** to see decrypted names.
Choose a file and **Download encrypted copy**. The app saves the original rclone
ciphertext under its private LocalCrypt storage; it does not save decrypted content
or add a plaintext filename to the copy's record. Filename privacy still depends
on the crypt remote's filename-encryption settings.

Remote browsing and unlocked copies show decrypted names. **Manage local files
and folders** opens a local browser with **Local files** and the session's
**LocalCrypt** destinations. **List** and **Tiles** use the same shared browsing
model as desktop. Visible PNG/JPEG images and comic/EPUB covers load in the
background, with a bounded memory cache. Select a file to see its name, size and
modified time, plus available comic/EPUB metadata below the entries. Folder
navigation supports tapping folder entries, **Parent folder** and **Back** through
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
supports text/Markdown editing, EPUB chapter text, and PNG/JPEG comic pages in
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
bookmarks, plaintext export or thumbnail cache. Markdown is edited as source text;
desktop Markdown formatting, folder mirroring and upload are not available here.

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
