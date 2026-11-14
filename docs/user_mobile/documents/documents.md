# Documents and readers

Open a file from **Home**, **Workspaces**, or the **Open document** action in Documents. The
storage row beneath the title shows its location, lock state, and whether it is
read-only. Images have previous and next controls for the same folder.

Home shows five recent files. **See all in Documents** opens the document
workspace. Choose **Libraries** for Notes and Comics libraries, the heart for
favourites, **Open** for active sessions, **Recent** for closed sessions, or
**Saved** for other saved documents. Tap the selected **Documents** tab again,
or choose **••• → All documents** in a reader, to see the list while keeping
your document open.

**Search documents** finds on-device filenames and folders, including unopened
files and unlocked LocalCrypt items. For results with a browsable source, choose
**••• → Show in folder**. Tap **×** to leave search.
Use **Unlock LocalCrypt** on Home, Workspaces, or Documents to unlock a
retained credential. Search reports locations it could not access.

To create a file, choose **New document**, enter a name, and select Text,
Markdown, or reMarkable Notebook. Tap **Next** on a narrow screen. Select **On My Phone** or **On My Tablet**, an individual rclone
copy, or an unlocked **Encrypted Copy**. Use **New folder** if needed, then tap
**Create here**. **Save** writes back to the chosen file. LocalCrypt saves stay
encrypted. Cloud and Home Server readers stay read-only. Use reviewed **Push**
to send changes from a managed copy. See [Notebooks on mobile](../../features/notebooks/user_mobile/user_mobile.md).

## Text and Markdown

Markdown opens in preview. Tap **Edit Markdown**, choose **Formatted** or
**Source**, and switch back to preview to check the same draft. New files start
in edit mode. Above 1 MiB, use Source. The text and source editor offers logical
line numbers and language selection. Syntax highlighting pauses above 128 Ki
characters.

## Save As and closing

**Save As** lets you pick a destination for a copy. Cancel returns to the same
draft. Tap **×** to close, then choose **Save**, **Quit without saving**, or
**Cancel** if prompted. A failed save keeps your edits available.

## Show a document's folder

Choose **••• → Show in folder** to reveal a file with a browsable source in
Workspaces. The reader stays open in its original tab. Unlock a private
session first to reveal its folder.

## Books and comics

Open EPUB books and CBZ/ZIP comics directly. Use reader **Appearance** or
pinch to adjust EPUB text size. Settings offers separate sizes for Markdown,
Text, and EPUB. **Settings → Reset → Clear cached documents** removes redundant
legacy imports and their reading records only when they match an available
original. Closing a reader keeps its saved file.

## Remote files

Open supported remote files read-only. To keep one offline, download a copy or
pull to a managed Local or LocalCrypt folder.

[Remote and offline files](remote.md) covers the limits and both copy workflows.

## Related pages

- [Reading and editing on mobile](reading-and-editing.md)
- [Document workflows](workflows.md)

## Markdown images from Local, LocalCrypt and Remotes

Use `![Photo](images/photo.webp)` or `![[images/photo.webp]]` for a relative
image. Preview and formatted editing support WebP, PNG, JPEG, and GIF.
LocalCrypt and remote image bytes stay in memory. Notes Library also checks
library-root paths and common attachment folders.
See [supported image paths and limits](../../features/text_editor/user_mobile/user_mobile.md#images-in-folder-backed-markdown).

## Favourite files

Choose **••• → Favourite file**. Home shows favourites above Recent. A note
favourited inside Notes Library reopens there. Session-only favourites stay
hidden until you unlock their credential.
