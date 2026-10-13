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
| File browser, bulk rename, IDE and Git/Perforce UI | Not ported |
| LM chat | Native text conversations, configured server/model, streaming/cancel, private history and Markdown export |
| rclone remote files | Credential ZIP import, read-only browsing, private downloads and export; session-only credentials |
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
migration, backup/reset behavior and credential storage remain separate work.

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

Imports are limited to 256 MiB, 5,000 archive members, 256 MiB of decompressed
member data in total, and 8 MiB per member. Native comic images must be PNG/JPEG,
no larger than 8 MiB or 16 megapixels, with each dimension at most 8,192 pixels.
Comics with other page formats are rejected rather than silently skipping pages.
EPUB chapters and rendered HTML are limited to 2 MiB. Small PNG/JPEG illustrations
(up to 256 KiB each, 1 MiB total) are embedded; unsupported/large illustrations
show an omission label. Raw scripts, forms, embedded objects, source styles and
external resources are removed. Chapter links are inert; use the chapter selector.
DRM, encrypted archives, CBR/RAR and fixed-layout SVG books are not supported.

The private book checksum is checked on opening, and the portable reader rejects
changes while reading. Re-import a changed private copy as a new entry. Malformed
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
local paths, scripts, service-account files, mounts, alias/crypt wrappers and
other backends are not currently supported. WebDAV URLs and custom S3 endpoints
must use HTTPS. Certificate verification stays enabled.

Choose a remote, optionally enter a relative folder, then **Browse folder**.
**Open selected folder** and **Parent folder** navigate its entries. A folder
result is limited to 1,000 displayed entries. **Download private copy** reads the
selected file into this app's private Downloads, up to 32 MiB. It never uploads,
renames, deletes or synchronizes remote files. **Cancel request** cancels the native
operation; individual network reads have a 15-second timeout and operations have
a two-minute deadline. Some upstream backends may take until their network call
returns to acknowledge cancellation.

Select a private download and choose **Open private copy** to import it into the
text/Markdown editor or EPUB/CBZ library, subject to those readers' existing format
and size limits. Other/bigger files can use **Export private copy…**, through the
system destination picker, up to 32 MiB. Repeated downloads produce separate private
copies; incomplete copies are excluded from the selector after a restart.

The ZIP password, decrypted credentials and refreshed OAuth tokens are held only
in this app session. They are not saved to preferences, extracted config files,
logs or downloaded-file metadata. **Forget session credentials** clears the
loaded session while preserving downloads. Re-import after restarting. Updated
tokens are not written back to the ZIP: accounts that rotate refresh tokens may
need a fresh credential package. A secure persistent credential vault and interactive
OAuth account setup remain future work. Private download files persist on this
device and are subject to the platform's normal app-data backup policy.
