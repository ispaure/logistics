# LocalCrypt on mobile

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
unchanged. These actions affect the selected local collection storage, not cloud originals or
arbitrary folders owned by another app.

To organize an older offline encrypted copy, select it on the Remote files screen,
open the manager and choose **Use selected offline encrypted copy**. Choose a
private download similarly with **Use selected private download**. Existing copies
are preserved until their transfer succeeds. Managed crypt files can be read and
edited directly, including their comic/EPUB metadata.

Markdown opened from the file browser starts in preview. **Edit Markdown** uses
one formatted editing surface, with **Source** for exact syntax. **Open** from
inside the editor starts editing directly. No source/preview split is added.

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

Cancelling an Open/Save As operation prevents a late result from opening a file
over the screen you selected meanwhile. A background call may need time to stop.
Locking private content cancels pending picker work; a file published just before
cancellation can still exist at the destination, so inspect it before retrying.


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
Saved and session-only servers can remain loaded together.
Reloading saved credentials preserves temporary connections;
loading a credential ZIP adds or replaces only its own package context.

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
