# Copy, move and recover documents

Start with the file's current location. If it is online or in an encrypted
folder on the device, use [remote and offline files](remote.md) to check
where changes can be saved. In a file list, hold an item or tap its **•••**
to see its full name and available actions. In that menu, hold the name
to see its full path.

## Browse in rows or tiles

In the Local File Browser, tap **Show tiles** in the folder toolbar for larger
previews. Tap **Show rows** to switch back. The browser keeps your folder,
selection and place in the listing. Filenames have two lines beneath the
preview. Tap the name to open a file or folder, or use **•••** in the
upper-right corner of the tile for item actions.

Images, notebooks, PDFs and comics in Local or unlocked LocalCrypt show
thumbnails as you browse, including in synced folders on your device.
Notebooks show a simplified first-page preview. A file icon appears while a
thumbnail loads or if a preview is unavailable. Online-only files keep their
file icons. Locking LocalCrypt clears its thumbnails.

## Receive files from another app

On iOS, use **Share → Logisticks**, wait for the result, and tap **Done**.
Open Logistics and find the file in **Workspaces → Local → On My Phone**
or **On My Tablet**. The same file appears in Apple's Files app under
**On My iPhone/iPad → Logisticks**.

On Android, share to **Logisticks**, wait for the result, and tap
**Open Logisticks**. On a selected collection drive, files go to
`<drive>/Logistics/Files`. If the drive is unavailable, completed handoffs
wait in app storage. Reconnect the drive to make them available.

Sharing puts a copy in ordinary unencrypted storage and leaves the original
in the other app. Duplicate names get numbered suffixes. If you cancel,
copies already received stay on the device. Retry attachments that reported
an error.

## Save or send a separate copy

Use **Save As…** to copy a draft to a writable folder. Name it and tap
**Save here**. You can pick an existing file in the save picker to reuse
its name, then confirm replacement. If the destination changes during
confirmation, review the file before retrying.

In an editor that offers **Import…**, the system picker supplies a private
app copy. Text imports accept up to 1 MiB. UTF-8 and supported Unicode BOM
encodings retain their line endings. **Export…** sends a copy of the current
draft through the system picker. Save the working document separately if
you also want to update it.

## Move or rename a file you are using

Choose **••• → Move…**, pick a writable folder, and tap **Move here**.
Moving a file out of an encrypted copy into ordinary storage requires
confirmation because the destination will be readable as an ordinary file.

In File Browser, use an item's actions to move a single file or folder.
To move several items together, choose **Select items**, tap each item,
then tap **Cut**. Browse to the destination and choose **Paste move here**.
With the listing focused, use **Command-X** and **Command-V** on iPhone or
iPad, or **Ctrl-X** and **Ctrl-V** on Android, for the same move. Tap the
destination listing before pasting if it needs focus. A focused search field
uses the text editing shortcuts.
Items that conflict stay at the source and remain cut. **Cancel move**
stops remaining work. Inspect both folders if a move stops after publishing
a verified destination.

Moving or renaming an open text file keeps its draft, and the next **Save**
writes to the new path. Moving a folder updates the open text files inside
it. Close affected readers or documents in other windows before moving
them. Close a text file before renaming it to or from Markdown.

A conflict or external change leaves the draft available. If the document
fails to reopen after a move, inspect the destination first, then use
**Save As** to preserve your draft.

## Recover a draft

A failed save keeps your edits open. If the saved file has changed outside
Logistics, use **Save a copy** to preserve your edits and the saved version
under separate names.

During ordinary editing, Logistics periodically stores a recovery draft.
An entry marked **Recovered draft** has edits to review and save. If a
restored item is unavailable, choose **Try again** after fixing access.
**Remove from open documents** removes its session entry only. The default
**Close saved documents on restart** leaves unsaved drafts and conflicts
available for recovery. **Restore last document**, also on by default,
reopens the last eligible ordinary file. Session-only files require an unlock, and private
text drafts are available only for the active session. Save those drafts
before locking the source.

## Delete an app-stored document

For an app-stored document, close other Logistics windows and choose
**Document actions → Delete document…**. Confirming removes the saved file,
recovery copy and Recent entry. For a folder-backed file, use the actions
from its folder.
