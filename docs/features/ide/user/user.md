# Using IDE

Enable **IDE** in **Settings → Features** and select its code icon on desktop.
See [mobile support](../user_mobile/user_mobile.md) for Android and iOS.

## Projects

Choose **+ → Register / Open existing project**, select a folder and name it.
Enter one source path per line, such as `.` for a flat Python project or `src`
for a src-layout package. Set exclusions and an optional Python executable or
environment under **Project → Project Settings / Source Paths**. Paths can be
absolute or relative to the project.

Use **+ → Reopen project** to restore a project’s layout and cursor positions.
Drag project tabs out to detach them. **Remove registration** deletes only IDE
metadata. Reopen missing roots or documents when their storage returns.
Changing the root leaves existing absolute document paths in place.
**Column guide** defaults to 120 and accepts 0 to hide it.

Workspace state lives in `IDE/workspace.json` beside Logistics preferences in
`~/Library/Application Support/Logistics` on macOS, `%APPDATA%/Logistics` on
Windows or `$XDG_CONFIG_HOME/logistics` on Linux (normally `~/.config/logistics`).
If another instance changes it, restart to load its state. Malformed state is
preserved for recovery.

## Files and groups

Open files in the tree or use **Go to file** to search relative paths and
**Locate file** to find the active document. Use the tree menu to create,
rename, reveal or delete files and empty folders. Rename with **F2**
(**Return** on macOS) and commit with Enter. Renaming open files retains edits
and updates save targets. Wait for pending opens and saves, and close affected
files in other projects before renaming. Close affected documents before deleting.

Choose **View → Split Editor Right** for a second view of the current file.
Drag tabs between headers to move or reorder them, or onto a side to split.
Up to three groups share file text, undo and modified state, with independent
cursors and scroll positions. Close the last view to get the unsaved-file prompt.
**Save As** changes the file in every view; **Reload** resets their shared undo.

Markdown tabs offer **Formatted**, **Source** and **Read**. Use Source to
preserve exact syntax. Local links open another tab. **Save As** requires
`.md` or `.markdown`.

**Save** preserves encoding, BOM and line endings. A failed decode offers an
encoding choice. Binary files and files over 16 MiB are refused. If a file
changes on disk, choose **Reload** to read it or **Save As** to keep both versions. Failed saves
retain the buffer. Closing offers Save/Discard/Cancel.

[Git](../../git/user/user.md) opens working files in the most specific enabled,
registered IDE project, reopening it if necessary. Unregistered files use Text Editor.

## Python navigation and search

| Action | Shortcut |
| --- | --- |
| Go to definition | **F12** or **Ctrl/Cmd-click** a reference |
| Find usages | **Shift+F12** or **Ctrl/Cmd+Shift-click** |
| Back / forward | **Alt+Left / Alt+Right** |
| Go to file / line | **Ctrl/Cmd+P / Ctrl/Cmd+L** |
| Current-file symbols | **Ctrl/Cmd+Shift+O** |
| Completion / inferred docs | **Ctrl/Cmd+Space / Shift+F1** |
| Find in Files | **Ctrl/Cmd+Shift+F** |

Jedi uses your source paths and optional interpreter. Save related files before
navigating imports or usages. Dynamic code and unresolved imports can return
incomplete results. Usages are limited to 200 within the project.

In **Find in Files**, choose a project, source or folder scope, then use **Cc**,
**W**, **.*** or a **File mask** such as `*.py; *.txt`. Open buffers supply
unsaved text. Search skips binary files, files over 1 MiB, excluded folders and
directory symlinks. It examines at most 10,000 files or 100,000 entries and
returns up to 500 matches. Open a result with Enter.

## Languages and initial limits

Pygments provides shared highlighting for Python, web and shell languages and
common config formats. Unknown text remains editable. Shared code styling lives
under **Settings → Appearance & shared controls → Styling**. Git operations
and conflict review live in Git.

## Change markers and automatic saving

The gutter compares live text against the Git index, or the last saved file when
Git is unavailable. Click a marker to review or **Revert change in buffer**.
For Git, save first, then **Preview Git hunk to stage** and
**Stage displayed Git hunk**. Reopen the review if the buffer or index changed.
The displayed Git hunk can include adjacent markers. Use Git’s File status for
renames, conflicts, conversions and permission changes. Hover over a colored
tree filename for its status.

Choose **File → Auto Save → After 1 second** (default), **On focus change** or
**Off** per project. External edits, deletions and write errors pause autosave
and retain your work. Resolve with **Save**, **Reload** or **Save As**. If a save
is active, let it finish before closing or retrying. Unsaved changes are held
in memory.
