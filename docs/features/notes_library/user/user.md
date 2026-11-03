# Using Notes Library

[Notes Library guides](../notes_library.md)

Select **Notes Library** immediately below Documents in the desktop sidebar.
Choose **Open Library** and navigate to an existing local folder or unlock a
LocalCrypt copy. Explicit opens accept folders without an Obsidian marker.
Cloud-only folders must be downloaded or synced first.

Each library has its own outer workspace tab. Its notes use the existing inner
document tabs and split groups. Switch libraries or destinations without losing
drafts. Opening the same root again focuses it; folders with the same display
name remain separate. Library windows can detach and return to this destination.
Favourites reopen the same library and select the saved note.

Close a note or library with its close control. Save, discard or cancel when
prompted. Turning off Notes Library in Features keeps open libraries reachable
for saving/closing and stops new opens. Text Editor has its own independent toggle.
Enable Notebooks to open/create `.rmdoc` drawings; Markdown and source editing
remain available without it. LocalCrypt still requires its usual storage access.

## Notes Library and Documentation Library

**Documentation Library** is the shared guide viewer used by Logistics and
other consumers such as the build/deployment manager. Sidebar titles come from
the opening Markdown heading (falling back to the filename). The sidebar does
not create, rename or move files, even when Alt/Option enables page editing.

**Notes Library** is Logistics' workspace for writing notes. Sidebar entries keep
their actual filenames. Use **Open as Notes Library** in the workspace action
panel for a local folder containing an `.obsidian` directory. Browsing folders
opens their files directly without a mode prompt.

For writable libraries, use **New Document**, **New folder** and **Rename / Move…**
in the sidebar. Click an already-selected file or folder name to rename it inline,
or press F2. Enter applies the name; Escape cancels. Drag an entry onto a folder
to move it; drop on empty sidebar space to move it to the library root.
Rename / Move accepts a path relative to
the library root, using existing folders. Moves preserve note history; unsaved
changes must be resolved first. Choosing Save continues the requested move after
saving succeeds; a failed save keeps the draft and its original path.
Existing destinations are never overwritten.
Links in other notes are not rewritten when files move.

Right-click a file or folder for **Move / rename…**, **Copy…** or **Delete…**,
as supported by the location. Copy refuses existing destinations. Delete asks
for confirmation and permanently removes the selected item and its contents.
Clicking a folder with a matching `Folder/Folder.md` opens that landing note;
use the expansion arrow to browse its children.

The sidebar has **Files** and **Calendar** tabs. File search offers
**Search within Notes Library** and **Search in File Names**, including unopened
folders. Name matches appear before content matches; quoted phrases and separate
keywords use the same search rules as mobile. **Show more notes** extends the
result list. Hidden configuration is excluded.

Calendar marks days with a `YYYY-MM-DD.md` note anywhere in the library. Select
a day to open it, choosing a path when several notes share that date. A missing
day asks before creating a note in the library root. **Refresh daily notes**
rescans names after outside changes. **Links** opens backlinks, outgoing links,
unresolved links and word/character counts for the saved Markdown note.

An unopened library offers Open Document and New Document cards. Choose Markdown
or Remarkable Document before naming a new file and selecting a library folder.
Both `.md` and `.rmdoc` documents open inside the same library window. Notebook
navigation and saving use the regular drawing canvas; unsaved changes must be
resolved before selecting another file. Wiki headings such as `# [[Tech]]` can
be edited in the formatted Markdown view.


From a Local or unlocked LocalCrypt location's actions page, choose **Open as Notes
Library** when the root contains an `.obsidian` directory. The reader opens in
the Notes Library destination with a folder/page sidebar, note history and read-aloud controls.
Library mode is local-only on every platform: download or sync a cloud folder
first. Individual remote Markdown files remain available in the read-only viewer.
Existing Markdown notes open in reading mode; choose **Edit Markdown** for
Formatted or Source editing in that same local copy. New Markdown documents
start editing. Per-note reading positions are retained while the library is open.
Unsaved changes are checked before switching notes or closing. Choosing Save
continues navigation after a successful save. Notes are
limited to 2 MiB. Hidden configuration is excluded and links stay inside the library.

Links such as `[[Tech]]` can open `Tech.md` in a subfolder. The current folder
and library root take priority; otherwise the app looks for a unique match across
subfolders when you follow the link. If several notes match, use an explicit path
such as `[[Topics/Tech]]`. Lookup stops after 10,000 entries.


## Embedded source files in Notes Library

The Files pane includes JSON and view-script files, including folders such as
`_Resources/dataview`. Select a file to open it inside the library's detail pane.
Markdown uses the existing Markdown viewer/editor, `.rmdoc` uses the notebook
canvas, and source files use the regular code-editor components. Explicit Markdown
links to supported source files also open inside the library.

Supported source extensions are `.json`, `.jsonc`, `.js`, `.mjs`, `.cjs`, `.css`,
`.txt`, `.csv`, `.yaml`, `.yml`, `.toml`, `.ini`, `.xml`, `.html`, `.py` and `.ts`.
Source files have syntax highlighting and Find/Replace. On desktop, use **Save**
or the standard Save shortcut; on mobile, use **••• → Save** and **Find / replace…**.
Markdown formatting/YAML controls apply only to Markdown documents. Opening a
JavaScript file shows its source; execution happens through a note's data-view block.

Changing files or closing the library asks about unsaved changes. Saves retain
encoding/BOM and line endings and refuse to overwrite an externally changed
file; the draft stays available after a failed save. LocalCrypt reads/writes use
the selected provider and keep plaintext in memory. Read-only locations remain
read-only. Source files are limited to 2 MiB; binary and hidden configuration
files are excluded. Content search includes supported source files. Calendar and
note metadata scans still read Markdown notes.

## JSON data views in Notes Library

Notes Library runs the supported `dataviewjs` subset automatically in reading
mode on desktop and mobile. There is no library trust prompt. The saved note and
its Source/Formatted editors retain the original code blocks; results are display
content only. Reopen the note to reload changed JSON or view scripts.

For a library containing `data/items.json`, use:

```dataviewjs
const rows = JSON.parse(await dv.io.load("data/items.json"));
dv.table(["Name", "Quantity"], rows.map(row => [row.name, row.quantity]));
```

Reusable JavaScript views receive `dv` (also named `dataview`) and `input`:

```dataviewjs
await dv.view("views/inventory", {path: "data/items.json"});
```

Place this view's code in `views/inventory.js` or `views/inventory/view.js`.
An explicit `.js` filename also works. Nested awaited views are supported. View
paths start at the library root. Within the script, `input.path` contains the
argument above; `dv.io.load(input.path)` returns the UTF-8 file as text, so JSON
needs `JSON.parse`. Missing text files return `undefined`; invalid JSON, missing
views and unsupported API calls produce a visible error in that block.
Extensionless `dv.io.load("data/items")` also tries `data/items.json`, after
checking the exact path. `dv.view` loads JavaScript, so its extensionless paths
try `.js` or `/view.js` rather than JSON.

Supported output helpers are `dv.table(headers, rows)`, `dv.list(values)`,
`dv.header(level, text)`, `dv.paragraph(text)` and `dv.span(text)`. Values display
as literal text, with objects serialized as JSON. Output does not interpret HTML
or Markdown supplied in values. Plain `dv.io.load` paths try the library root,
then the current note's folder. Explicit `./` and `../` paths resolve from that
folder. The optional second argument supplies an origin note path relative to
the library root. Paths may not escape the library or read hidden configuration.
JSON and JavaScript files can also be opened and edited through Files.

This subset does not implement Dataview queries, `dv.pages`, metadata indexing,
Obsidian's `app`/plugin APIs, DOM manipulation or `view.css`. Code blocks inside
lists, quotes, frontmatter or fenced examples do not execute. Each render runs in a disposable
worker with no host write API or network access. It permits up to 64 script
blocks, 128 file requests, 2 MiB per file and 8 MiB of total reads, with bounded
output and a 30-second worker deadline. Closing, locking or changing notes
retires the run. LocalCrypt content remains in memory.

## Notes Library document groups

Opening sidebar entries keeps each document in its own inner tab. Drag an inner
tab to another header to reorder it, or to the left/right side of a document to
create a neighbouring group (up to three). The tab's context menu offers the same
moves. Inner tabs stay within the library. Each document retains its draft while
you switch tabs; Save applies to the focused document. Closing a tab or library
resolves unsaved edits. File moves update affected tabs and preserve their groups.
