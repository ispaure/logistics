# Logistics on mobile

## Direct remote reading

Open a remote from Folder Hub or Remote files. Tap a supported file to open a
read-only, memory-only reader: small text/Markdown/INI, PNG/JPEG/WebP, EPUB and
CBZ/ZIP comics. Search filters the current folder only. Unsupported files and
content beyond the reader limits show a dialog asking you to manually make a
local copy; opening a file never automatically creates one.

Remote browsers have no standalone file or folder download actions, including
encrypted downloads. Use Folder Hub's managed Pull workflows for offline Local
or LocalCrypt folders. Existing offline copies remain readable and exportable.
Direct readers show no Save, Save As or metadata-edit controls. Locking or replacing credentials
retires their contents, including readers opened with session-only credentials.
See the [rclone guide](../../features/rclone/user_docs/README.md#browse-remote-files-directly)
for limits and desktop behavior.

## Android appearance and E Ink status

Android normally follows the device's light/dark mode. This remains the default.
To opt in, open **Settings → High contrast / E Ink**. The Android-only switch saves
immediately on this device and persists after restarting the app.

While enabled, the app uses black text on white, black outlines and simpler
square controls. Navigation keeps a visible selected state. Button elevation and
navigation ripple effects are removed; HTML text views disable CSS animation and
transitions. Markdown previews, chat and EPUB text receive the same high-contrast
treatment, including already-open HTML views. Images and comic pixels are not
recolored, and no source files or reader theme preferences are changed.

The mode forces this app's light appearance even when Android uses dark mode.
Turn it off to restore the normal system-following app palette and the original
reader/HTML styling. Existing documents, drafts and transfers remain in place.

**Settings → Text & Markdown** also provides editor/preview font size (12–32).
In an open EPUB or comic, **••• → Appearance…** offers reader typography, margins,
width, theme and comic layout. The high-contrast override takes precedence over
reader text colors while enabled; turning it off reveals the chosen theme again.

This is an app appearance mode designed to be useful on E Ink devices, including
BOOX. It does not select BOOX waveforms, force hardware refreshes, remove physical
ghosting or configure the stylus. Those vendor-specific controls are not part of
Logistics. Android emulator checks cover toggling, process restarts, live views
and restoring the normal palette; physical BOOX behavior remains unverified.

## Settings and build information

On iPhone and iPad, choosing a dropdown option closes its picker immediately.

Settings switches use one compact row: label, **ⓘ** help, then the on/off switch.
Tap **ⓘ** for an explanation without changing the setting. This includes
**Document card overview**, **Restore last document**, **Close saved documents on restart** and,
on iOS, **Show Legacy**. Save/reload preferences continue to work as before;
document overview and Show Legacy still apply immediately.

**About** at the bottom of Settings shows muted build information: the app version,
short source revision and commit time when available, plus the platform and
packaged source snapshot. Local modified builds are identified. This information
is available offline; the About heading keeps its normal appearance.

## Current feature support

Android and iOS have the same prototype scope. “Implemented” describes code in
the native app; real-device interaction testing is still required.

| Logistics capability | Mobile status |
| --- | --- |
| Plain-text editing | Implemented: create, select, rename, edit and save private documents |
| Hub and navigation | Native Home, Folder Hub, Documents, Chat and Settings destinations; retained screen per destination |
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
| rclone remote files | Credential ZIP import, direct remote previews, existing offline copies/export, LocalCrypt encrypted offline reading/editing, local folder management and Save As; encrypted saved or session-only credentials |
| Media/image tools, archives and other desktop integrations | Not ported |

## Preferences and storage

The launcher icon includes light and dark artwork. On supported iOS versions it
also includes a monochrome variant for tinted icons; Android 13+ launchers can use
the monochrome artwork for themed icons. The system or launcher controls this
appearance, separately from the app's system-following surfaces and reader themes.

### Local / LocalCrypt location

On Android, open **Settings → Folder Hub → Local / LocalCrypt location…**.
One drive setting controls both collections. Select the SD card to use:

```text
<SD card>/Logistics/Local
<SD card>/Logistics/LocalCrypt
```

Tap **Allow SD card / shared storage access…**, enable Android's **All files
access** for Logistics, and return to the app. Then choose **Copy collections
and use this drive…**. Close open readers and provider documents first and wait
for transfers to finish. Logistics copies existing managed Local and LocalCrypt
folders, checks file contents, and saves the new location only after verification.
Different files already in the destination stop the switch without overwriting;
when there are no existing source files, collections on the selected drive may
be adopted. The app closes after a successful switch; reopen it.

The original copies remain as a recovery backup and continue to occupy space.
Only the selected location is used afterward. Switching back refuses to replace a
backup whose files differ from the current collection. Interrupted migration can
leave copied destination folders, but the original selection remains active until
both collections pass verification. Repeating the switch reuses matching copies.

Credentials, transfer mappings, preferences, imported standalone books, text
imports and recovery drafts remain in internal app storage. Local is readable
storage; other apps with access to the card can read it. LocalCrypt preserves
its encrypted filenames and bytes and still requires the matching credentials.
The public collections survive app uninstall, but private credentials and
transfer associations do not. Reinserting the card alone cannot recover those.

If the card is missing or permission is revoked, local collection operations
stop; Logistics does not silently download into internal storage. Reinsert the
same card or restore permission. iOS keeps its existing private storage location.

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

## Home and document search

Home shows **Your workspace**, with a **Continue** card for the selected document,
**New document** and **Open file…**. Recent lists up to three other ordinary
files; Folder Hub and Books & Comics remain available below. Wider windows put
Recent and Your spaces side by side. Continue restores the document's
Edit/Preview mode. Open file browses existing Local/LocalCrypt files and detects
the supported format when you open one.

Documents puts **Open documents** first, with New document and Open file in a
compact toolbar. Open files are grouped by Text, Markdown, EPUB books and Comics;
empty groups are omitted. **Document card overview** switches between preview
cards and compact rows. Cards use bounded excerpts of ordinary text drafts;
private provider contents are never previewed here. Cards use one column on
phones, two in wider windows and three on large tablets. Closing an item retains
its stored file and uses the existing unsaved-change guard. Recent appears below
open documents and excludes files already open. Private provider sessions and
protected readers remain excluded from durable recent history.

Editor status distinguishes **Unsaved changes · recovery copy kept** from
**Saved on this device**. A recovery copy protects your draft; it does not save
back to an imported original or upload to Remote. A detected external file
change remains visible and offers **Save a copy…**. Local/LocalCrypt provider
editors retain their own source-save and session-only status.

The ordinary text/Markdown editor offers **Find** beside Save and Preview.
Search is literal, wraps through the active document, and supports **Match case**,
**Replace** and **Replace all**. Replacement text is literal too. Search controls
belong to each editor, so switching documents keeps their separate queries and
drafts. **Done** hides the controls. Replacements update the draft and use the
same checkpoint and conflict-aware save behavior as typing; press Save to publish
them. Search does not include other files or the separate private reader editor.

## File and conversation drawers

Documents has a hamburger in its navigation bar. Opening it reveals a menu
with **Browse Local Files**, on-disk unlocked LocalCrypt locations, **Recent**
(up to six ordinary documents), **Comics Library**, and **Shortcuts** for new text,
new Markdown and Folder Hub. Browse and library shortcuts open the existing file
browser in the main area. LocalCrypt browse labels show the remote name without
a transfer-status suffix. Recent can reopen a closed document. Private provider
sessions and password-protected reader sessions are excluded from durable recent
history. The menu's comics folders come from the same discovery as Home's
**Books & Comics**; both show folder names without full paths. Books & Comics
uses folder icons and opens each folder through the existing file browser.

The menu leaves a strip of the current page visible on compact screens. Tap the
hamburger again to return. Reduce Motion skips the animation. Browsing retains
independent storage, folder, search and history, without changing Folder Hub's
selection. Folder Hub has no hamburger; use its Browse Local/LocalCrypt/Remote
actions instead.

At window widths of 640 points/dp or more, including a sufficiently wide Duo
window, the open Documents menu occupies the left half and the current document stays on
the right. In Documents, **Split** appears in a wide window with an editable document and lets you choose a second open text or Markdown
document, including editable provider files. The first stays on the left and the
chosen document opens on the right. Opening the hamburger replaces the left
editor with the menu; closing it restores the pair. **Use one document** in the
Split picker clears the pair. Narrowing the window shows the current document
without closing either session or losing its draft. Books and comics keep their
own reader controls and immersive mode.

LM Chat is a full-screen destination. Its top-left hamburger opens the conversation
list; choosing a conversation restores its unsent draft and messages. On a wide
Duo/tablet window the list occupies the left half and the conversation remains on
the right. Close the menu to give messages the full width. Chat configuration and
app Settings open as full-screen pages with native Back navigation, rather than
bottom sheets. Opening these screens does not send a model request.

## Document workflow

The app opens on **Home**, a landing page with quick access to files, editors,
books/comics and chat. The house icon is the first native destination, before
**Folder Hub**, **Documents**, **Chat** and **Settings**. **Folder Hub** lists folders and their available local, encrypted and remote copies.
If folder discovery fails while credentials change, Folder Hub shows an error
with **Refresh**, **Browse local files** and **Connections…**. Retry there after
the connection is ready; restarting the app is unnecessary.
Tap a folder to browse its preferred available copy directly. The **•••** button
beside a folder opens its Browse Local/LocalCrypt/Remote, Pull, Push and management
actions. The main Browse action is prominent; Delete local folder is separated
and uses destructive styling. Pull/Push direction is shown for mapped copies.
Deletion still requires confirmation, and Push retains its existing review. Local browsing uses app-managed files rather than
the entire device filesystem. Choose **Documents → New** for **Plain text (.txt)** or **Markdown (.md)**.
Books and comics are available through Folder Hub or Home’s Books & Comics panel;
Chat has its own bottom navigation button between Documents and Settings. Native tab
controls adapt to the Apple layout; Android uses bottom navigation in compact
windows and a rail at 600 dp or wider. Switching destinations retains each
screen. **Folder Hub** returns to the folder list and **All documents** returns
from the editor to the Documents hub.

Back returns through screens within the current destination. It does not switch
tabs or close a document. iOS uses its native navigation stack and Back control;
Android uses the lifecycle-owned AndroidX Back dispatcher. At a destination root,
Android yields Back to the system. Existing save/checkpoint failures block a
Back action that would leave the screen.

Choose a document from **Open documents** in Documents or **Recent** in its menu,
or use **Actions → New document**. Edit its name in the name field and
its contents in the text area. **Save** publishes the edited file inside the app.
Text and Markdown use the same plain-text editor.

Each open text/Markdown document owns its editor and draft. **New**, opening a
stored document, and successful imports add it to **Documents → Open documents**;
opening the same stored identity again activates it. Documents with the same name
remain separate. Switch using Open documents or Recent. Closing a document keeps
its stored data; the six most recent ordinary documents can be reopened from Recent.
**Close** removes an item from that list without deleting its stored document.
For an ordinary unsaved document, choose **Save and close**, **Keep draft and
close**, **Discard changes and close**, or **Cancel**. Retained drafts remain on disk and recent entries can reopen them. Discard resets recovery to the current saved file without
overwriting changes made outside the editor or recreating a deleted file. A
failed save or conflict keeps the document open; use **Save a copy** to preserve
both versions. Session-only drafts offer Save, Discard, and Cancel without durable
draft retention. **Close saved documents on restart** is enabled
by default in Settings. On restart, saved text and reader sessions leave Open
documents; stored files and reading progress remain available. Unsaved text,
conflicts and unreadable recovery entries stay in the open list. Turn this setting
off to retain all ordinary open items at the next launch. There is a maximum of
32 open items. An empty workspace stays empty until you create or open a file. Their active selection resumes when **Restore last
document** is enabled; turning it off also prevents automatic EPUB/comic reopening.
You can still explicitly reopen those readers from Open documents with their saved
progress. Private resource restoration remains excluded. Native cursor/selection and scroll offsets are recorded for text views.
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

**Books & Comics** lists configured library folders from Local and unlocked
LocalCrypt copies. Detection uses each collection's `remoteConfig.ini`, matching
desktop: `[LogisticsComics] libraries = Comics,Mangas` names immediate child
folders, in that order. Existing ComicRack/YACReaderLibrary configurations also
identify a collection. Missing folders and unconfigured individual files are not
listed. Tap a folder to browse it and open a book or comic; **Refresh** discovers
configuration changes and newly pulled copies. LocalCrypt names stay in memory
and disappear when credentials are locked or forgotten.

Use **Import…** for a standalone EPUB or comic. EPUB and
CBZ/ZIP imports create private copies; the selected source is never
changed. Imports open directly and remain available through document sessions.
The Books and Comics library shows configured library folders only; it has no
separate imported-items section, selection switches or imported-results paging.
There is no folder search field; the available configured folders appear directly.
Previous/Next and the
chapter/page selector navigate the book's reading order. EPUB pages scroll in the
native web view; comic images fit the native image area. The EPUB view follows
system light/dark appearance and uses the configured font size.

Standalone password-protected CBZ/ZIP comics support AES and legacy ZipCrypto
on iOS and Android, without rclone or a credential package. Import one through
Folder Hub, then enter its ZIP password and choose **Unlock comic**, or press Enter.
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
In the comic reader, horizontal swipes turn pages in both normal and fullscreen
views, including swipes from the screen edge. They do not navigate Back. Zoomed
pages use dragging to pan; fit the page to resume swipe paging. Use the visible
Back control to leave the reader.
Comics fill the available reading width immediately on opening and resize with
the reader. The image keeps its aspect ratio, so some pages can have natural
letterboxing. With controls visible, books and comics use the same hamburger
position as Documents; on iOS it is in the navigation bar. Bottom controls,
reading status and progress indicators stay above the destination bar.

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

Choose **Chat** in the bottom navigation. Open **••• → Server & model settings**, enter your
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
The same button becomes **Stop** during generation; it stops the connection and
retains received text with cancelled status.
Reopening an interrupted streaming record identifies it as interrupted. Failures
retain the user message/partial reply; no automatic retry occurs. The top-left
conversation menu reopens saved conversations. Malformed, oversized or concurrently changed files
are preserved, and saving reports the problem. Export can preserve a current
valid in-memory copy before reopening a conflicting file.

The header shows the conversation title and configured model. Your messages use
compact bubbles; assistant replies use the full reading width with offline basic
Markdown formatting (headings, bulleted/numbered lists, bold and code). Raw HTML is
escaped and links/images do not load external resources. **Copy** copies a reply's
displayed text; if the platform declines copying, select the text and use its
system Copy command. Streaming follows the latest reply only while you are near
the bottom. **Latest message ↓** returns there after reading older messages.

The native message field grows as you type, up to a bounded height; longer drafts
scroll inside it. Send/Stop sits beside the field. Status appears only for ongoing
work, feedback or problems. Server/model settings and **Export conversation…**
are in the **•••** menu. Configuration is scrollable when the keyboard reduces
the available space. Draft storage and text-only request limits are unchanged.

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

Open a folder’s **•••** actions in **Folder Hub**, then choose **Browse Remote** to open its
online file browser. Credential setup is under
**Settings → rclone / Remote connections…** (also reached through **Manage connections…**
in the remote browser). The native app embeds rclone 1.74.1; no desktop
executable, shell, mount, or separate RC server is required. **Check rclone engine**
performs an offline in-memory read and displays the engine version.

The online browser loads filenames and sizes without fetching thumbnails, in
both list and tile views. Opening a folder or file shows the current step and
elapsed seconds, with an animated progress bar. Remote previews report connection
checks, archive index reads and member/data reads; **Cancel** stops the pending
request. The elapsed time is a wait indicator, not a download percentage.

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
setup. Tap folders to open them; **Back** returns through successful visits.
**Folder Hub** returns to the folder list. Tap supported files for read-only,
in-memory previews. Unsupported files show a dialog asking you to make a local
copy yourself. The remote browser has no file or folder download/copy actions;
use the managed Pull workflows to create or refresh offline folders.

Remote CBZ/ZIP comics download completely into memory once before opening.
The status shows downloaded MiB and percentage; subsequent page turns read that
snapshot without contacting the share. The cache allows up to 128 MiB per comic
and 256 MiB across open comics in all windows. Close a remote comic to free its
cache. Closing, locking or replacing credentials clears its cache; nothing is
written to disk. Larger comics require a managed local copy. To see changes made
to the online archive after it was cached, close and reopen the comic.

While an online request is running, Folder Hub's action menus and local folders
remain available. Another online operation shows a busy message and **Cancel
current request** rather than silently waiting. LocalCrypt browsing can continue
during transfers and remote reads; credential replacement must finish first.
Returning to Folder Hub and opening **•••** use the last discovered folder
metadata without rechecking rclone. Credential loading and **Refresh** update
encrypted-folder discovery in the background. Opening a mapped remote shows
**Checking connection…** while its identity and folder path are checked; menus
and navigation remain usable during that check.

A file or folder's **•••** opens actions for that item: **Open preview** for a file
or **Open folder** for a folder. Comic archives offer an inner ZIP password field;
opening a password-protected comic also brings up this form automatically.
The browser status shows when a remote file is opening and reports opening failures.

**Search** filters names in the current folder. Changing folders clears search.
Remote listings read only the selected folder's immediate children. Remote
screens display 24 rows per list page or 16 tiles, with **Previous** and **Next**
above the items; paging, sorting and filtering do not contact the remote again.
The status distinguishes **Listing…** from **Displaying…** and keeps an elapsed
timer while waiting. Folder Hub and its action menus remain available during listing.
Failed navigation preserves the prior listing and history. Browsing has a
two-minute deadline; managed Sync has no fixed overall deadline. Cancellation
may wait for an upstream network call to return.

**Actions → Downloaded copies…** and **Encrypted offline copies…** retain access
to copies created by older versions. Open or export existing private copies;
new standalone copies cannot be downloaded from the browser.

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
For a new encrypted offline folder, use Folder Hub's managed **Pull to LocalCrypt**
workflow. Existing individual encrypted copies remain readable with matching
credentials; the remote browser no longer creates them.

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
the Folder Hub actions described below.

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

Encrypted managed transfers, moves, reads and metadata rewrites have no fixed whole-file
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


### SMB and Mac shared folders

In **Folder Hub**, tap **Add SMB / Mac share…** (also available in Remote connections).
Give each server a unique connection name, enter its IP address or hostname,
username and password, and choose **Add connection and browse**. Enter only the
server in the Server field, without `smb://` or a shared-folder path. The default
port is 445; change Domain when your server requires one. For guest access, enter
`guest` and leave the password empty.

You can add multiple servers. Adding one preserves existing connections and rejects
names already in use. **Save credentials on this device** defaults to on: usernames
and passwords are stored in the existing encrypted credential vault, protected by
Android Keystore or iOS Keychain, and restored when Folder Hub initializes. Turn it off
for a session-only connection; this leaves previously saved credentials unchanged.
Reload saved credentials before adding a saved server if you previously chose
session-only connections: reloading replaces those temporary connections. Importing
a credential ZIP also replaces the loaded connection set.

On a Mac, enable **File Sharing**, enable sharing using **SMB**, and allow the
account used here to access the desired shared folders. Connect from the same
network or a VPN that reaches the server. If a hostname cannot be resolved, use
the server's IP address. Legacy AFP shares are not supported.

The browser first lists the server's shares. Open a share, then the folder you
want, and use **Pull…** in its folder actions to create a managed offline copy.
Existing Pull progress, cancellation and refresh rules apply. A network/login
failure keeps the added connection;
retry browsing after fixing network access. **Forget saved credentials** removes
the saved connection set for all servers, as it does for credential ZIPs.

SMB remotes can also be loaded from existing credential ZIPs. Use rclone's `smb`
configuration with `host`, `user`, `pass`, `domain`, and `port`; `pass` in a ZIP
must already be rclone-obscured. The direct form accepts your ordinary password.
Physical-device SMB transfers still require validation with an actual server.

### Managed folder pulls

Use **Pull…** from Folder Hub for reviewed Local or LocalCrypt sync. The older
snapshot-style repeatable-pull workflow has been removed. Existing downloaded
folders remain on the device; they can still be browsed as local files. Sync can
replace or delete destination files after confirmation, without a retained backup.

## File browser locations and actions

The file browser keeps your current folder, selection, list/tile mode, search, sort and browse
history when you visit Documents or Settings. Local and remote browsers give most
of the screen to the listing. Tap a local file to open it, or a folder to browse
it. Search stays visible; **Sort** reveals sorting and list/tile options. The
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
ordinary text/Markdown and library reading; Folder Hub, transfers, connections and chat
remain in the original window. This keeps private views and connection workers
under one owner. Phone/Duo and Android independent-window controls remain disabled;
Android resizing and split-screen presentation remain available.

System scenes are verified on an iPad simulator. Real-device document pickers,
OS-driven scene eviction, assistive input and physical multitasking still require
separate evidence.

## Folder Hub and Local / LocalCrypt sync

**Folder Hub** combines ordinary Local folders, downloaded LocalCrypt copies and loaded
remotes in one scrollable folder tree. **Credential** defaults to **All**, combining
all local and loaded remote copies. Choose a credential ZIP to filter its folders.
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

**Folder Hub → Transfers** opens **Transfer details**: live progress, completed/known
file and byte counts, cancellation, active review, and completion or error
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

## Mobile UI refresh (local development)

Home offers Continue and compact shortcuts to Folder Hub, writing and the library.
Documents groups open sessions by type and shows preview cards by default. Tap
a filename to continue. Cards show a short text excerpt for ordinary text/Markdown documents
and a type placeholder for books, comics and private provider sessions. The **×**
button closes a session through the existing unsaved-change guard.
In **Settings → App**, turn off **Document card overview** to use the grouped list
with the same direct **×** close control. This switch saves immediately and updates the document
overview, including when an editor is open. Stored documents are not listed in the overview.
Settings groups feature options under Text & Markdown, Books & Comics, LM Chat
and Folder Hub; reader appearance stays in each open reader. Documents offers New document and Open file in its toolbar; Chat has
its own bottom navigation destination. The Library shortcut has been removed
from Documents.

The library is a searchable list of configured library folders. Tap a folder to
browse its books and comics. Contents/bookmarks and appearance have separate tools, keeping the reading
area clear. An editor's **•••** menu contains less frequent document commands.
Markdown opened from local/provider files offers Preview/Edit without saving the
draft; leaving the view clears the rendered preview and keeps the draft in memory.
Closing or locking private content clears the preview as well as its editor text.

Folder Hub starts with a scrollable list of folders. Names have no Local/Remote prefix.
Name-based groups (such as Server → Library → Comics) remain expandable. The Hub
lists storage entry points and managed copies; browsing a remote does not add its
contents to this tree. Open an entry to browse actual subfolders in its file browser.
Tap a folder row to open its action page. **Browse Local**, **Browse LocalCrypt** or **Browse Remote** opens the file browser for that copy.
Managed copies offer **Pull…** and **Push…**. Folders with a loaded remote offer
Pull to create or associate a copy. Local folders also offer **Delete local
folder…**, with native confirmation; online files are kept. Deletion waits until
transfers finish. **Choose another folder** returns to the list. At widths of at
least 640 points/dp, the tree remains on the left and actions appear on the right,
in equal panes centered in the available content. Narrow windows use a separate
action screen. Mapping removal is not offered on this page.
**Settings → rclone / Remote connections…** loads credentials. **Transfers** and
**Refresh** stay above the scrolling list. Transfers opens progress and managed-copy
options; Refresh has its own circular-arrow icon and updates folder discovery.
Returning through the bottom Folder Hub tab refreshes the same complete list.

An ordinary local folder can also **Push…** before its first Pull. **Push whole
folder…** infers the remote from the folder name: `Books` goes to `Books:` in the
matching credential package. **Push as subfolder…** lets you select a loaded
remote: local `Comics` beneath `Books` goes to `Books:Comics`. Existing mappings
retain their account and destination. Review and execution use the same exact
mapping; confirmation does not rename the local folder or resolve another target.
New copies use readable folder names without generated ID suffixes.

In **Transfers → Transfer settings…**, choose rename tracking, an optional positive
whole-number bandwidth limit in MB/s, and Push exclusions (one rclone pattern per
line). Defaults match desktop Push filters. Excluded destination files are kept;
Pull does not apply these exclusions. The review captures the options used by
execution, including when you proceed without the full review. Ordinary Local
transfers follow file links. Links inside LocalCrypt remain rejected.

LocalCrypt Push removes only independent generated files named `.DS_Store`,
`Thumbs.db`, `ehthumbs.db` or `ehthumbs_vista.db`, case-insensitively, including
encrypted names. Review shows **Cleanup** for local removals and **Delete** for
resulting remote removals, without changing files. Plain generated files with an
exact raw allowlisted name can be removed directly; encrypted generated files
must authenticate before removal. Corrupted ciphertext blocks Push and is
preserved. Custom exclusions never authorize local cleanup.

Folder rows use one line with an icon/name and a navigation chevron. Files can
show their size and **•••** actions. Opening a folder does not flash a selection
checkmark. Sort and List/Tiles remain in the Sort controls.

Push and Pull scan their comparison without changing destination files. Both ask
for native **OK / Cancel** confirmation before writing. **Proceed without full
review…** is available while scanning or checking a completed review: it stops the
comparison and asks you to confirm with an explicit warning that more replacements
and deletions may occur. Required credential, destination and LocalCrypt integrity
checks still run. Comparison failure or cancellation never starts a transfer by
itself. Cancelling the review keeps destination files unchanged and does not publish
a new-copy mapping. The popup identifies the
source and destination and warns about replacements/deletions. Changing the
connection or mapping while the popup is open invalidates that operation.
A compact transfer strip remains available while writing or reading. The rclone
Sync behaviour and destructive scope are described in the Folder Hub section above.

Native colours follow the system appearance, and phone lists use vertical scrolling.
iPhones request the tab-bar presentation; iPads retain the adaptive sidebar. These
local UI changes need a freshly built app; the previously released main.07 does
not contain them. Screen-reader and physical touch/keyboard validation remain
separate from the automated checks.

Local file folders remain browsable during a pull: open Folder Hub, choose a readable local folder,
and enter folders or go Up while the transfer continues. Remote engine operations
remain serialized. The transfer status strip opens details and can be dismissed
after completion without closing your current document.

While a pull runs, tapping a local text or Markdown file opens its editor and
keeps edits in that document session. Tapping a local CBZ/ZIP comic or EPUB opens
the library reader; paging and returning to an open text draft keep the pull
running. Opening and browsing use separate local work without replacing the
transfer cancellation handle. LocalCrypt operations that need the cloud engine
remain serialized.

Home’s **Folder Hub** opens the same folder list each time. Choosing
**All files → Browse Local** refreshes the local root and clears an old
search filter. Local browsing does not wait for a credential restore or an
unrelated cloud request.

### Light and dark appearance

The app follows your device's light/dark appearance. Mobile uses the Logistics Slate
palette throughout its workspaces: soft off-white/off-black backgrounds, slightly
raised card surfaces, subtle grey outlines and blue accents. Home, document
cards, file tiles, editors, Markdown previews and chat share those colours. Editor text, document-name
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
Folder Hub returns first to reading and then to the same folder. Each provider document
owns its request and cancellation; cancelling that document does not cancel a
separate pull. Wait for its operation to finish before closing it.


On iOS, hamburger controls open after you release inside the button, allowing a
scroll that starts on the control to be cancelled by dragging away. Workspace
menus use the native navigation bar's own touch target.


## Mobile spacing follow-up

Home hides its redundant top navigation title while retaining its bottom tab.
Documents and Folder Hub use their existing navigation titles without a second
large heading. Settings starts directly with its grouped controls. Both Home and
the bottom navigation use the desktop Folder Hub stack-of-three glyph.
On iOS, Chat measures floating-tab overlap to keep the composer and Send control
above the navigation bar, including while the keyboard is open and drafts grow.


On iPhone, all five bottom-tab labels use their complete names immediately after
launch. Opening each tab is not needed to make its name fit; the startup layout
preserves the selected destination and does not open other workspaces.


## Credential groups, open documents and privacy

Folder Hub's Credential selector includes All and the names of imported credential
ZIPs (for example, Personal). All combines known local and remote folder trees.
For session-only imports, password-protected source ZIPs are retained under device
encryption with their remote names and crypt-setting fingerprints. LocalCrypt can
therefore find the matching ZIP after restarting and ask only for its password.
The ZIP password and decoded credentials remain in memory for the current app
session; the retained ZIP does not restore an unlocked session. Unencrypted ZIPs
are not retained in session mode: select them again next time. **Forget saved
credentials** removes retained ZIPs and their device key. Association metadata
includes ZIP labels and remote names, not decrypted document names or contents.
Previously saved credentials remain saved until explicitly forgotten.

Documents lists open files in type groups below its compact New/Open toolbar. The menu opens immediately using cached shortcuts, then refreshes
available folders in the background. Chat opens on its first tab selection.
On iPhone, plain text actions retain at least a 44-point-wide hit area around
their text or icon, bounded by their own controls. Bordered rows and icon controls
retain their full visible touch targets.

LocalCrypt and private provider documents remain memory-only: their names, paths,
content and previews do not enter Recent or the saved open-document manifest.
They disappear from Home and the opened-document cards when their credential
session is no longer current, and cannot reopen until unlocked. Recent contains
up to six ordinary local/imported document identities. Pulling an
unencrypted managed Local copy makes that copy an ordinary local file, which can appear
in local document history independently of the original remote's lock state.


Opened documents use their filename as the resume link, with a direct ×
close control beside it. There is no separate opened-count heading. Turning off
card previews in Preferences keeps the same name/close row without the excerpt.
On iPhone, tab selection waits for UIKit to finish changing its selected screen
before laying out Documents or Chat, so their content and menus appear on the
first tap.


Chat uses the same rounded, outlined surfaces as the other tabs for its transcript,
conversation list and message input. On iPhone its conversations menu lives in the
native top-left navigation bar, matching the Documents menu position.


Home's Open file action browses all file formats in Local/available LocalCrypt
folders. Comic ZIP/CBZ archives and EPUBs remain visible alongside text files;
opening them uses their reader, while text and Markdown use the editor. The
format-specific Open actions inside Documents retain their category filters.


Folder Hub shows active transfer progress directly below its navigation title,
above Credential. Transfers, Refresh and Add share appear on a single row;
Add share opens the SMB / Mac share connection form. The transfer banner also
shows completion and opens the existing transfer details screen.


Home has a Logistics navigation title above the compact Your workspace
heading. The former “Read. Write. Organize.” tagline has been removed; the bottom
navigation tab remains named Home.


Long file-browser names are shortened visually in the middle when needed, keeping
the beginning and filename ending (including its extension) visible. The complete
name remains available to accessibility, file information and all file actions;
this display setting does not rename or change the file path.


On iPhone, changing file-browser locations now refreshes the native picker before
selecting the new location. Opening a LocalCrypt comic uses that encrypted folder
instead of accidentally falling back to Local files. If a private file cannot be
opened, the reason appears in the file browser instead of only in Connections.


LocalCrypt INI files can now open in the memory-only text editor and save back
to encrypted storage. They use the same 1 MiB limit, encoding/line-ending
preservation and conflict checks as private text/Markdown files. Opening them
never adds their names or content to ordinary history or recovery storage.


LocalCrypt comics use the nearest ancestor `remoteConfig.ini` when an inner
archive requires its configured `[LogisticsZIP] archive_password`. The lookup
reads through encrypted storage and stops at that storage root. An empty nearest
LogisticsZIP section stops inheritance; a manually supplied value takes priority.
Resolved values stay in memory for the reader session and are cleared on close.

On Android and iOS, folders whose names start with `Legacy-` are hidden in Folder Hub,
file browsers and library shortcuts by default, including Local, Remote and
LocalCrypt folders. Settings → Folder Hub → **Show Legacy** changes visibility
for the current session. Press **Save preferences** to keep the choice after
restarting; **Reload preferences** restores the saved choice. Files with that
prefix remain visible when their parent folders are visible.

The same **Show Legacy** switch also hides credential/ZIP choices whose
names start with `Legacy` (case-insensitive, no dash required), including retained
ZIP unlock choices. Turning it on reveals these choices immediately. Hiding a
selected credential returns the Folder Hub selector to **All**; stored credentials
and their ZIPs are retained.

### LocalCrypt session and screen privacy

A session lasts for the running app process. Privacy protection starts as soon
as session-only credentials load, before any document is opened. A configured
crypt, saved credentials or a selected ZIP alone does not activate it. Protection
continues until both those credentials and all associated private views are cleared.
Navigating between tabs does not lock the session. Leaving the app or locking
the device covers it immediately; returning shows a lock screen until you enter
the session's ZIP or connection password. Private edits remain in memory behind
the lock. Private views with a separate archive password may require that password
as well. Passwordless sessions first ask you to set a temporary lock password.
On iOS, the lock form stays inside the safe area, clear of the status bar, notch
and home indicator in portrait and landscape.
These lock passwords and their verification data are never saved to disk.
Closing/replacing credentials retires private readers; cached plaintext reads
check the credential generation shared by all windows. Private thumbnails, names,
reading positions and drafts do not enter document history or recovery files.
This does not promise secure erasure of RAM or protection on a compromised device.

On iOS, windows with loaded session-only credentials or associated private views
are covered while inactive before app-switcher snapshots. Fresh launches and
saved credentials alone do not activate the black privacy screen. Loaded private
session content is also covered during detected recording/mirroring. Stop capture
to use the session or its lock screen. External displays receive a blank screen,
never a separate workspace or frozen Home view. iOS does not provide
a supported general switch to prevent still screenshots; screenshot detection
happens after capture. On Android, secure windows block ordinary screenshots and
nonsecure capture while session-only credentials or associated private views remain loaded. Native device
behavior can vary; these controls do not block an external camera.

LocalCrypt follows the credential package's filename settings. Names remain
readable if filename or directory-name encryption was disabled; ciphertext sizes,
counts and timestamps and connection/remote labels are not secret. **Pull to Local**, Move/Save As to Local, exports and clipboard copies intentionally
produce plaintext. Session-only imports leave an older saved credential vault
unchanged; use **Forget saved credentials** to remove it and older retained ZIPs.

### Locked credentials and Folder Hub

Mobile now follows desktop Folder Hub visibility. Before a session-only credential
is unlocked, only its existing mapped Local/LocalCrypt copies appear. Retaining
a ZIP remembers which password can unlock a local copy; it does not expose the
ZIP's entire remote list in Folder Hub. Credential groups with no visible copies
are omitted there while locked. After unlocking, all normally visible remotes in
that credential appear, including remotes without a local copy.

Use **Settings → rclone / Remote connections… → Unlock <ZIP name>** to unlock a
retained ZIP even if it has no local folders. Enter its ZIP password; a wrong
password keeps the prompt open and the remote-only list hidden. Success returns
to Folder Hub with the loaded remotes. **Choose credential ZIP…** still imports a
new ZIP or one that was not retained. **Lock credential session** clears the
unlocked credentials and hides remote-only entries while keeping local copies,
retained ZIPs and previously saved credentials. Save or discard private edits
before locking. **Forget saved credentials** also removes retained ZIPs and keys.


### Reader navigation and imported metadata

Imported EPUBs now provide nested contents/internal links, current-chapter search,
screen-step navigation and passage-based resume/bookmarks. Android and iOS provider
EPUBs share rich rendering, nested contents, internal links, highlighted search and
appearance controls through a private browser view. Their positions and bookmarks
remain session-only; other backends retain bounded native text passages. See the [Books guide](../../features/books/user_docs/README.md#native-mobile-reading)
for pagination and persistence differences.

Comic readers offer single/automatic/two-page layouts, manga-aware spreads and
spread-aware turns. Imported comics also have first/last and neighboring-comic
commands; folder-backed provider comics can open neighboring comics from their
reader menu. See the [Comics guide](../../features/comics/user_docs/README.md#native-mobile-library).

The Books & Comics catalogue now includes imported copies. Reader menus edit
metadata on ordinary imported EPUBs/comics; selecting comic rows opens explicit-field
batch editing. These writes change the imported copy, preserve page/resources and
leave the external source untouched. Existing provider metadata saves keep their
own encrypted-publication policy. A recovery journal completes an imported
archive/checksum-record publication interrupted after the archive was saved.


### Mobile EPUB speech and expanded appearance

EPUB reader menus now include **Read aloud…**, with installed offline voices,
speed, selected-passage playback, pause/resume and stop. Resume repeats the current
sentence/passage. Private-reader suspension stops speech and clears its queued text.
Appearance includes local font families, custom line spacing and maximum width,
and Sepia/Slate alongside existing themes. See the
[Books guide](../../features/books/user_docs/README.md#native-mobile-reading).

Imported catalogue search indexes all ordinary imports incrementally, persists a
disposable local cache, and shows 50 results per page. Comic edit forms offer
collection suggestions. Ordinary local and unlocked LocalCrypt folders have recursive comic
metadata batches through **Files → Actions → Edit comics in this folder…**. See the
[Comics guide](../../features/comics/user_docs/README.md#mobile-collection-search-and-folder-batches)
for scan limits, explicit-field saves and private-session cleanup.

## Focused browsing and setup

In the Local/LocalCrypt file browser, **Parent folder** moves up the folder tree;
the native Back action leaves the current screen. The Open file browser displays
the current folder breadcrumb beside Parent folder. Duplicate browser Back
controls are omitted; Sort and view controls remain secondary to search and files.

Chat shows **Set up chat** until a server and model are configured. Send is
disabled until configuration is available; opening setup does not connect to a
server or discard an unsent draft. User messages retain bubbles; assistant
messages use an open layout. The conversation menu, streaming Stop action and
history remain available.

An empty Books & Comics library offers **Import a book or comic…** and
**Open Folder Hub**. An empty search offers **Clear search**. Library search has
its own row so Refresh and Import do not crowd the search field.

On iOS, ordinary screens reserve the measured overlap of the floating tab bar,
including keyboard changes. Chat and immersive readers retain their own chrome
ownership. The local presentation uses larger touch targets and names document
close/action controls for accessibility.

### Compact mobile control icons

Reader Previous/Next page controls use left/right chevrons. File-browser history
uses a back chevron; **Parent folder** uses an up arrow, so moving up a directory
remains distinct from leaving a screen. Browser result paging and editor Find
Previous/Next match controls also use chevrons. Reading Contents uses a list icon,
Appearance uses a text-size icon, and editor Find uses a magnifying glass.
Overflow menus use an ellipsis and document close controls use a cross.

These controls have 48-point touch targets and descriptive VoiceOver/TalkBack
names, including the affected filename on row menus and close buttons. Save,
transfer, deletion confirmations, and named return destinations keep text labels.
The icons follow system appearance, including Android's high-contrast setting.

### Current iOS and Android differences

Both platforms share the main file, editor, EPUB/comic, chat, and transfer
workflows. Navigation bars, pickers, menus and installed speech voices use each
platform's native presentation. iPad supports additional app windows; Android
currently keeps one app workspace/window. Android alone offers **High contrast /
E Ink**. iOS alone offers **Show Legacy**, which controls visibility of names
beginning with `legacy-` and credential package names beginning with `legacy`; Android shows them without that filter.

Android protects sensitive windows with its secure-window flag. iOS hides content
for inactive app snapshots and detected recording/mirroring, but cannot prevent
still screenshots. See the developer [parity review](../../../docs/developer/mobile-ui-refresh.md#control-icons-and-iosandroid-parity-review-2026-10-15)
for the implementation boundaries and verification scope.

### Android fullscreen comics and developer settings

Comic reading mode hides both Logistics navigation and Android's status/navigation
bars. Tap the comic to restore reading controls; navigating away restores system
bars. An edge swipe can temporarily reveal Android's system bars. Image fitting
still preserves page aspect ratio, so a page need not cover every pixel.

Android **Settings → Developer settings…** opens the system developer options
directly, including Wireless debugging, once developer mode is enabled. This
avoids a separate settings-launcher app. It does not keep wireless debugging
enabled if the tablet's firmware disables it during sleep or a Wi-Fi change.
