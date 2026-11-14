# Document workflows

## File actions and long names

Hold a file or folder, or tap its **•••**, to see its full name and actions.
Hold the name in that menu to see the full path. When naming a new document,
choose its format to set the extension. Folder names can include dots.

## Receive files from another app

1. On iOS, choose **Share → Logisticks**, wait for the result, and tap **Done**.
   Open Logisticks and find the copy in **Workspaces → Local → On My Phone**
   or **On My Tablet**. Apple Files shows it under **On My iPhone/iPad →
   Logisticks**.
2. On Android, share to **Logisticks**, wait for the result, and tap **Open
   Logisticks**. On a selected collection drive, files go to
   `<drive>/Logistics/Files`. If the drive is unavailable, completed handoffs
   wait in app storage.

Sharing leaves the originals in the sending app. Duplicate names get numbered
suffixes. Cancel keeps files already received. Retry attachments that report an
error. Received files start in ordinary unencrypted storage.

Choose **••• → Move…**, pick a writable folder, then tap **Move here**.
Moving an encrypted file into ordinary storage requires confirmation.
Moving or renaming an open text file keeps its draft, and the next **Save**
writes to the new path. Moving a folder also updates its open text files.
A conflict or external change preserves the draft. Close affected readers or documents open in another
window before moving them. Close a text file before renaming it to or from
Markdown. If reopening fails after a move, inspect the destination and use
**Save As** to preserve the draft.

## Document workflow

- **Create.** From Home or Documents, choose **New document**, pick a format,
  and name it. Tap **Next** on a narrow screen or use the folder
  pane on a wide screen. Choose a writable folder, create a subfolder if
  needed, and tap **Create here**. Resizing or going back to the name keeps the
  chosen folder. [Documents and readers](documents.md) lists supported locations.
- **Open.** Use **Open document** from Home or Documents. The folder arrow goes up
  a level. Android Back dismisses search or retraces folders before returning
  to the overview. **Documents → Open** lists active sessions. **Recent** lists
  closed sessions. If an old reference fails, open the file from its current
  folder, reconnect the remote, or unlock its credential.
- **Save.** Folder-backed files save to their original path. Use **Save As**,
  pick a writable folder, enter the name, then tap **Save here**. Choose an
  existing file to reuse its name. Confirm replacement when asked. If the
  destination changed during confirmation, review it before retrying. Save
  ordinary copies to Local and encrypted copies to LocalCrypt.
- **Copy through a provider.** **Import…** makes a private copy from the system
  picker. Text imports are limited to 1 MiB. UTF-8 and supported Unicode BOM
  encodings retain their line endings. **Export…** sends a copy of the current
  draft through the system picker. Save the document itself separately.
- **Close.** Tap **×**. If prompted, choose **Save**, **Quit without saving**,
  or **Cancel**. A failed save keeps the draft open. If there is a conflict,
  use **Save a copy** to preserve both versions.
- **Delete.** Choose **Document actions → Delete document…** for an app-stored
  document. Confirm to remove its saved file, recovery copy, and Recent entry.
  Close other app windows first.
- **Recover.** Draft edits are checkpointed during editing. If a restored item
  is unavailable, choose **Try again** or **Remove from open documents** to
  remove only its session entry. The default **Close saved documents on restart**
  keeps unsaved drafts and conflicts. Enable **Restore last document** to
  reopen the last eligible ordinary file. Session-only items need an unlock.
