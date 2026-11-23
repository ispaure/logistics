# Workspaces on mobile

Use **Workspaces** when you want to browse files where they are stored.
For instance, open **Local → On My Phone** or **On My Tablet** to find a
note you made in Logistics or a file another app shared with it. Tap a
folder to enter it and a file to open it. You can return to the folder
with Back or resume the file later from **Documents → Open**.

## Choose the folder to browse

| Source | What you will find |
| --- | --- |
| **Local → On My Phone / On My Tablet** | Ordinary files and files shared with Logistics. |
| **Local → Rclone Copies** | Managed offline copies, including readable copies and encrypted LocalCrypt copies. |
| **Cloud → Rclone Remotes** | Online folders from loaded credential packages. |
| **Home Server** | [SMB or Mac shares](../../features/rclone/user_mobile/connections.md#smb-and-mac-shared-folders) added through **Add share…** and their offline copies. SMB remotes from credential ZIPs appear in Cloud. |

Read [remote and offline files](../documents/remote.md) to see where you can
edit and when an encrypted folder needs a password. Use **Credential** to
narrow the Rclone Copies or Cloud list. If your folder is missing, load or
unlock the matching package in [Remote
connections](../../features/rclone/user_mobile/connections.md). If the list
failed to load, tap **Try again**.

Wide windows show the workspace list beside the browser. Narrow windows
open the browser on its own screen. Rotating or folding keeps your current
folder. The folder-view button switches between a hierarchy and a flat list.

## Search and act on a file

Tap the magnifying glass and type a filename or part of it. Local and
LocalCrypt search covers subfolders. Cloud and Home Server search filters
the folder you are viewing. Separate words may appear in any order. Put
a phrase in quotes to match it in order. Tap **×** to clear the filter.

If a large ordinary folder takes time to search, the app may show saved
matches while it checks them. **Checking…** means those checks are still
running. Tapping a saved result checks that file immediately. A result
that is missing or inaccessible leaves the list and shows a message.
Private names stay out of the saved local index.

Tap **…** beside an item for eligible actions such as **Details**,
**Rename** or **Move**. Keep the app open during a long move. Switching
apps or locking the device interrupts the operation, so inspect the
destination before retrying. See [moving a file you are
using](../documents/workflows.md#move-or-rename-a-file-you-are-using) if
the file is open in an editor.

Use the open folder’s **…** button beside its view controls to create a
**New folder…** or enter **Select items**. An individual item's menu
offers **Move…** and, where the storage supports it, **Duplicate…**.

On iPhone and iPad, press and hold a file or folder in List or Tiles,
then drop it on a folder in the same writable location. If that folder
already contains an item of the same name, the move stops and both
items stay in place.
Keep holding over a folder to make it flash twice and open. Continue
dragging to another folder, or release to move the item into the open
folder.

Tap **Transfers** below the Workspaces source tabs to see transfer
progress or find interrupted downloads.

## Notes Library

For a folder marked as a Notes Library or an Obsidian vault, choose
**… → Open as Notes Library**. Search filenames and note text in local
or unlocked encrypted libraries. Use **Names only** to skip text search.
See [Notes Library on mobile](../../features/notes_library/user_mobile/user_mobile.md)
for supported files, editing and size limits.

## Keeping your place during delayed opens

If you switch to another document while a private file opens, the newly
opened file appears under **Documents** and your current view stays in place.

## Workspaces and Local / LocalCrypt sync

Tap **…** for workspace actions. **Pull…** updates an offline copy from
the online folder. **Push…** updates the online folder from the managed
copy. Either direction can replace files and remove destination files
that are missing from the source. Finish edits and review the proposed
changes in [remote transfers](../../features/rclone/user_mobile/workflows.md)
before starting the sync.

**Remove mapping (keep files)** detaches the association. **Delete local
folder…** permanently deletes the local folder after confirmation and keeps
the online copy.

## Local / LocalCrypt location

On Android, choose **Settings → Workspaces → File storage…** to change
where collections live. Keep Logistics open if you choose to copy files
and switch. **Use these files** selects existing collection folders after
checking their paths. To verify file contents during a move, use the copy
and switch option. See [file storage](../settings/settings.md#file-storage)
for permissions, deleting an inactive copy and returning to an old location.

## Select several files

Choose **Select items** from the folder or item menu. Tap the circles before
the filenames or tap the rows. The selection bar shows the number selected and
the available group actions, including **Move…** and **Archive**. Use **Done**
to leave selection mode.
