# Using IDE

Enable **IDE** in Settings → Features, then select its code icon in the navigation
rail, immediately before Git when both are enabled. IDE does not require Text
Editor, Git or any reader feature to be enabled.

## Projects

**+ → Register / Open existing project** selects an existing directory and lets you name it. Settings
accept one source directory per line (relative to the root or absolute), excluded
names/relative paths, and an optional Python executable or environment path (relative to the project root or absolute).
Use `.` for a flat Python project and `src` for a src-layout package.

Each full-width top-level tab is an independent project; two or more share the
available header width, with scrolling for overflow. **+ → Reopen project** lists
registrations. The + remains available with no projects open. Project tabs use the
same docking and detached containers as Documents. A detached window's + opens
projects there; a registration already open elsewhere moves its existing tab there.
A detached single project can hide its header while retaining + at the upper right.
**Project → Project Settings / Source Paths** configures the active project.
Closing a project keeps its registration and layout. **Remove registration** asks
for confirmation and removes only IDE metadata; it never deletes source files.
Missing roots and missing or temporarily unreadable open files remain recorded,
including their editor group and cursor position. Reopen once storage is available.
Changing a root in settings changes browsing and analysis; existing absolute document paths are not automatically relocated.

Configuration is versioned JSON at `IDE/workspace.json` beside Logistics
preferences: `~/Library/Application Support/Logistics` on macOS,
`%APPDATA%/Logistics` on Windows, and `$XDG_CONFIG_HOME/logistics` (normally
`~/.config/logistics`) on Linux. No project-local configuration is created.
Layout saves are debounced and flushed on close. Intervening instance changes are
rejected with a status message; restart to load the other instance's state.
Simultaneous writers are not protected by a cross-process lock.
Malformed configuration is retained and will not be overwritten automatically.

## Files and groups

Git's **Open working file in editor** action and ordinary file double-clicks
open files in registered IDE projects, including closed projects. Existing tabs
retain unsaved edits. Nested registrations use the most specific project root;
unregistered files use Text Editor. IDE must be enabled for this routing.
Diff review and conflict merging remain in the Git tab.

`.md` and `.markdown` files open in the Markdown editor as ordinary IDE file
tabs alongside code. Use **Formatted**, **Source**, or **Read** in the tab;
formatting, tables, properties, contents and Markdown find/replace are available
there. Formatted edits can normalize Markdown syntax; use Source for precise
syntax. Callouts and incomplete frontmatter select Source automatically.
Local Markdown links open another IDE tab without replacing the current file.
Project Save/Save All, Save As, Reload and unsaved-close prompts apply to these
tabs too. Markdown Save As requires a `.md` or `.markdown` filename.
Split views share Markdown source and modified state; each formatted view has
its own rich undo history. Source undo/redo is shared across views. Saved cursor
locations and go-to-line use Source mode.

The left tree lists folders before files, with natural filename ordering within
each group (for example, `file2` before `file10`). It loads directories lazily,
hides configured exclusions, and filters
filenames without recursively crawling the project. **Go to file** searches
relative paths in a background scan. **Locate file** selects the active document.
The tree menu creates files/folders, renames closed items, reveals the selected item
in the system file manager (with a containing-folder fallback on Linux), refreshes, and deletes files or empty folders
with confirmation. Close affected documents before renaming or deleting a subtree;
pending file opens also block these operations.
Recursive folder deletion is intentionally unavailable.

The browser and editor panels have font-scaled minimum widths and cannot collapse.
Editor tabs belong to their project. Drag onto a group header to insert/reorder,
into its center to merge tabs, or onto its left/right quarter to create a split.
A preview marks the target. Up to three groups are supported; a side drop at the
limit is rejected unless moving an existing single-file column, which can be
repositioned without adding a fourth group. Escape or releasing outside this project's editor area cancels.
Moving one single-file column beside another reorders the existing columns and
keeps the file's unsaved text, cursor and undo history. Release finishes the
originating drag even when the pointer crosses into the other editor.
Empty groups disappear after files move/close. **View → Split Editor Right**
adds a group showing another view of the current file, up to three groups. You can
edit either view: text, undo/redo, modified state and disk identity are shared.
Each view has its own cursor, selection and scroll position. Cursor and scroll
positions are restored on reopening the project; selections are not persisted. Folding is shared because it changes the common text layout.
With no active file, Split right adds an empty group.

**Move left/right** moves the current tab. If the destination already shows that
file, its existing view is selected and the redundant source view closes.
Closing a group moves its unique files into a remaining group and merges duplicate
views. Closing one view leaves its shared buffer alive in other groups; only
closing the last view prompts for unsaved changes. **Close all in group** follows
the same rule. Closing the project/application prompts once per modified file.
Internal tabs and groups cannot detach.

Opening an already-open file selects its view in the active group, or an existing
view in another group. Use **Split right** to open a second view deliberately.
**Save**, **Save As**, and **Reload** apply to all views of that file; Save As
changes the path and language for every view, while Reload replaces shared text
and resets its undo history. Separate projects keep independent buffers.

Save preserves encoding, BOM and line endings. Save As can replace an existing
file after confirmation and checks for intervening changes. Unicode encodings
are detected; a failed decode offers an explicit encoding choice. Binary content
and files over 16 MiB are refused. A star marks unsaved edits. Closing files,
projects or Logistics offers Save/Discard/Cancel. Failed saves retain your buffer.
Unsaved buffers are not crash-recovery checkpoints; save important work regularly.

External edits/removals produce a status message. **Reload** asks before discarding
unsaved text; saving refuses a conflicting disk version. Save As can preserve both.
Line numbers, bracket matching, indentation, undo/redo and shared line editing come
from the same CodeEdit used by Text Editor. **Find / Replace** opens its shared
search panel. File operations (including Save All and Close Project) live in **File**,
editing in **Edit**, group layout in **View**, navigation in **Navigate**, and
configuration in **Project**. These menus follow the active project/editor and
use the application's native macOS menu bar or the existing in-window menu on
Windows/Linux. Keyboard shortcuts remain available.

Code text defaults to 9 points and shares its saved size with Text Editor and
Git code panes. Ctrl+wheel zoom updates other open code panes and future views.
Line numbers resize with the font and line count.

## Python navigation and search

- **F12**: definition of a Python symbol. Ctrl-click (Command-click on macOS)
  jumps from a reference to its definition; clicking a function or class declaration
  instead lists its usages in the registered project.
  Hold Ctrl/Command over Python source for a pointing-hand cursor; a reachable
  symbol turns blue and underlined after background analysis. Releasing the key
  or moving off the symbol clears the link feedback.
- **Shift+F12** or **Navigate → Find usages…**: list usages of the symbol at the
  caret. Ctrl+Shift-click (Command+Shift-click on macOS) also lists usages. Choose
  a result to open its file and position; Back returns to where you searched.
  Results appear in a popup over the editor, with filename, line number and code
  preview. Filter by file/path or preview text; use arrows and Enter or click a row
  to open it. Escape or a click outside closes the popup without choosing a result.
- **Alt+Left / Alt+Right**: back/forward with cursor and approximate scroll position.
- **Ctrl/Cmd+P**: Go to file; **Ctrl/Cmd+L**: Go to line.
- **Ctrl/Cmd+Shift+O**: symbols in the current file.
- **Ctrl/Cmd+Space**: choose a basic completion.
- **Shift+F1**: inferred documentation.
- **Ctrl/Cmd+/**: comment/uncomment supported source languages.
- **Ctrl/Cmd+Shift+F**: case-insensitive project text search.

Jedi analyzes Python on background workers using the configured source paths and
optional interpreter. It follows common local definitions, imports, classes,
functions and statically inferable methods. No language server needs installation.
Usages are semantic references found by Jedi, capped at 200 and filtered to the
registered project outside its configured exclusions. Declarations and import
bindings are omitted; imported aliases and dynamic Python can have incomplete
results. Other files are analyzed from their saved content, so save changes first.
Missing Jedi disables analysis while editing remains available. Requests for
changed/closed source buffers are ignored. Dynamic references, unresolved imports
and builtins without navigable source can return no target. Other open files'
unsaved edits are not overlaid into Jedi's import analysis; save them first.

Quick-open caps traversal at 100,000 file/directory entries and shows at most 500 matches.
Project text search examines up to 10,000 files, skips binary/over-1-MiB files,
and returns up to 500 matching lines. Scans skip excluded folders and directory
symlinks. Search reads saved files, not unsaved editor content.
Analysis accepts up to 1,048,576 source characters. These tools are bounded searches,
not a complete background project index. Wait for active work before closing a
project or application, then retry closing.

## Languages and initial limits

Shared Pygments highlighting supports Python/stubs, JSON, YAML, TOML, XML,
Markdown, HTML, CSS, JavaScript, TypeScript, shell, batch, PowerShell, PHP and Blade,
along with the shared editor's C/C++, C#, Java, Rust, Go, SQL and INI grammars.
`.blade.php` is recognized before `.php`; Blade directives and single-line
expressions combine with HTML/PHP highlighting. Multiline Blade constructs have
limited highlighting. Unknown text remains editable as plain text. Colors follow
the application palette.

This initial IDE has no debugger, terminal, automatic diagnostics, automatic hover,
Git status UI or direct Git handoff. Git remains independently available in its own
feature. Navigation history is per open project session. File reads use workers;
bounded saves/reloads and small tree mutations currently run on the GUI thread.
Windows and Linux still require native desktop validation.
