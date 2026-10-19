# Connect and transfer remote folders

Load private credential packages, then push or pull folders using the chosen
remote config. FUSE is optional and only needed for mounting.

## Set up credentials

1. Place your credential ZIP packages in the checkout's `Credentials/rclone/`
   directory (or the configured credentials resource directory).
2. Open **Settings → rclone → Credential packages** and load a package, entering its password when asked.
3. Return to **Workspaces** and select the rclone source and credential.
4. Select a remote. If a local folder has exactly the same name, it is associated
   with that entry.

**Load on Disk** saves credentials for later use. Each saved package creates
its own config, such as `~/.config/rclone/Personal.conf`.
Credential ZIPs contain TXT entries with a remote section header as their first
line and the remote's rclone settings below it. Every TXT entry must be encrypted
with the package password; plain or mixed encrypted/plain packages are rejected
by both desktop load options. Packages must be supplied separately;
Logistics does not create account credentials for you.

Choose **Load for Session** to use a package only for this Logistics session.
Pressing Enter in the password field also loads for the session. The ZIP is decrypted directly in memory, with no extracted
TXT or `.conf` file. Workspaces shows the package with a **(session)** label. Push,
Pull and previews pass its settings to each rclone child in a private environment,
with a memory-only config and no secret command arguments. Existing saved configs
remain unchanged. Session credentials disappear when Logistics exits, or when you
use **Forget Credentials** / **Forget All Session Credentials**. The cleanup controls appear in order: **Clear All .rconf Files**, **Forget
Credentials**, then **Forget All Session Credentials**. The first deletes saved
rclone `.conf` files; **Forget Credentials** removes both saved and session
credentials for the selected package and keeps its ZIP. Detached FUSE mounts
currently require saved configs.

Short-lived desktop CLI processes do not return refreshed OAuth tokens to Logistics.
Session mode may need another unlock or a renewed package if a provider rotates its
refresh token. Saved `.conf` files retain rclone's token updates; these files contain
credentials and rclone's obscured passwords are not secure encryption. Mobile's
saved option instead uses its device-protected encrypted vault.

The **INI files** tab holds feature configuration, including software download
settings. Switching tabs retains unsaved INI edits and credential-panel state.
Use **User Guide** to return to these instructions.

## Transfer files

Use the selected folder's **Push…** or **Pull** action. Review the direction and
available options before starting: the operation changes files at its destination.
If several credentials define the same remote name, choose the intended credential;
its label does not change the local sync path. Mount paths are separated by config.

Desktop and mobile Sync preserve empty source folders where the destination
backend supports directories.

Sync inventories, comparison reviews and their generated-file cleanup plans
have no fixed entry limit on desktop or mobile. Local safety checks still scan
the full folder and can be cancelled.

GUI Push/Pull opens a retained **Workspace actions** job with live transfer statistics,
command output, operation state and retry attempt. Results stay available after completion.
Success requires a normal exit with code zero; failures show the exit code and
recent output. rclone retains its own retry policy, and a successful retry reports
which attempt succeeded. **Cancel** stops the process; completed destination changes
remain. Closing Logistics cancels active integrated transfers and waits for them
to stop. A started job is not yet a successful transfer; check its final result.

| Location | Default path |
| --- | --- |
| Local copy | `~/Server/Local/<folder>` |
| Optional mount | `~/Server/NetworkMount/<config-id>/<remote>` |

Before an rclone command, a missing or mismatched executable offers a verified
download. Declining, cancelling or a download failure stops that command.
Windows/macOS/Linux x86_64 and ARM64 builds are pinned. Downloads do not start just
because you browse folders. Transfers have their own execution model; the download
Cancel button does not cancel a later transfer.

## Remove a loaded config

Removing a loaded credential deletes its generated config, leaving the ZIP package
available to load again. **Clear All .conf Files** removes every config directly in
the rclone config directory, including configs created outside Logistics.

For mounted browsing, see [FUSE](../../../fuse/docs/user/user.md). For local software
and credential paths, see [application setup](../../../../../docs/user/configuration.md).

## More help

See [Using Logistics](../../../../../docs/user/user.md) for navigation and settings.


Marc’s existing Dropbox credential folder (`Software/GIT/logistics/Credentials/rclone`)
is also discovered automatically when present. Hover a package to see its location.

## Choose a rclone download version

In **Settings → rclone**, the configuration tabs list supported platforms. Each
contains the version, download URL, ZIP member, local destination and verification
hashes. If you change releases, update these values together. One hash verifies
the ZIP; the other verifies its executable. Saving does not download anything or
replace a running tool. See [download settings](download-versions.md#rclone-download-versions)
for the field details.

Sync progress opens in **Workspace actions** on the left rail. Each job has its own
tab with transfer statistics and logs; completed and failed jobs remain available
until you close them. A red badge marks results you haven't viewed. Completion
and errors also use system notifications when the platform supports them.
Closing a running job cancels it and waits for its process to stop.

## Choose the sync scope

Push and Pull use **sync**, not an additive copy. Files missing from the source can
be deleted at the destination; changed files can be replaced. Logistics provides
no undo for these transfers. Keep independent backups of destination-only files.

| Choice | Source → destination | Consequence |
| --- | --- | --- |
| Entire local folder | Managed local folder → remote root | Remote contents become a mirror of the local folder |
| Specific folder | Chosen folder → `remote:<folder-name>` | Only that destination subtree is synchronized; siblings are outside its scope |
| Pull | Remote root → managed local folder | Local destination-only files can be removed; the app asks for confirmation |

**Track renames**, offered for entire-folder Push, asks rclone to detect renames
instead of transferring matching content again. Specific-folder Push offers a
positive bandwidth limit in MB/s; blank means unlimited. Review the displayed
source and destination before pressing **PUSH**. Both Push and Pull then scan a
detailed review of file additions, replacements and deletions using rclone's own
dry-run comparison. Review does not write destination files or create a new local
copy. Confirming a complete review checks for changes again before starting; if
the comparison changed, inspect the new results and confirm again. Comparison
scans use rclone’s normal retries on both desktop and mobile. Each attempt
replaces the previous attempt’s results; an exhausted or cancelled comparison
remains incomplete. Cancel and **Proceed without full review…** remain available
while waiting for a retry.

Empty source folders are preserved when the destination backend supports them.
Both desktop and mobile review list directory changes with a trailing `/`,
including nested empty folders and decrypted crypt folder labels. The final
change check tracks directory membership and type without treating directory
timestamp changes as new transfer work.

While scanning or checking a completed review, **Proceed without full review…**
lets you stop waiting and explicitly confirm the source and destination. The
confirmation warns that additional replacements and deletions may occur. It waits
for the comparison to stop before launching the transfer. Credential, destination
and LocalCrypt integrity checks still apply. **Cancel** closes the review without
starting a transfer. An incomplete or failed comparison never starts one by itself.

Ordinary sync follows source file links (`--copy-links`), so linked content can be included.
Unassociated local folders match accounts by remote name. A folder pulled with
temporary credentials remembers its matching ZIP; a different ZIP cannot claim
that same local folder name.

For a session-loaded crypt remote, **Pull to LocalCrypt** mirrors the backing
remote's ciphertext into `~/Library/Application Support/Logistics/LocalCrypt` on
macOS (the Logistics per-user preferences folder on Windows/Linux). **Push** sends that copy back to the
matching backing remote and subpath without encrypting it again. Both operations
are explicit mirrors; editing a local document does not upload it.

The encrypted copy's root folder may itself be a symbolic link or Windows
junction, including when `LocalCrypt` is relocated. Entries **inside** the
copy cannot be symbolic links, junctions or hard-linked files. Transfers and
private browsing reject these entries with an error naming the offending path.
A missing or invalid credential mapping blocks Push rather than guessing a remote.

## Browse remote files directly

On desktop choose **File Browser → File → Open Remote…**, or select a remote on
Workspaces to browse it in the Files pane. Each remote opens in its own tab, labelled with its account
and remote name. Navigation stays within that remote. Duplicate tabs retain the
account and current directory; tabs use the existing workspace docking.
Credentials must already be loaded through rclone settings.

Remote browsing is read-only. Search filters the current folder; it does not scan
subfolders. Listings, thumbnails and directly opened contents stay in memory,
without filesystem indexing or persistent preview caches.
Small text/Markdown/INI files open read-only (up to 1 MiB); PNG/JPEG/WebP images
use up to 16 MiB. EPUB and CBZ/ZIP comics read archive members on demand, with
bounded buffers. Inner archive passwords are separate from crypt credentials.
On mobile, CBZ/ZIP comics first cache the complete archive in RAM, then read
pages from that session snapshot without further network requests. The limits
are 128 MiB per comic and 256 MiB across windows. Download progress shows bytes
and percentage. Closing the comic or retiring its credentials releases the cache;
it is never written to disk. Larger comics need a managed local copy. Reopen to
load a newer online version. Mobile remote listings do not fetch thumbnails.
On mobile, a comic's inner password opens an item-specific password form. The
file/folder **•••** page also offers **Open preview**/**Open folder** for that item,
with an optional inner ZIP password for archives. File-opening progress and
failures appear above the browser listing.
Other formats and content exceeding the direct-reader limits show a dialog asking
you to manually make a local copy and open it. External applications require an
explicit local copy. Remote readers cannot save text or metadata back to storage and show no Save,
Save As or metadata-edit controls.

Remote browsers on desktop, iOS and Android offer browsing and direct previews
only. They have no standalone file or folder download/copy actions. To create an
offline copy, use the existing managed **Pull to Local** or **Pull to LocalCrypt**
workflow from Workspaces. Session-only credentials do not create a persistent
remote document; locking or replacing credentials retires its open readers.

On mobile, open a remote from Workspaces or **Remote files**, then tap a supported
file to read it directly. Current-folder filtering and the manual-local-copy
dialog apply on mobile too. Failed navigation retains the previous listing and
selection while credentials remain current; credential changes clear stale views.
Reader menus expose only commands available for the current file type. No remote editing, uploading, renaming, deletion or
moving is available in the remote browser.

## Android and iOS prototype

See [Rclone mobile workflows](../user_mobile/workflows.md#android-and-ios-prototype).

## Read and edit a LocalCrypt copy on desktop

For a session-loaded crypt remote with no existing copy, Workspaces offers:

| Action | Destination | Contents on disk |
| --- | --- | --- |
| Pull to Local | `Server/Local/<remote>` | Ordinary decrypted files |
| Pull to LocalCrypt | Logistics application support folder, `LocalCrypt/<remote-name>` | Original ciphertext |

Once a copy exists, **Pull** refreshes the selected kind: Local stays decrypted,
LocalCrypt stays encrypted. If both exist, select the appropriate entry first;
the account row prefers Local and the separate LocalCrypt entry selects ciphertext.
When no local copy exists, choose **Pull to Local** or **Pull to LocalCrypt**.
Pull uses sync and can replace destination files or delete destination-only files.

**Pull to Local** with temporary credentials also saves a small connection record
under the Logistics application support folder's `Connections/Local`. It contains the credential ZIP's location and
remote name. After credentials lock or Logistics restarts, Workspaces still shows
that Local copy under its account; **Push…** and **Pull** request the matching ZIP's
password. Keep that ZIP at its recorded location. Previously pulled folders acquire
this association the next time you Pull with their temporary credentials.

Existing `Server/LocalCrypt` copies and `Server/.local-connections` records relocate
to these application support locations when first discovered. Decrypted Local files
stay in `Server/Local`. If both an old and new storage directory exist, Logistics
preserves both and reports the conflict rather than replacing either copy.

A loaded account can show folders that exist only remotely. After the account is
unloaded, its saved Local or LocalCrypt entry appears only while the corresponding
folder exists on disk. Connection records without a folder do not create entries.

Choose **Load for Session**, unlock the ZIP containing both the crypt
remote and its direct backing remote, then use **Pull to LocalCrypt**. Open its
LocalCrypt folder to browse decrypted names. Supported documents are text (`.txt`), Markdown (`.md`, `.markdown`), EPUB books
and comic ZIP/CBZ files. EPUB and comic metadata are editable from the context
menu or reader. Other file types stay unopened in this private browser. This workflow needs no mounted filesystem.

Names are displayed decrypted. Use **New folder**, or right-click an item for
**Rename**, **Delete** and **Move to**. Move can target another folder in the same
LocalCrypt, another unlocked LocalCrypt, or an ordinary Local folder. The toolbar's
**Move file/folder into this folder** imports local files and folders, encrypting
them before removing the source. Moving out creates decrypted destination files.
Empty folders and inner ZIP passwords are preserved. Cloud files change only when
you separately Push or Pull.

Private folder navigation reads the selected folder rather than rescanning the
entire copy. Comic and EPUB reads share a bounded memory cache, and unchanged tile
thumbnails survive folder navigation. File changes invalidate cached reads;
closing the last browser or reader releases its cache. Decrypted cache data stays
in memory.

Private Markdown opens in preview. **Edit** switches to formatted/source editing;
holding Alt/Option while opening starts editing directly.

Private Markdown **Save As** uses the same Local/LocalCrypt destination choice and
switches the editor to the newly saved file. The original remains unchanged.
Save As and moves reject existing destination names; rename or remove the conflict
first. Delete is permanent and asks for confirmation. Cross-storage moves verify
the destination before deleting the source; cancellation or a later deletion
failure can leave both copies or remaining source entries. Refresh both folders
before retrying. Open documents whose original was moved must be reopened or saved
with Save As; a stale save cannot recreate the old path.

Markdown can be edited and saved locally. **Edit comic metadata…** and
**Edit EPUB metadata…** update metadata in the encrypted local archive. Pages,
chapters, covers and unrelated metadata are preserved. Inner ZIP passwords remain
in effect; rewritten encrypted archives use AES-256 with the same password.
For an EPUB, the password comes from inherited `remoteConfig.ini` or a session-only
prompt. No plaintext temporary file or backup is created for LocalCrypt metadata
saves. Conflicts, failed verification and cancellation preserve the original.
An inner ZIP password is separate from the credential-package password; the reader
can find it in an ancestor `remoteConfig.ini` or ask for it. Saves stage ciphertext
and reject stale originals. Cancel before publication preserves the original;
a cancellation after a completed replacement cannot undo that save. Use **Push**
explicitly to upload local changes, and review its resolved backing destination.

The private browser keeps filtering, locations and resources in memory. Persistent
indexing, disk thumbnail caches, recent-file records and private comic/EPUB reading positions
are disabled. Private EPUB bookmarks stay in the current session. Markdown Open
and Save As use the Local/LocalCrypt picker; temporary-file diagram rendering is disabled;
images are limited to prefetched local resources inside the copy. Markdown files
are limited to 8 MiB, folder listings to 10,000 entries, and prefetched Markdown
images to a combined 32 MiB. Comic members have separate bounded reading limits.

Closing the browser does not invalidate documents that are still open. Closing
the last owner removes its private reader credentials. **Forget Selected
Credentials** and **Forget All Session Credentials** also revoke dependent reader
credentials. Unlock the matching ZIP and reopen documents to resume I/O. Already
visible text/images may remain in memory until their windows close. Session-only
storage does not promise secure erasure of process memory.

Do not move or rename the credential ZIP without planning to recreate its local
mapping: the absolute ZIP path participates in the copy's identity. Missing or
invalid mappings block Push, including a LocalCrypt directory selected through an
ordinary folder's **Specific folder** option.

If a move saves the verified destination but cannot finish removing the source,
the error says so. Keep the destination and refresh both locations before deciding
what remains to delete; do not repeat the entire move. A partial deletion can leave
some source entries. Save verification failures preserve the original and your draft.

Ordinary desktop editors and raw file-browser operations cannot modify the
LocalCrypt backing directory directly, including through a symlink or an operation
on a containing folder. Editor Open and Save As now offer one browser: choose
Local files or a LocalCrypt location, then navigate decoded folders and names.
Selecting LocalCrypt applies name and content encryption together. Saving out to
Local files explicitly creates plaintext. Private text/Markdown drafts stay in
memory, including after export; Save As preserves the original and requires a
new destination name.


### Push checks and generated junk

Before a LocalCrypt push, Logistics removes raw and encrypted `.DS_Store`, `Thumbs.db`,
`ehthumbs.db` and `ehthumbs_vista.db` files (case-insensitive) throughout that copy.
Only independent regular files with these exact raw or decoded names are eligible.
Raw locally generated files are removed directly. Encrypted files are recognized
by their decoded names, authenticated, and deleted through the crypt provider.
Links and folders are never automatically removed. Corrupted encrypted junk
still blocks the push and is preserved for inspection. A normal ciphertext sync
also removes the deleted encrypted junk from its destination. Nothing else is deleted by this cleanup, including files matching your
custom exclusion patterns. Dry runs do not perform cleanup.

The Push review lists these local removals as **Cleanup**, and lists any resulting
remote removal as **Delete**. Unchanged encrypted junk is therefore shown as a
planned deletion, rather than hidden among matching files. Cancelling review
preserves both copies. Encrypted junk must still pass authentication before removal.

The cancellable check then validates every stored name and fully decrypts and
authenticates every file in memory. Plaintext with an encrypted-looking filename,
unknown names, corrupt ciphertext and files that change during checking refuse
the push. This reads the whole copy before transfer, so large copies take time.
Repair or move unexpected files explicitly; changing an exclusion cannot bypass
validation. The app does not create decrypted temporary files for this check.

**Settings → rclone → Push exclusions** controls one [rclone exclusion pattern](https://rclone.org/filtering/)
per line. Defaults skip common Finder/Explorer junk and AppleDouble sidecars.
These apply to local-to-remote pushes, including dry runs, and preserve excluded
files already at the destination. Pulls keep their existing behavior. Patterns
match the names passed to rclone: ordinary pushes use normal names; ciphertext
mirror pushes use encrypted stored names. They do not match decoded names in a
LocalCrypt mirror. Exclusions do not authorize local deletion.


The Local files destination may be rooted at your drive; moves still work when
LocalCrypt lives elsewhere on that same drive. Actual source/destination overlap
is refused. After Markdown Save As, document links follow the new storage location.


New LocalCrypt pulls use the remote's exact name, for example
`~/Library/Application Support/Logistics/LocalCrypt/Legacy-ComicRack` on macOS. Credential associations are kept in hidden
`.connections` records. If another credential package already owns that folder
name (including a difference only in letter case), Pull refuses to mix the copies;
rename the remote to a distinct folder name before pulling. Existing untracked
folders also block Pull. Old hashed-layout mappings are no longer loaded. Their
records and ciphertext are preserved; they are not automatically migrated, deleted or adopted by a new
mapping. An unsupported record for the same account blocks creating a replacement
mapping until it is explicitly resolved.
Remote names must be valid portable folder names.


Navigating into a mapped LocalCrypt copy from Logistics' regular File Browser now
opens its decoded browser tab automatically, reusing an existing tab for that copy.
Unlock the matching credential ZIP if prompted. The ordinary tab stays at its
previous location; encrypted contents are not listed there. Unmapped LocalCrypt
folders show an error instead of opening as ordinary files. Finder and other
external file browsers still show ciphertext names.

Workspaces shows a loaded credential's encrypted copy once. If both decrypted Local
and LocalCrypt copies exist, both remain selectable with short **Local** and
**LocalCrypt** labels. Hover an entry to see its complete source and path.

Private desktop browser tabs, text and Markdown editors, comic readers and metadata windows begin their titles with **🕵️ Private -**. The private browser shares the regular browser’s list, tile and column views, icon-size controls, navigation and folder breadcrumbs. Comic/EPUB covers and image thumbnails are generated on demand and kept only in memory. **Move into this folder…** groups file and folder imports in one toolbar menu. Open/Save As keeps the storage picker at the top and uses the same navigation style, without a side preview or storage maps.

Select a file in the private browser to see **File Information** and supported
**Comic Metadata** or **Book Metadata** in the right Preview panel. Column view
places these details in its final column. Preview can be toggled in list/tile view.
Images show a bounded preview and their width and height.
Two thumbnails load concurrently; larger archive ranges and scaled JPEG decoding
reduce repeated reads. Preview and thumbnail data remain in memory.

Credential unlocks for browsing, Push and Pull validate before closing the prompt.
A wrong password shows an error in that same prompt, clears the password field
and leaves it focused for another try. Enter submits once; Cancel abandons the
unlock without creating an empty private browser. Password-protected file opens
and metadata edits use the same retry behavior for inner archive passwords.

Workspaces keeps **Pull** and **Push...** available for LocalCrypt entries. Select the workspace to open its private browser in the Files pane. Tools that require ordinary local files (such as Calibre or Obsidian detection) are excluded from private copies.

### Session privacy

Desktop **Session only** keeps decoded credentials in the running application.
It does not expire when you navigate away or put the computer to sleep. Forgetting
or replacing the credential session revokes open private providers, clears their
caches and hides their document/browser/metadata windows. Reopen after unlocking;
old windows cannot resume under a new unlock. Cached stream reads also check the
session. This is not secure erasure of process memory.

Forgetting or replacing a desktop session also requests cancellation of its active
transfers, comparison previews and LocalCrypt commands. Re-unlocking cannot resume
those old jobs. Pending LocalCrypt command output is rejected after revocation;
destination changes already completed by a transfer remain.

On Android and iOS, loading session-only credentials immediately enables screen
privacy. Leaving the app locks access; returning requires the session password
while private edits remain in memory. Protection ends only after both credentials
and associated private views are cleared. Passwordless sessions require a temporary
lock password. See the [mobile privacy guide](../../../../../docs/user_mobile/navigation/panels.md#localcrypt-session-and-screen-privacy)
for capture behavior and platform limits.

Session mode does not remove credentials previously saved with **Save**, or your
original credential ZIP. LocalCrypt honors rclone filename settings: use standard
filename encryption and enable directory-name encryption to conceal stored names.
Remote names, package paths, ciphertext sizes and timestamps remain visible.
Desktop process inspection can expose rclone's decrypted path arguments and key
bearing environment. Thumbnails and private reading state stay in memory; explicit
Save As/Move to Local, exports and clipboard copies can expose plaintext.


### Mobile folder navigation

See [Rclone mobile workflows](../user_mobile/workflows.md#mobile-folder-navigation).

### Android collection drive

See [Rclone mobile workflows](../user_mobile/workflows.md#android-collection-drive).

### Side-by-side mobile credential packages

See [Rclone mobile workflows](../user_mobile/workflows.md#side-by-side-mobile-credential-packages).

### Mobile Workspaces source tabs

See [Rclone mobile workflows](../user_mobile/workflows.md#mobile-workspaces-source-tabs).


- [Choose rclone download versions](download-versions.md)

## LocalCrypt filename search

Search waits until you stop typing for 0.4 seconds, then searches the current
folder and every subfolder. Results include relative paths to distinguish equal
filenames. Desktop LocalCrypt uses one recursive listing per search. Search
reports listing errors instead of silently treating a partial scan as complete.
