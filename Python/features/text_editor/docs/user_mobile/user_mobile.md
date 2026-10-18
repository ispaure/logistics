# Text editing on mobile

The mobile app provides its text editor in Documents and Folder Hub.
See the [Documents and editing](../../../../../docs/user_mobile/documents/documents.md) guide for opening, editing, saving and exporting files.

Markdown opens in preview. The top **pencil** icon (**Edit Markdown**) opens a single formatted editing
surface; choose **Source** there for exact syntax. The Formatted/Source selector
is hidden while reading. The top **page** icon returns to preview. Save is shown
only after text changes, and disappears after saving or reverting. Reading uses
one compact top toolbar in portrait and landscape on iOS and Android, with no
separate edit/save footer or duplicate file-drawer row.
Background memory cleanup preserves the active Markdown reading or editing
surface when returning from sleep. Reading and formatted editing use the
platform's default font, including the device-selected sans-serif font on Android;
code retains a monospace font.
Open the **three-dot Document actions** menu in the editor or Markdown preview
and choose **Delete document…** to remove an app-stored document, including an
unsaved Untitled document. Confirm the warning to close it and permanently remove
its saved content, recovery copy and Recent entry. **Cancel** keeps it open.
**Close document** keeps the stored document; discarding changes only reverts edits.
Close other app windows before deleting. Files opened directly from a folder
continue to use that folder's file-management actions.
Choose **New document** from Home, Documents or Document actions to enter a name
and select the file type before creating it. Markdown offers an optional title
that becomes the first heading; the filename remains independently editable.
For a new Markdown document, tap anywhere in the blank writing area below the
formatting toolbar to place the cursor and open the keyboard.
Formatting and source share the same
buffer, recovery and Save actions. There is no automatic preview split on phones
or tablets. See [Reading and editing](../../../../../docs/user_mobile/documents/reading-and-editing.md)
for supported formatting and syntax that uses Source mode.

Rotating Android between portrait and landscape keeps the current Markdown
document open while the content reflows to the available width. A landscape
file sidebar collapses on return to portrait so the document uses the full
reading width; the hamburger can reopen the file drawer.

Tap the **speaker** icon in the Markdown preview or vault reader toolbar to open
**Read aloud** in a floating panel with speed, pause/resume and stop controls.
The panel leaves the page layout unchanged. Choose the saved offline voice in
**Settings → Read aloud → Read-aloud voice**. Select a passage to read it, or
play the whole rendered note. See [Reading and editing](../../../../../docs/user_mobile/documents/reading-and-editing.md#markdown-read-aloud).

Formatting controls use the same icons as desktop, including Bold, Italic, Undo,
Redo and the Format menu. Buttons keep accessible names and tooltips.

## Images in folder-backed Markdown

Markdown opened from Local or LocalCrypt displays static WebP, PNG and JPEG
images in preview and formatted editing. Use a path relative to the Markdown
file, for example `![Photo](images/photo.webp)` or `![[images/photo.webp]]`.
Parent-folder paths work within the same storage root. Bare filenames refer to
the Markdown file's folder; there is no vault-wide filename search.

LocalCrypt images are decrypted into memory for display; no decrypted image file
or separate import is created. Missing, locked, unsupported or oversized images
show their alternative text. Images are limited to 8 MiB and 16 megapixels each,
with a 16 MiB image-data budget per render. Animated WebP is unsupported.
Network URLs and paths outside the current provider root are not loaded.
Standalone imported Markdown without its original folder cannot resolve sibling
images; open the file through Local or LocalCrypt to retain folder access.

## Lock-screen speech

Markdown read-aloud shares the system playback controls used by EPUBs, including
Play/Pause and approximate 15-second skips. Session-only credentials require an
explicit saved opt-in for background speech; it defaults to off. See
[Speech while locked](../../../../../docs/user_mobile/settings/settings.md#speech-while-locked).

## Notes Library

From a Local, LocalCrypt or Remote location's actions page, choose **Open Notes
Library** when the root contains an `.obsidian` directory. The reader opens in
Documents with a folder/page sidebar, note history and read-aloud controls.
Folder and file icons identify each sidebar entry; the selected row is highlighted.
When the sidebar and page appear side by side, navigation, edit and read-aloud
controls sit above the Markdown page.
Remote libraries have no search or recursive index; folders load only when
expanded. Local filtering searches only loaded note names. Notes are read-only
in this view and limited to 2 MiB. Hidden configuration is excluded and links
stay inside the library.
