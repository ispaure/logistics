# LocalCrypt on mobile

## LocalCrypt encrypted offline reading

[Import a credential ZIP](connections.md#remote-files-and-credential-zips)
containing both a crypt remote and its supported direct backing remote. Select
the crypt remote under **Choose remote** and tap **Browse folder** to see
decrypted names.

To make an encrypted offline copy, see
[choose storage on the first pull](workflows.md#choose-storage-on-the-first-pull).
Open it under **Workspaces → Local → Rclone Copies**. Tap a locked encrypted
copy and enter its retained ZIP password. If you forget the package, the copy
stays on disk and needs a package with matching crypt settings to reopen.

## Search, move and save encrypted files

Search includes subfolders and reports unreadable paths. The filename index
can be cached encrypted under the ZIP password. Without that password, the
index stays in memory.

To move a file, choose **••• → Move…**, pick the destination folder, then tap
**Move here**. Moving into LocalCrypt encrypts names and contents according to
the remote settings. Moving to Local makes decrypted files and requires
confirmation. Moves require an unused name. Cross-storage moves verify the
new copy before deleting the source. If cleanup stops, inspect both locations
before retrying.

**Save As** switches future saves after reopening the destination. Confirm
before replacing an existing file or writing a decrypted copy. If a completed
save cannot reopen, your draft remains available. Inspect the destination
before retrying. See
[text editing](../../text_editor/user_mobile/user_mobile.md#plain-text-storage-and-platform-scope),
[notebooks](../../notebooks/user_mobile/user_mobile.md), and
[document session limits](../../../user_mobile/documents/reading-and-editing.md#reading-and-editing).

## Edit encrypted archive metadata

For a password-protected EPUB or comic, enter the inner archive password when
prompted. Use **Edit metadata… → Save encrypted metadata**. Logistics preserves
the archive contents, unrelated metadata, and the inner password. It verifies
the replacement before publishing it. Failed validation keeps the original
and your draft. Upload separately through a [reviewed Push](workflows.md#review-file-changes).

LocalCrypt previews read up to 16 MiB per archive member. See
[mobile comic page limits](../../comics/user_mobile/reading.md#supported-formats-and-page-limits).
Transfers and verified metadata saves stream data.

## LocalCrypt session and screen privacy

Private edits stay in memory. Save or discard them before locking. After
unlocking the session, a protected archive may ask for its own password again.
See [resuming a locked session](connections.md#resuming-a-locked-session) and
[mobile screen privacy](../../../user_mobile/settings/settings.md#screen-privacy-and-platform-limits).

LocalCrypt follows the remote’s filename encryption settings. Names can remain
readable if name encryption is disabled. File counts, ciphertext sizes,
timestamps and connection labels remain visible. Pull, move or Save As to
Local, exports and clipboard copies produce plaintext.
