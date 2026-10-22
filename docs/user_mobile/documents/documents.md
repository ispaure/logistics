# Documents and readers

Use the document workspace to return to open text, Markdown, books, comics and
conversations. Switching to another part of the app keeps these sessions available.
Tap **Documents** while that tab is already selected to return to the Documents
list without closing the current document. Switching to Documents from another
tab resumes any document already displayed within Documents; otherwise it shows
the list. Tap Documents again to see the list.

Home provides Open/New actions and five recent files. **See all in Documents**
opens the full workspace, where **All open** puts the active document first and
provides close controls. **Recent** lists closed history entries, and **Saved
documents** lists other saved text and Markdown files. **Search documents**
filters all three sections by filename. **Open Books & Comics library** is available
below those lists. Empty lists show plain informational text without a rounded block.

In a book, comic or provider-backed document reader, open the **…** actions menu
and choose **All documents** to return to the Documents list without closing the
document. Opening a document from Home or Workspaces keeps that tab selected.
iOS navigation Back and Android system Back return to the retained opening screen
without closing the session. Android may first dismiss reading controls or
fullscreen mode.
While a file downloads or prepares to open from Home, Documents or Workspaces,
a separate panel shows its file icon, name and loading bar.
Measured full-file reads show **Reading N%** when the size is known, or
**Reading file…** when it is not. The bar switches to **Preparing document…**
while decoding and the first page finish. Opening paths that read selected
ranges, including PDFs, keep an indeterminate bar. The reader replaces the panel
when ready. Back returns to the opening screen, including when used
before loading finishes. Failed opens return to that screen too.
On iOS, the top navigation bar shows the opened document's filename with its
extension, without the folder path, including files opened from local, remote
and encrypted storage. Fullscreen reading hides the bar
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

Preview and Edit are modes of one document screen. Switching between them keeps
the same draft and does not add a Back step; Back returns directly to the screen
that opened the document.

## Save As and closing

Cancelling Save As or dismissing its picker returns to the document that opened
it, including an unsaved new draft. It does not switch to an earlier open file.
When closing asks you to Save, Discard or Cancel, Cancel keeps the document open;
a failed save keeps edits available for retry. If the document changes while a
close prompt is open, its old answer is ignored rather than applied to the new
state. Return to the document and close it again if needed.

## Show a document's folder

Choose **Show in folder** from the document's **…** actions menu to browse its
source in Workspaces with the file selected. The reader stays open in its
original tab, including unsaved text. On iOS, Back in that browser moves through
parent folders, then returns to the Workspaces overview at the storage root.

The action appears for folder-backed local, encrypted and remote documents.
Local imports opened from the app's file browser retain their source location
for the current app run. Imported copies without a known accessible source,
new app-owned documents and locked private sessions omit the action.

## Books and comics

Open supported EPUB books and CBZ/ZIP comics in their readers. Reader controls
include navigation and Appearance. Reader settings are separate from the general
Markdown font-size preference. Text has its own font size under Settings → Text,
and EPUB under Settings → EPUB. Pinch with two fingers in a reader or editor to
change that format’s size (12–32); it is saved on this device. Markdown source,
formatted editing and preview share one size, and text viewing and editing share
one size. Existing shared sizes migrate to all three settings.

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
