# Using Text Editor

Open **Documents → Text Editor** or choose **Open in Text Editor** from File Browser. Use the context action to open Markdown source.

## Documents and saving

**Save** keeps the current location. **Save As** creates a separate copy. Closing a modified document offers Save, Discard or Cancel. **Save All** writes sequentially. Failed saves retain the buffer. If a file changes on disk, **Reload** discards edits after confirmation. **Keep Buffer** retains your changes. Use **Save As** to keep both versions or review **Merge…**.

Files are limited to 16 MiB. UTF-8 and BOMs are detected automatically. Choose the original encoding if decoding fails. Ordinary saves preserve encoding and line endings. **Force Open as Text** requires care with binary files.

## Editing and search

| Command | Shortcut |
| --- | --- |
| Find / Replace | Ctrl/⌘+F / Ctrl/⌘+H |
| Next / previous match | F3 / Shift+F3 |
| Go to line and column | Ctrl/⌘+G, then `line:column` |
| Duplicate line or selection | Ctrl/⌘+D |
| Delete line | Ctrl/⌘+Shift+K |
| Move selected lines | Alt+Up / Alt+Down |
| Toggle line comment | Ctrl/⌘+/ |
| Indent / unindent | Tab / Shift+Tab |

Search the current document by case, whole word, regex or captured selection. Regex replacements accept `\1`, `\g<name>`, `$1`, `${name}`, `\n` and `\t`. Replace All is one undo step.

## Appearance and preferences

Use the status bar for Encoding, Line Endings, Indentation or Syntax. Choose a language manually or use Automatic. **View → Logistics Settings…** opens [preferences](preferences.md).

**File → Keep Session and Close Editors** checkpoints buffers without writing originals. **Restore Editor Session…** opens an older available checkpoint. Recovery covers unsaved files and both views, up to 64 MiB and 100 documents. A crash can lose changes since the last checkpoint. Disk conflicts still apply. Private LocalCrypt buffers have no ordinary recovery.

## Text transformations and structured text

**Edit → Text Transformations** sorts, deduplicates, trims, converts case or tabs/spaces, and inserts line numbers. Line commands use selected lines or the whole document. **Tools → Format JSON/XML** and **Validate JSON/XML** act on the selection or document, up to 1 MiB. XML formatting refuses DTDs, mixed content and CDATA.

## Multiple cursors and rectangular selection

**Edit → Add Next Occurrence** (**Ctrl/⌘+Alt+D**) selects matching occurrences. **Alt-click** adds a cursor. **Alt+Shift-drag** selects a rectangle. Escape clears extra cursors. With one clipboard line per cursor, Paste fills them individually.

## Folding and two views

Use **View → Code Folding** or the gutter markers. Folding is limited to 256 KiB and 10,000 lines. **View → Document Views** splits one file. Text and undo are shared, and navigation follows the focused view.

## Comparing and discovering commands

**Compare → Compare with Disk / Another File** compares up to 1 MiB and 5,000 lines per side. **Use Left Change** applies an edit to the buffer for review and saving. **View → Find Command…** (**Ctrl/⌘+Shift+P**) shows commands and shortcuts. **Configure Shortcuts…** changes bindings or restores defaults.

### Merge changes from disk

Choose **Merge…** or **Compare → Merge Disk Changes…**. Apply non-conflicting changes, choose a side or edit and resolve each conflict, then Apply and save. Reopen the merge if the buffer or disk changes while reviewing.

## Change markers

Gutter marks compare the buffer with Git's index when available, or the last saved version. Click to inspect or **Revert change in buffer**. To stage a Git change, save first and use **Preview Git hunk to stage → Stage displayed Git hunk**. Review the whole patch, which can include nearby edits. Reopen stale reviews.

## LocalCrypt Open and Save As

Choose an unlocked LocalCrypt location in the shared picker. Private text is limited to 16 MiB and Markdown to 8 MiB. Private drafts and recent paths stay out of ordinary recovery. Save before closing. A failed save keeps the draft. Export to Local creates plaintext. Moving an ordinary draft into LocalCrypt does not erase older plaintext copies or backups.

## Notes Library and Documentation Library

See [Notes Library](../../notes_library/user/user.md#notes-library-and-documentation-library).

## Embedded source files in Notes Library

See [source files](../../notes_library/user/user.md#embedded-source-files-in-notes-library).

## JSON data views in Notes Library

See [data views](../../notes_library/user/user.md#json-data-views-in-notes-library).

## Markdown images

Use Markdown links or Obsidian embeds such as `![[images/photo #1.png|400]]`. Use `|400x200` to set both dimensions. Notes Library searches the note folder, library root and standard attachment folders. Explicit relative paths stay within the provider root.

## Notes Library document groups

See [document groups](../../notes_library/user/user.md#notes-library-document-groups).
