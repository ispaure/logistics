# Remote connections on mobile

## Remote files and credential ZIPs

Open a folder’s **•••** actions in **Workspaces**, then choose **Browse Remote** to open its
online file browser. Credential setup is under
**Settings → Workspaces → rclone connections…**. The native app embeds rclone 1.74.1; no desktop
executable, shell, mount, or separate RC server is required. **Advanced & troubleshooting → Check rclone engine**
performs an offline in-memory read and displays the engine version.

Home opens before saved connections finish loading in the background. You can
browse and open ordinary local files during that work. Saved connections load
automatically without a confirmation prompt or an online connectivity check;
connection badges update when ready. Opening a cloud-backed file waits for its
matching saved credentials. Password-protected session-only ZIPs still need their
password after a restart or lock. Push/Pull review and permanent local-folder
deletion retain their confirmation dialogs.
The editor-specific **Open / Save As** picker still waits for initial credential
loading because it includes encrypted destinations.

Workspaces's **Cloud** tab includes remotes from retained password-protected ZIPs
even before a local copy exists. Tap a locked remote to enter its ZIP password and
continue browsing online. A wrong password leaves it locked.

In Workspaces's **Cloud** and **Local** tabs, encrypted folders show a combined
folder-and-lock icon before their name. Blue open padlocks mean unlocked;
orange closed padlocks mean locked. Each folder reports its own state, including
mixed states within one group. Ordinary folders use a plain folder icon.
Cloud crypt folders use the lock icon even when there is no local copy. Unlocking
an older retained session-only ZIP repairs missing folder-type metadata, so the
crypt folders remain marked as locked after locking again or restarting. Older
entries without that metadata need one successful unlock before their type can
be shown correctly.
Group headings and nesting remain expanded and cannot be collapsed.

The online browser loads filenames and sizes without fetching thumbnails, in
both list and tile views. The current folder name stays in the header. Loading,
download progress and errors appear in a smaller status line beneath it, without
replacing the folder name. Opening a folder or file shows the current step and
elapsed seconds, with an animated progress bar. Remote previews report connection
checks, archive index reads and member/data reads; **Cancel** stops the pending
request. The elapsed time is a wait indicator, not a download percentage.

Tap **Import credential ZIP…** to open the separate import page and select your
existing Logistics credential package. Use **Choose credential ZIP…** to select
a different ZIP. Its filename appears under the button. Enter its password, then tap
**Load remotes** below the password field, or press Return. Leave the password
blank for an unencrypted ZIP. A failed load clears the password and keeps the
selected ZIP ready: correct the password and tap **Load remotes** again without
selecting the file again. After loading, choose a remote and tap **Browse folder**.
The ZIP password is never saved; selecting a ZIP alone does not load credentials
or connect to a remote. TXT entries must each contain one `[Remote name]`
section and rclone settings, including `type`. Plain, ZipCrypto and WinZip AES
packages are readable; importing never extracts files or modifies the source ZIP.
ZIPs are limited to 1 MiB, 64 entries and 256 KiB per TXT entry. Duplicate remote
names within a ZIP, unsafe archive paths and unsupported settings are rejected
before changing any loaded package. Reloading the same ZIP filename replaces only that package's
remote list; it makes no remote connection by itself.
Loading and unlocking work offline once the ZIP is available on the device.
If another operation is using credentials, loading returns a busy message
immediately. Stop that operation and retry; it does not queue behind a network
request or test the account online. Old network clients disconnect in the
background. Unlocking a remote to continue browsing resumes that online action
only after the local unlock succeeds.

This first mobile adapter includes Google Drive, Dropbox, OneDrive, S3 and WebDAV,
plus the memory backend used by the offline diagnostic. Existing authenticated
settings are required. It accepts a deliberately limited set of backend settings;
local paths, scripts, service-account files, mounts, alias wrappers and
other backends are not currently supported. WebDAV URLs and custom S3 endpoints
must use HTTPS. Certificate verification stays enabled. A single crypt layer over
one supported backing remote is available for [LocalCrypt reading](localcrypt.md#localcrypt-encrypted-offline-reading).

Choose a connection in Settings and tap **Browse remote files** to open the
browser. Tap folders to open them.
The header’s parent arrow moves up a folder; at the remote root it returns to
Workspaces. The bottom **Workspaces** tab also returns to the folder list. Tap supported files for read-only,
in-memory previews. Unsupported files show a dialog asking you to make a local
copy yourself. The remote browser has no file or folder download/copy actions;
use the managed Pull workflows to create or refresh offline folders.

Remote EPUB books and CBZ/ZIP comics download completely into memory once before opening.
The status shows downloaded MiB and percentage; subsequent page turns read that
snapshot without contacting the share. The cache allows up to 128 MiB per archive
and 256 MiB across open books and comics in all windows. Close a remote reader to free its
cache. Closing, locking or replacing credentials clears its cache; nothing is
written to disk. Larger archives require a managed local copy. To see changes made
to the online archive after it was cached, close and reopen the reader.

While an online request is running, Workspaces's action menus and local folders
remain available. Another online operation shows a busy message and **Cancel
current request** rather than silently waiting. LocalCrypt browsing can continue
during transfers and remote reads; credential replacement must finish first.
Returning to Workspaces and opening **•••** use the last discovered folder
metadata without rechecking rclone. Credential loading and **Refresh** update
encrypted-folder discovery in the background. Opening a mapped remote shows
**Checking connection…** while its identity and folder path are checked; menus
and navigation remain usable during that check.

Tap a file to open its preview or a folder to browse it directly. File browser
rows have no **•••** button. Opening a password-protected comic brings up its
inner ZIP password form automatically.
The browser status shows when a remote file is opening and reports opening failures.

The magnifying glass on the right reveals **Search**, which filters names in the
current folder. **×** clears and hides it. Changing folders clears search.
Tapping outside a search field dismisses the keyboard.
Remote listings read only the selected folder's immediate children. Remote
screens display up to 40 items per page in both List and Tiles, with **Previous** and **Next**
above the items; paging, sorting and filtering do not contact the remote again.
The status distinguishes **Listing…** from **Displaying…** and keeps an elapsed
timer while waiting. Workspaces and its action menus remain available during listing.
Failed navigation preserves the prior listing and history. Browsing has a
two-minute deadline; managed Sync has no fixed overall deadline. Cancellation
may wait for an upstream network call to return.

The remote browser uses a compact location header with a plain directory-name
label, storage and lock icons, and the search button. It omits item
counts and the Sort control. Progress and **Cancel** appear only
while a request is running.

**Save credentials on this device** is enabled by default. Turn it off before
importing to keep decoded credentials and the ZIP password only in memory for
this app session. Settings autosave never saves them. The original password-protected
ZIP is retained under device encryption for future password-only unlocking.
Unencrypted ZIPs must be selected again next time. A session-only
import leaves saved packages unchanged; **Reload saved credentials** reloads
saved packages while keeping currently loaded session-only packages active. Multiple
saved and session-only packages are supported together. Each ZIP filename
appears above the remote selector, so the package and its remote names stay associated.

Saved settings and refreshed OAuth tokens use an AES-256-GCM encrypted private
vault. Android Keystore protects its key, and the files are outside Android backup;
iOS Keychain stores a device-only key available while the device is unlocked, and
the vault folder is excluded from backup. Saved credentials restore during app
startup, before Home appears, without contacting a remote. Recent and Documents
show the restored connection state; opening a cloud file waits for any pending
restoration and continues directly. Session-only ZIPs still require their password
after restarting the app. The ZIP password is never saved, and neither
mode rewrites the source ZIP. A locked device, missing key or damaged vault stops
restoration; there is no plaintext fallback or silent replacement of saved data.
Unlock the device and reload, or use **Forget saved credentials** before reimporting.

Password-protected session-only credential ZIPs also have an **AES-256 ZIP** cache
for their open and recent file lists. It uses the same credential ZIP password,
with filenames and paths inside the encrypted payload. Unlocking that credential
restores the entries in the current window; file contents load only when selected.
The cache keeps no passwords, document contents or unsaved edits. Locking a session
preserves the encrypted cache while removing the visible entries. Unencrypted
credential ZIPs do not enable password-protected list caching.

**Forget saved credentials** unloads the active session and removes the saved
ciphertext, its known protected key, retained ZIPs and encrypted open/recent list
caches in every window, while preserving private downloads. Private
downloads follow the platform's normal app-data backup policy. Interactive OAuth
account setup remains future work. Session-only token updates are lost on exit;
providers that rotate refresh tokens may require a fresh credential package.

The main rclone page groups loaded packages with their saved or session-only
status and shows **Unlock** for retained, locked ZIPs. Import fields live on
the import page. **Reload saved credentials**, **Check rclone engine**, and
**Forget saved credentials** are under the initially collapsed
**Advanced & troubleshooting** section. **Lock connections** also locks active
SMB sessions.

SMB setup has its own **Settings → Workspaces → SMB shares…** page; see
[SMB and Mac shared folders](localcrypt.md#smb-and-mac-shared-folders).

### Locked credentials and Workspaces

Retained session-only ZIPs keep their remote names visible in Workspaces even
while locked and without a downloaded copy. Their credential filter remains
available. Tapping one asks for the matching ZIP password before browsing.
Wrong passwords keep the prompt open. The Settings connection page also offers
**Unlock** for each retained ZIP. Use **Choose credential ZIP** for a new ZIP or
one that was not retained. **Lock connections** clears decoded credentials
while keeping discoverable remote names, local copies, retained ZIPs and saved
credentials. Save or discard private edits
before locking. **Forget saved credentials** also removes retained ZIPs, keys and encrypted
open/recent list caches.

### Multiple credential packages on Android and iOS

Load each ZIP with **Save credentials on this device** set independently. For
example, load Personal with it on and Legacy with it off. Both remain active and
appear as separate credential groups in Workspaces; select **All** to see all
available folders. Connections lists each loaded package with **saved** or
**session only** status. **Show Legacy** still controls Legacy-prefixed groups
and folders on both platforms.

Up to 32 loaded packages are supported, with up to 64 configured remotes per
package. A ZIP filename identifies its package: reloading that filename replaces
only its active context. If two packages contain a remote with the same name,
the additional remote is qualified with its package name and an identifying
suffix. Their backing remotes, account identities and token updates remain
separate. Existing downloaded copies use their recorded connection identities
to resolve the matching loaded context.

Saved packages are encrypted in the private device vault and return after
restart. Session-only decoded credentials and resume-password verifiers remain
in memory. Session-only imports retain their original password-protected ZIP under device
encryption for password-only unlocking after restart. The ZIP and its remote
associations live in private app storage: `CredentialPackages` on iOS, and
`LogisticsCredentialPackages` in Android’s no-backup storage. Decoded credentials
and ZIP passwords are never written there. Reloading saved credentials does not discard
active session packages. Adding or refreshing a saved package never serializes
session-only contexts. Existing saved vaults migrate using their current device
key; package vaults use a new header which older builds refuse to load.

Loading a previously saved filename as session-only does not erase its older
saved copy; use Forget saved credentials if you want to remove saved secrets.
**Lock connections** unloads all active contexts. **Forget saved credentials**
retains its existing explicit all-credentials removal behavior.

## Folder search scope

Remote and PC-server search filters every entry in the active folder listing.
It does not descend into subfolders. Local and LocalCrypt search includes
subfolders recursively. Neither search has an entry or result count limit.
The browser shows up to 40 results per page; use the page arrows for more.

## Resuming a locked session

When the app locks a session after leaving the foreground, its unlock screen
shows the credential ZIP filename whose password is required. If several
credentials are locked, enter their passwords in turn; unlocked filenames
disappear from the list. A passwordless connection asks you to create a temporary
session password. These labels and password checks stay in memory.
