# Remote connections on mobile

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
names within a ZIP, unsafe archive paths and unsupported settings are rejected
before changing any loaded package. Reloading the same ZIP filename replaces only that package's
remote list; it makes no remote connection by itself.

This first mobile adapter includes Google Drive, Dropbox, OneDrive, S3 and WebDAV,
plus the memory backend used by the offline diagnostic. Existing authenticated
settings are required. It accepts a deliberately limited set of backend settings;
local paths, scripts, service-account files, mounts, alias wrappers and
other backends are not currently supported. WebDAV URLs and custom S3 endpoints
must use HTTPS. Certificate verification stays enabled. A single crypt layer over
one supported backing remote is available for [LocalCrypt reading](localcrypt.md#localcrypt-encrypted-offline-reading).

Choose a connection and tap **Open remote**. **Connections…** opens credential
setup. Tap folders to open them; **Back** returns through successful visits.
**Folder Hub** returns to the folder list. Tap supported files for read-only,
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

**Search** filters names in the current folder. Changing folders clears search. Tapping outside a search field dismisses the keyboard.
Remote listings read only the selected folder's immediate children. Remote
screens display up to 500 items per page in both List and Tiles, with **Previous** and **Next**
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
import leaves saved packages unchanged; **Reload saved credentials** reloads
saved packages while keeping currently loaded session-only packages active. Multiple
saved and session-only packages are supported together. Each ZIP filename
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

### Multiple credential packages on Android and iOS

Load each ZIP with **Save credentials on this device** set independently. For
example, load Personal with it on and Legacy with it off. Both remain active and
appear as separate credential groups in Folder Hub; select **All** to see all
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
in memory. Their original password-protected ZIPs can be retained in additionally
device-encrypted form for password-only unlocking after restart; each retained
ZIP contains only its own package. Reloading saved credentials does not discard
active session packages. Adding or refreshing a saved package never serializes
session-only contexts. Existing saved vaults migrate using their current device
key; package vaults use a new header which older builds refuse to load.

Loading a previously saved filename as session-only does not erase its older
saved copy; use Forget saved credentials if you want to remove saved secrets.
**Lock credential session** unloads all active contexts. **Forget saved credentials**
retains its existing explicit all-credentials removal behavior.
