# LocalCrypt on mobile

## LocalCrypt encrypted offline reading

Import a ZIP containing both a crypt remote and its supported direct backing
remote. Select the crypt remote under **Choose remote** and tap **Browse folder**
to see decrypted names.

For a managed offline copy, choose **Pull…** in Workspaces. For a new
session-only crypt copy, choose **Yes** to keep ciphertext or **No** for a
decrypted Local copy. Both persist on disk. New copies from saved credentials
and non-crypt remotes pull to Local. Later pulls retain the copy’s storage type.
Tap a locked encrypted copy and enter its retained ZIP password. Once unlocked,
you can read offline with matching credentials.

In Workspaces, open **On My Phone** or **On My Tablet** for ordinary files,
or **Rclone Copies** for your encrypted copy. Search includes subfolders and reports
unreadable paths. The filename index can be cached encrypted under the ZIP
password. Without that password, the index stays in memory.

For moves, choose the destination storage and enter a relative path including
the final name. Create the parent folder first. Moving into LocalCrypt encrypts
names and contents according to the remote settings. Moving to Local makes
decrypted files. Moves and Save As refuse occupied names. Cross-storage moves
verify the new copy before deleting the source. If cleanup stops, inspect both
locations before retrying cleanup. Confirm permanent deletions carefully.

Open Markdown to preview, then **Edit Markdown** or **Source** for exact syntax.
**Open** and **Save As** use the storage picker. Save As keeps the original file
and switches future saves after reopening the new file. If a completed save
cannot reopen, your draft remains available. Inspect the saved destination
before retrying. Export or save to Local only when you want a plaintext copy.

For a protected EPUB or comic, enter the inner archive password on opening.
Use **Edit metadata… → Save encrypted metadata** to update its fields. Saves
preserve archive contents, unrelated metadata and inner passwords and verify
the replacement before publishing it. A failed validation keeps the original
and your draft. Text saves preserve encoding, BOM and line endings. Upload
separately through a reviewed **Push**.

Text editing is limited to 1 MiB, archive members to 16 MiB and comic pages to
8 MiB and 16 megapixels. File transfers and verified metadata saves stream data.

### Open provider and private documents

**Documents → Open documents** holds up to four Local, LocalCrypt or remote
provider items with a shared 32 MiB retained-input limit. Open the same resource
to resume its existing session. **X (Close document)** or Android Back in the
main reader releases a slot. Save or explicitly discard private edits before
closing, changing credentials or mutating the file. Failed saves retain drafts.

Provider document titles, paths, drafts, bookmarks and positions stay in memory.
Reopen after restart. Forgetting credentials preserves ciphertext, but you
must reload matching crypt settings to unlock it.

### SMB and Mac shared folders

Open **Settings → Workspaces → SMB shares…**, or **Home Server → Add share…**.
Enter a unique name, server hostname/IP (without `smb://` or share path), and
account credentials, or select **Connect as guest**. The default port is 445.
Change domain or port under **Advanced options**. Choose **Connect & browse shares**.

**Save credentials on this device** defaults on and uses the device vault.
Turn it off for a temporary connection. Previously saved credentials remain.
On a Mac, enable **File Sharing** using SMB and grant the account access to the
folders. Connect from the same network or a reachable VPN. Try the IP if the
hostname fails. Open a share and choose **Pull…** for a managed copy. A network
or login failure keeps the connection available for retry.

For SMB in a ZIP, rclone accepts `host`, `user`, `pass`, `domain` and
`port`. The ZIP’s `pass` must be rclone-obscured. The direct form accepts
your ordinary password.

### Managed folder pulls

Use **Pull…** from Workspaces to create or refresh a mapped copy. Sync can
replace or delete destination files without a backup. **Skip preview and
start** still checks storage access and unsafe filesystem links.

### LocalCrypt session and screen privacy

Session-only credentials activate screen protection. Leaving the app or locking
the device covers private views. Enter the ZIP, connection or temporary session
password to return. Private edits stay in memory. A protected archive can ask
for its own password again. Lock passwords are never saved.

Android secure windows block ordinary screenshots and nonsecure capture. iOS
covers inactive views and detected recording or mirroring, but still screenshots
can capture visible content. External comic displays stay blank during private
sessions. These controls depend on the device.

LocalCrypt follows the remote’s filename encryption settings. Names can remain
readable if name encryption is disabled. File counts, ciphertext sizes,
timestamps and connection labels remain visible. Pull, move or Save As to
Local, exports and clipboard copies produce plaintext.

## Create and edit notebooks

Choose **Notebook (.rmdoc)** in New document and select an unlocked LocalCrypt
folder, or open an existing notebook there. Save keeps it encrypted. Exporting
or choosing Local asks before making a decrypted copy. Save or discard private
edits before closing or locking. See [Notebooks on mobile](../../notebooks/user_mobile/user_mobile.md).
