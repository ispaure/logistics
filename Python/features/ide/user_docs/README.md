# Using IDE

Enable **IDE** in Settings → Features, then select its code icon in the navigation
rail. IDE does not require Text Editor, Git or any reader feature to be enabled.

## Projects

**Register project** selects an existing directory and lets you name it. Settings
accept one source directory per line (relative to the root or absolute), excluded
names/relative paths, and an optional Python executable or environment path (relative to the project root or absolute).
Use `.` for a flat Python project and `src` for a src-layout package.

Each top-level tab is an independent project. **Reopen** lists registrations.
Closing a project keeps its registration and layout. **Remove registration** asks
for confirmation and removes only IDE metadata; it never deletes source files.
Missing roots and missing open files remain recorded. Fix the root in project
settings or reopen once its storage is available.

Configuration is versioned JSON at `IDE/workspace.json` beside Logistics
preferences: `~/Library/Application Support/Logistics` on macOS,
`%APPDATA%/Logistics` on Windows, and `$XDG_CONFIG_HOME/logistics` (normally
`~/.config/logistics`) on Linux. No project-local configuration is created.
Layout saves are debounced and flushed on close. Concurrent instance changes are
rejected with a status message; restart to load the other instance's state.
Malformed configuration is retained and will not be overwritten automatically.

## Files and groups

The left tree loads directories lazily, hides configured exclusions, and filters
filenames without recursively crawling the project. **Go to file** searches
relative paths in a background scan. **Locate file** selects the active document.
The tree menu creates files/folders, renames closed items, reveals their containing
folder in the system file manager, refreshes, and deletes files or empty folders
with confirmation. Close affected documents before renaming or deleting a subtree.
Recursive folder deletion is intentionally unavailable.

Editor tabs belong to their project. Drag tabs to reorder them. **Split right**
adds a group, up to three; **Move left/right** moves the current file. Closing a
group moves its files into a remaining group. **Close all in group** closes files
individually with save prompts. Internal tabs and groups cannot detach.
Opening an already-open path activates its existing buffer, including across
groups. This version uses one view per file, rather than duplicate split views.

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
search panel. Toolbars expose overflowing actions through Qt's overflow control.

## Python navigation and search

- **F12** or Ctrl-click (Command-click on macOS): definition of a Python symbol.
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
Missing Jedi disables analysis while editing remains available. Requests for
changed/closed source buffers are ignored. Dynamic references, unresolved imports
and builtins without navigable source can return no target. Other open files'
unsaved edits are not overlaid into Jedi's import analysis; save them first.

Quick-open caps traversal at 100,000 file entries and shows at most 500 matches.
Project text search examines up to 10,000 files, skips binary/over-1-MiB files,
and returns up to 500 matching lines. Scans skip excluded folders and directory
symlinks. Analysis accepts up to 1 MiB of source. These tools are bounded searches,
not a complete background project index. Wait for active work before closing a
project; closing the application retains workers until they stop.

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
