# Using Text Editor

Open **Settings → Text Editor → Open Text Editor**, or right-click a text file in File Browser
and choose **Open in Text Editor**. Scripts, configuration and ordinary text open
there on double-click. Markdown keeps its existing reader; the right-click action
opens its source in Text Editor. Extensionless and unknown files are recognized
by a bounded content check rather than a restrictive extension list.

## Documents and saving

Use File → New/Open to create document panes. Each file uses the same tabs as
other readers; there is no second tab bar inside the editor. Drag a document tab
to detach it or split the view; its X or Ctrl/Cmd+W closes only that document.
Reopening a file selects its existing pane. A star marks unsaved changes; closing
offers Save, Discard or Cancel. Save keeps the original location; Save As selects
a new one.

Save All saves open text documents in sequence. Close All closes text document
panes, stopping if you cancel an unsaved-changes prompt. Reload from Disk asks before
discarding edits. A disk-change banner offers Reload or Keep Buffer. Keeping the
buffer does not overwrite the external version: choose Save As to preserve it.
Failed saves keep the buffer and explain the problem. Read-only files can be
edited for Save As, but their original permissions are never changed for you.

UTF-8 and Unicode BOMs are detected automatically. When decoding fails, select
the original encoding, such as Windows-1252. Likely binary files require explicit
approval or **Force Open as Text**. Forced opening does not make a binary format
safe to edit. Very large files are refused, and files over 1 MiB use simpler
presentation. Ordinary saves preserve encoding, endings and final-newline behavior.

## Editing and search

File/Edit menus use the platform's conventional shortcuts for open/save,
undo/redo, clipboard and selection. Other useful commands:

| Command | Shortcut |
| --- | --- |
| Find / Replace | Ctrl/Cmd+F / Ctrl/Cmd+H |
| Next / previous match | F3 / Shift+F3 |
| Go to line and column | Ctrl/Cmd+G, then `line:column` |
| Duplicate line or selection | Ctrl/Cmd+D |
| Delete line | Ctrl/Cmd+Shift+K |
| Move selected lines | Alt+Up / Alt+Down |
| Toggle line comment | Ctrl/Cmd+/ for supported languages |
| Indent / unindent | Tab / Shift+Tab |
| Zoom | Ctrl/Cmd+Plus/Minus; Ctrl/Cmd+wheel where supported |

Search stays in a nonmodal panel. It supports case, whole words, regex, wrapping
and a captured selection scope. Select a region before checking **In selection**.
Regex replacements accept `\1`, `\g<name>`, `$1` and `${name}`, plus `\n`/`\t`.
Replace All is one undo step. Close the panel with Escape. Search is limited to
the active document; Find in Files is not included.

## Appearance and preferences

The status bar shows position, line count, selection size, encoding, endings,
indentation and syntax. Click Encoding or Line Endings to convert on the next
save; conversions are explicit. Click Indentation to select tabs/spaces and width,
or Syntax to choose a language manually. Plain Text disables highlighting.

View offers font selection, wrapping, line numbers, whitespace, automatic
indentation and optional bracket/quote pairing. The editor follows Logistics'
light/dark palette and uses a monospace font by default. New documents inherit your
saved preferences. Feature defaults live in `config.ini`; private overrides,
recent files and window geometry live under the commonUtils Cache/TextEditor
folder. **Reset Editor Preferences** removes overrides and restores feature defaults.

In the main app, Text Editor opens in **Open documents**. Drag its tab outside
the window to detach it; **Bring back** returns it without losing edits.

Disabling Text Editor removes its browser actions but retains its open
buffers. Re-enable it to return to those documents. Browser windows do not own
editor buffers. Application closure still checks modified documents. Open sessions are checkpointed privately while you work and restored when you next
open Text Editor. Recovery includes unsaved Untitled buffers, edits, encoding and
line-ending choices, cursor/selection and scroll positions, and both document views.
Application shutdown waits for a durable checkpoint and retains editor buffers;
closing an individual document still asks Save/Discard/Cancel. If checkpointing
fails, ordinary save prompts remain in effect. Recovery never writes your original
files. Disk changes since a checkpoint retain normal conflict protection.

**File → Keep Session and Close Editors** also suspends standalone editors.
**Restore Editor Session…** lets you select an older checkpoint; sessions held by
another running instance cannot be restored. Checkpoints live in private
Cache/TextEditor/sessions files, with a 64 MiB total and 100-document limit.
Checkpoints run about one second after changes; a crash can lose changes made
since the last completed checkpoint. Corrupt checkpoints are retained for inspection.


## Text transformations and structured text

**Edit → Text Transformations** offers sorting, duplicate removal, trailing-space
trimming, case conversion, tab/space conversion, and numbered lines. Line commands
operate on complete selected lines, or the whole document without a selection.
Case commands use the selection or current word. Conversion to tabs affects leading
spaces only. Each transformation is one undo step.

**Tools → Format JSON/XML** formats the selection, or the document without a
selection. **Validate JSON/XML** reports syntax errors without changing text.
JSON formatting preserves numeric tokens and duplicate keys. XML formatting
preserves comments but refuses DTD/entity declarations, mixed content, CDATA,
and xml:space="preserve" content; mixed content and CDATA can still be validated.
Formatting/validation is limited to 1 MiB of text.

## Multiple cursors and rectangular selection

Use **Edit → Add Next Occurrence** (Ctrl/Cmd+Alt+D) to select the current word and
add matching occurrences. Alt-click adds a cursor; Alt+Shift-drag makes a rectangular
selection. **Rectangular Selection from Selection** converts an existing selection
into a column selection. Short lines clamp at their end; virtual columns are not
inserted. There is a limit of 1,000 cursors.

Typing, deletion, Enter/Tab, optional pairing, copy/cut/paste and simple input-method
commits work across cursors. A paste containing exactly one line per cursor fills
those cursors individually; other text is pasted at every cursor. Escape clears
extra cursors before dismissing search. Unsupported navigation/commands return to
one cursor, and edits through another view clear stale extra cursors.

## Folding and two views

**View → Code Folding** toggles the current region or folds/unfolds all regions.
Click a gutter +/− marker to fold a region. Folding uses indentation for Python/YAML,
tags for XML/HTML, and lexical delimiters for other highlighted languages; it is
structural rather than a language parser. Folding is disabled above 256 KiB or
10,000 lines. Search and Go to Line reveal hidden destinations; editing expands
folds before refreshing the regions. **Indentation Guides** can be toggled in View.

**View → Document Views** splits one document side by side or above/below. Both
views share text, undo history, folding and save state, with independent navigation.
Commands and search follow the focused view. **Single View** removes the extra view.

## Comparing and discovering commands

**Compare → Compare with Disk / Another File** opens a read-only side-by-side view
and a unified diff. Previous/Next visits changes. **Use Left Change** copies the
selected disk/file change into your buffer in one undo step; it never saves the
file. Reopen comparison after applying a change. Applying changes is blocked if the
buffer changed after comparison. The disk-change banner also offers Compare.
Comparison is limited to 1 MiB and 5,000 lines per side.

**View → Find Command…** (Ctrl/Cmd+Shift+P) searches editor commands and displays
shortcuts. **Configure Shortcuts…** saves bindings globally for editor panes,
rejects conflicting bindings and offers Restore Defaults. Clear a binding in the
shortcut field to remove it. Shortcut choices are saved separately from normal
editor preferences.
