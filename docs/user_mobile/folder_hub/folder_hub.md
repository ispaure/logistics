# Workspaces on mobile

Open **Workspaces** for local files, managed copies, remotes and network shares.
Tap a folder to browse or use **…** for workspace actions. Wide windows keep the
workspace list beside the browser. Narrow windows open the browser on a separate
screen. Rotating or folding keeps your current folder.

| Source | Open it for |
| --- | --- |
| **Local → On My Phone / On My Tablet** | Ordinary files and incoming shares. |
| **Local → Rclone Copies** | Managed readable and encrypted copies. |
| **Cloud → Rclone Remotes** | Online folders from loaded credential packages. |
| **Home Server** | SMB or Mac shares added through **Add share…** and their offline copies. SMB remotes imported in a credential ZIP stay in Cloud. |

Use **Credential** in Rclone Copies or Cloud to narrow the list. Open a locked
folder and enter its ZIP password. If the source is missing, load or unlock the
matching package in [Remote connections](../../features/rclone/user_mobile/connections.md).
Use **Try again** if the workspace list failed to load. The folder-view button
switches between a hierarchy and a flat list.

## Notes Library

Use **… → Open as Notes Library** for a folder marked as a Notes Library or an
Obsidian vault. Search names and note text in local or unlocked encrypted
libraries. Use **Names only** to skip text search. See
[Notes Library on mobile](../../features/notes_library/user_mobile/user_mobile.md)
for supported files, editing and size limits.

## File browser locations and actions

Tap a folder to enter it or a file to open it. Back returns to the browser
with the same folder and search. Open sessions are also available under
**Documents**.
Use the magnifying glass to search and **×** to clear the filter. Local and
LocalCrypt search includes subfolders. Cloud and Home Server search filters the
current folder.

Use the **…** beside an item for **Details**, **Rename**, **Move** and other
eligible actions. Keep the app open during a long move. Switching apps or
locking the device interrupts the move. Check the result before retrying.

Use **Pin current folder** to add a local or remote shortcut to Workspaces.
Remote shortcuts require the same connection. Encrypted paths cannot be pinned
for restoration. Remove a pin to remove just the shortcut.

## Workspaces and Local / LocalCrypt sync

Choose **Pull…** to make a local destination match an online folder, or **Push…**
to make the selected online destination match the local copy. **Either action
can replace files and delete destination files missing from the source.**
Logistics does not create a backup of these changes.

Before the transfer starts, check **From**, **To**, and the list of additions,
replacements and deletions. Changed comparison results require another review.
**Proceed without full review…** skips the completed comparison and still
requires confirmation, credentials and destination checks. Cancel before
confirmation to leave the destination unchanged.

For a first pull from a session-only encrypted remote, choose a readable
**Local** copy or an **Encrypted Copy**. Encrypted copies retain the original
encrypted names and bytes. Later transfers reuse the existing location and
storage type. If more than one local mapping matches, choose the intended
destination before reviewing the transfer.

Tap the transfer indicator for progress or **Cancel**. Back closes the details
and leaves the transfer running. Only one transfer runs at a time. You can
browse existing local files during it. Finish edits before syncing their
folder. Cancelling an active transfer can leave completed writes and deletions
in place. See [rclone mobile workflows](../../features/rclone/user_mobile/workflows.md)
for review, retries and copy handling.

**Remove mapping (keep files)** detaches the association. **Delete local
folder…** permanently deletes the local folder after confirmation and keeps the
online copy.

## Local / LocalCrypt location

On Android, use **Settings → Workspaces → File storage…**. Keep Logistics open
until it verifies the copy and switches locations. **Use these files** selects
an existing collection after checking its folder paths. It does not verify file
contents. See [File storage](../settings/settings.md#file-storage) for permissions,
deletion and returning to an old location.

### Keeping your place during delayed opens

If you switch to another document while a private file opens, it stays available
under **Documents** without taking over your current view or draft.
