# LocalCrypt on desktop

Use [Pull](user.md#transfer-files) to create an encrypted copy from a
session-only crypt remote. Open it under **Workspaces → Local → Rclone
Copies** and unlock with the matching credential package. A private File
Browser tab shows decoded names. Open the file with a supported Logistics
reader or editor. Save an edit back to the copy, then run a separate
[reviewed Push](user.md#choose-the-sync-scope) to apply it online.
Use the [Text Editor storage picker](../../text_editor/user/user.md#localcrypt-open-and-save-as)
to save a text document elsewhere. Exporting to ordinary storage writes plaintext.

## Push checks and generated-file cleanup

Review LocalCrypt Push before writing. It can list cleanup of generated
metadata files and the related remote deletions. Custom exclusions do not
authorize local cleanup. If corrupted ciphertext blocks Push, preserve the
file and resolve the problem before retrying.

## Session privacy

Private thumbnails, preview data and unlocked credentials stay in memory.
Locking or replacing credentials retires the open private views. Save or
discard private drafts before locking. Keeping an encrypted copy on disk
still requires the matching credentials to reopen it.

## Search by filename

Open an unlocked LocalCrypt browser and use its filename search. The matching
names stay within the private session.
