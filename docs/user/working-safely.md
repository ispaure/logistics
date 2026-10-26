# Choose a location, save confidently and recover

Start with a disposable document while learning a storage workflow. Logistics
can show a live folder, an offline copy, a private encrypted copy or a remote
preview. The location determines where changes go.

## Choose the source that matches your task

| You want to… | Choose | What to expect |
| --- | --- | --- |
| Work with ordinary files | File Browser on desktop; Local/All files on mobile | Edits to folder-backed documents save to that file |
| Use a configured collection offline | Its Local copy in Workspaces | Changes stay local until you review Push |
| Keep an offline copy encrypted | Its unlocked LocalCrypt copy | Saved contents stay encrypted; private drafts remain memory-only |
| Inspect a remote file | Remote/Cloud browsing | Direct previews are read-only; opening does not automatically create an editable copy |
| Receive a file from another mobile app | Share to Logisticks, then Received Files | A copied attachment, separate from the sending app's original |

Desktop File Browser can browse ordinary folders outside configured collections.
Mobile All files is the app's available storage locations, not unrestricted access
to every device path. The [desktop file guide](files-and-documents.md),
[mobile document guide](../user_mobile/documents/documents.md) and
[remote/offline guide](../user_mobile/documents/remote.md) explain those boundaries.

## Create and find your first mobile document

Choose New document, enter a name, select Plain text, Markdown or Notebook, and
choose a writable destination. The current form shows the name, type and folder
together. Create document creates the file in that folder and opens it. Cancel
before creation creates nothing. A duplicate filename needs a different name;
do not assume creation replaces the existing file.

Save writes edits back to the opened file. Close uses the save/discard guard.
Return through Workspaces or All files to confirm the file is where you chose.
Existing legacy saved documents remain available in Documents; new folder-backed
documents do not require that older private store. See the
[current creation steps](../user_mobile/documents/documents.md).

## Know when you are making a copy

Importing or receiving an attachment does not grant write-back to the original
in another app. Export creates a separate copy. Save As chooses another
destination through the document's storage picker; read that editor's guide for
which document becomes active afterward. Notebook Save As switches the editor to
the new file, while Export .rmdoc leaves a separate export.

Before moving private content into ordinary storage, read the plaintext
confirmation. The new ordinary file is decrypted. Saving a private document
does not give it ordinary Recent/history/recovery storage. Save or explicitly
discard unsaved private edits before locking credentials.

## Review transfers before changing the remote

Pull prepares an offline copy from the selected source. Push sends reviewed local
changes back through the configured mapping. Confirm direction and both endpoints;
same-named Local and LocalCrypt copies can have different storage policies.
Inspect the proposed changes and conflict choices before approval. Do not assume
an edit in an offline copy has already reached the server.

If a transfer stops, inspect its result and affected destinations before retrying.
Cancellation may leave completed items. Keep the original and your draft until
the resulting files are verified. The [rclone guide](../features/rclone/user/user.md)
owns connection setup, Pull/Push and LocalCrypt details.

## Recover without overwriting the version you need

| Symptom | Next step |
| --- | --- |
| Save reports an external change | Keep the draft, inspect the saved version, then use Save As/export if needed |
| File was saved but its editor did not reopen | Inspect the destination before retrying; retain the draft and visible error |
| File is visible but name search misses it | Check index scope/progress/errors and refresh where offered; search metadata can lag behind live browsing |
| LocalCrypt content disappears after locking | Unlock the intended credentials and reopen; retired readers do not regain access automatically |
| Received Files seems unavailable on Android | Check that the selected collection drive is connected; completed incoming handoffs can wait for it |
| A remote preview offers no Save | Choose the managed offline-copy workflow, edit that copy and review Push |

Keep the application open while preserving an unsaved draft. Repeated retries
can obscure whether publication already succeeded. A useful report includes
platform, app/build version, location type, operation and exact error; exclude
credentials and private document contents.

For desktop tools, choose the [feature guide](features.md). For notebooks, use
[desktop](../features/notebooks/user/user.md) or
[mobile](../features/notebooks/user_mobile/user_mobile.md) instructions. For
connection/storage preferences, use [configuration](configuration.md).

[Using Logistics](user.md)
