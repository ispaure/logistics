# Documents and readers

Use the document workspace to return to open text, Markdown, books, comics and
conversations. Switching to another part of the app keeps these sessions available.
On iOS, the top navigation bar shows the opened document's name, including files
opened from local, remote and encrypted storage. Fullscreen reading hides the bar
until you show the reading controls again.

## Text and Markdown

Markdown files open in preview. **Edit Markdown** enters a single formatted
editing surface; **Source** shows the exact Markdown instead. Phones and tablets
use the same mode switch, without a second preview pane. **Preview** returns to
reading the current draft. New Markdown documents start editing. Preview and
formatted editing have a 1 MiB source limit; larger documents use Source.
See [Reading and editing](reading-and-editing.md) for supported formatting.

On Android 12 and newer, Markdown preview and formatted editing use the native
app font, including device font customizations when Android exposes the font.
Code remains monospace. Older Android versions use the platform font fallback.

Text and source files have logical line numbers, monospace text and syntax colours.
Automatic detects the filename, or choose a language from the selector. Wrapped
continuations keep the same logical line number. Common source/configuration
files, including Python, JSON, YAML, shell and JavaScript, can be opened and saved
through the file picker. Highlighting pauses above 128 Ki characters while text
editing and line numbers remain available. The mobile editor retains native
keyboard, selection and undo; desktop folding and multiple cursors are not
provided by this control.

Local/private Markdown uses the same Formatted/Source switch and opens in
preview. Remote previews remain read-only. Save changes before closing a private
draft.

## Books and comics

Open supported EPUB books and CBZ/ZIP comics in their readers. Reader controls
include navigation and Appearance. Reader settings are separate from the general
Text & Markdown font-size preference.

Settings → Books & Comics → Saved books & comics lists retained imports and their
space usage. Close removes an open view. Delete local copy removes that retained
import and its reading records after confirmation; it leaves the original source
file alone.

## Remote files

Open configured remotes from Workspaces or Remote files. Supported remote documents
open read-only in memory within the reader limits. Direct remote reading does not
automatically create an offline copy. Use Workspaces's managed Pull workflow when
you want an offline Local or LocalCrypt folder.

[Remote and offline files](remote.md) explains the difference.

## Related pages

- [Reading and editing on mobile](reading-and-editing.md)
- [Document workflows](workflows.md)

## Markdown images from Local and LocalCrypt

Folder-backed Markdown displays WebP, PNG and JPEG images in preview and formatted
editing. Both `![Photo](images/photo.webp)` and `![[images/photo.webp]]` resolve
relative to the Markdown file. LocalCrypt image bytes remain in memory.
See the [Text Editor mobile guide](../../../Python/features/text_editor/docs/user_mobile/user_mobile.md#images-in-folder-backed-markdown)
for supported paths and image limits.
