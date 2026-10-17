# Documents and readers

Use the document workspace to return to open text, Markdown, books, comics and
conversations. Switching to another part of the app keeps these sessions available.

## Text and Markdown

Markdown opens with source and a live formatted preview together. On phones the
preview is below the editor; wider editor panes show it beside the source. It
updates after a short typing pause. Hide preview expands the editor; Live preview
restores it. Preview still opens a separate reading page, and Back to editor
returns to the same session. Preview has a 1 MiB source limit.

Text and source files have logical line numbers, monospace text and syntax colours.
Automatic detects the filename, or choose a language from the selector. Wrapped
continuations keep the same logical line number. Common source/configuration
files, including Python, JSON, YAML, shell and JavaScript, can be opened and saved
through the file picker. Highlighting pauses above 128 Ki characters while text
editing and line numbers remain available. The mobile editor retains native
keyboard, selection and undo; desktop folding and multiple cursors are not
provided by this control.

Local/private Markdown preview keeps the source visible while editing too. Remote
previews remain read-only. Save changes before closing a private draft.

## Books and comics

Open supported EPUB books and CBZ/ZIP comics in their readers. Reader controls
include navigation and Appearance. Reader settings are separate from the general
Text & Markdown font-size preference.

Settings → Books & Comics → Saved books & comics lists retained imports and their
space usage. Close removes an open view. Delete local copy removes that retained
import and its reading records after confirmation; it leaves the original source
file alone.

## Remote files

Open configured remotes from Folder Hub or Remote files. Supported remote documents
open read-only in memory within the reader limits. Direct remote reading does not
automatically create an offline copy. Use Folder Hub's managed Pull workflow when
you want an offline Local or LocalCrypt folder.

[Remote and offline files](remote.md) explains the difference.

## Related pages

- [Reading and editing on mobile](reading-and-editing.md)
- [Document workflows](workflows.md)
