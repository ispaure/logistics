# Using Text Editor

Open **Settings → Text Editor → Open Text Editor**, or right-click a text file in File Browser
and choose **Open in Text Editor**. Scripts, configuration and ordinary text open
there on double-click. Markdown keeps its existing reader; the right-click action
opens its source in Text Editor. Extensionless and unknown files are recognized
by a bounded content check rather than a restrictive extension list.

## Documents and saving

Use File → New/Open to create tabs. Drag tabs to reorder; use the close button,
middle-click or Ctrl/Cmd+W to close a tab. Ctrl+Tab switches documents. Reopening a
file selects its existing tab. A star marks unsaved changes; closing offers Save,
Discard or Cancel. Save keeps the original location; Save As selects a new one.

Save All processes modified documents in sequence. Reload from Disk asks before
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
light/dark palette and uses a monospace font by default. New tabs inherit your
saved preferences. Feature defaults live in `config.ini`; private overrides,
recent files and window geometry live under the commonUtils Cache/TextEditor
folder. **Reset Editor Preferences** removes overrides and restores feature defaults.

In the main app, Text Editor opens in **Open documents**. **Detach** moves the same
editor into a separate window; **Bring back** returns it without losing buffers.

Disabling Text Editor removes its browser actions but retains its open
buffers. Re-enable it to return to those documents. Browser windows do not own
editor buffers. Application closure still checks modified documents. Tabs are
not restored automatically after a restart; there is no autosave or crash recovery.
