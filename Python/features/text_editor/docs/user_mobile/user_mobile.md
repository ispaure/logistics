# Text editing on mobile

The mobile app provides its text editor in Documents and Folder Hub.
See the [Documents and editing](../../../../../docs/user_mobile/documents/documents.md) guide for opening, editing, saving and exporting files.

Markdown opens in preview. **Edit Markdown** opens a single formatted editing
surface; choose **Source** for exact syntax. Formatting and source share the same
buffer, recovery and Save actions. There is no automatic preview split on phones
or tablets. See [Reading and editing](../../../../../docs/user_mobile/documents/reading-and-editing.md)
for supported formatting and syntax that uses Source mode.

Markdown previews and vault notes offer **Read aloud**, with offline system
voices, speed, pause/resume and stop controls. Select a passage to read it, or
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
