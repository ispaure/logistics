# Using Logistics

Logistics gathers folder, library, remote-storage and maintenance tools in one
desktop application. Tools appear according to enabled features and the selected
folder's contents or configuration.

## Find a tool

The icon sidebar keeps **File Browser** and **Folder Hub** at the top. Hover an
icon for its name. Logistics opens
in File Browser; Folder Hub is the destination for configured libraries, servers
and remotes. **Tools** opens a dropdown of enabled tools and Debug; **Settings**
stays at the bottom. Switching destinations retains each view's state.

| Page | Use it for |
| --- | --- |
| File Browser | Browse your home folder or open another location; use file/folder right-click tools |
| Folder Hub | Choose a source/folder and use detected library, server or remote actions |
| [Git](Python/features/git/user_docs/index.md) | Clone/open repositories, inspect history, commit changes, and manage branches, remotes, submodules and subtrees |
| Settings | Enable features, manage credential packages and edit configuration |
| Tools → Debug | File/media/maintenance tools, Open File Browser and Bulk Rename |
| Settings → Features | Enable/disable integrations using feature toggle cards |
| Tools → Aviation Tools | Flight calculators and aircraft/airport reference tables |
| Tools → Links / Smart Home | Controls provided by those enabled features |

Disabling a feature removes its new actions; existing windows/jobs can finish.
Enabling also enables required dependencies. Choices are saved for the next launch.
A user guide remains accessible when its feature is disabled or lacks a dependency.

The document icon opens a popup listing Markdown documents, text buffers, comic
and EPUB readers, and metadata editors. Click an entry to select or focus it.
Drag their tabs outside the workspace to open floating windows, or onto the
center of another document to tabify and onto either edge to split. Floating
windows move with their full contents; drag them back over the main window to
reveal the document docking area, or double-click their tab header to return. The popup
also offers **Bring back** beside detached entries. When all documents are
detached, the empty document workspace closes; the icon stays available for return.
Detaching retains the document and
reading/editing state. Unsaved buffers and background workers are checked before
closing. File-browser pane tabs remain independent of these document tabs.
Closing an originating browser pane retains documents hosted by the main app.

## Remove files and folders

To remove files or folders, select them in the file browser and choose **Move to
Trash / Recycle Bin…** from the right-click menu. You’ll be asked to confirm.
If a network drive or another location cannot use Trash, the items stay in place.
You can keep them or review a separate permanent-deletion warning; permanent
deletion cannot be undone through Logistics.


## Read documentation

Select a feature under **Settings → Feature settings**, then choose **User Guide**
in its upper-right corner to read it. Hold **Alt**
(**Option** on macOS) while clicking to open it with editing enabled. The reader supports headings,
lists, tables and code examples. Click a Markdown link to navigate to another guide
or a heading, and use Back/Forward to retrace your steps. Website links open in
your default browser. Unsupported or missing documents show an explanation while
keeping the current page available.

Guides opened normally from feature settings are preview-only: they offer no editing or saving.
Links followed inside a preview-only window remain preview-only.

Double-click `.md` or `.markdown` files in the file browser to open a document that
permits editing and starts in Formatted edit mode. Reading does not modify a document. **Contents** opens a floating list of headings
on the right; select a heading to jump, or click outside to dismiss it. Editable
windows let you type directly in the formatted document. Headings, bold text, lists and
tables stay rendered while you type. Choose **Source** in the editing-mode selector
for precise Markdown syntax, or **Read** to return to reading. Formatted edits can
normalize Markdown and lose unsupported HTML/extensions; use Source when those
need to be preserved.

The Markdown reader follows the app's light/dark appearance, with clearer tables,
quotes and code blocks. Obsidian-style callouts (`> [!tip] Title`) appear as colored
panels; `+` and `-` after the type make their titles expandable. Callout documents
use Source mode for editing so their syntax stays intact. Mermaid code blocks can
be rendered using **Diagrams** when the optional Mermaid CLI is installed.
**F11** enters fullscreen; **Escape** leaves it after dismissing any open Contents
or Find panel.


In Formatted mode, typed `# ` through `###### ` becomes a heading, and completed
`**bold**`, `*italic*` or backtick code renders immediately. Selecting text and
pressing `*` wraps it as italic; pressing `*` again while it remains selected makes
it bold. `_` and backticks also wrap selections. Formatting markers appear when
the cursor is inside the text or you select it, so you can edit the markers directly.
They hide when you move away. Deleting a closing marker leaves plain incomplete
syntax (for example, `**bold*`); completing it restores formatting. Source mode
shows all delimiters. Undo reverses edits; saving is still explicit.

For multiline code, put three backticks on their own opening and closing lines.
An optional language name can follow the opening backticks. Code stays literal
and monospaced; fences appear while you edit the block. Unfinished blocks remain
editable without automatically adding a closing fence.

Use **Table** on the formatting toolbar or the right-click menu to insert a table,
add rows/columns around the current cell, or delete rows, columns or the whole
table. These controls work in Formatted editing; each change supports Undo.
The first row remains the header. Removing the final row/column removes the table.

Use **File → Save** (Ctrl+S, or Command+S on macOS) to save, **Open** (Ctrl+O) to
open another file, and **Save As** to write a separate copy. Formatting controls,
Undo/Redo and Find/Replace are available while editing. Leaving an edited document
prompts for Save/Discard/Cancel. Saving refuses to overwrite a document that has
changed on disk since it was loaded; Save As lets you keep your changes separately.
YAML properties between `---` delimiters at the start of a note appear above its
body. In formatted editing, use Add/Edit/Remove property or Edit YAML; text,
lists/tags, numbers, checkboxes and dates are supported. Body edits retain these
properties. Invalid YAML shows an error and remains available in Source mode.
Developer READMEs remain separate from these user guides.

## Resources and settings

Default private resources live in `Software/` and `RemoteCredentials/` at the
checkout root; Dropbox is optional. Credentials must be supplied separately.
Missing rclone software and macOS/Windows mount-driver installers can offer verified
downloads on first use. Other integrations keep their own installed-app or private
software requirements. See [configuration and resource setup](CONFIGURATION.md)
for path overrides and the configuration layers.

Managed folders use `~/Server/Local/` and mounts use `~/Server/NetworkMount/` by
default. The rclone config directory is `~/.config/rclone/`. Per-feature guides show
where their settings belong and what actions change files or external services.

## Feature guides

- [Create encrypted ZIPs](Python/features/archives/user_docs/index.md)
- [Read and manage comics](Python/features/comics/user_docs/index.md)
- [Connect and transfer remote folders](Python/features/rclone/user_docs/index.md)
- [Open a mounted remote folder](Python/features/fuse/user_docs/index.md)
- [Compress images and edit JPG comments](Python/features/images/user_docs/index.md)
- [Open and export Calibre libraries](Python/features/calibre/user_docs/index.md)
- [Back up and restore Plex server data](Python/features/plex/user_docs/index.md)
- [Rename MKA chapters from a CSV](Python/features/media/user_docs/index.md)
- [Download configured channels and playlists](Python/features/youtube_downloader/user_docs/index.md)
- [Manage Minecraft servers](Python/features/minecraft/user_docs/index.md)
- [Launch a local Perforce server](Python/features/perforce/user_docs/index.md)
- [Open Obsidian vaults](Python/features/obsidian/user_docs/index.md)
- [Browse Dropbox folders and clean conflicts](Python/features/dropbox/user_docs/index.md)
- [Open configured service shortcuts](Python/features/links/user_docs/index.md)
- [Control Philips Hue lights](Python/features/smart_home/user_docs/index.md)
- [Apply X-Plane 12 presets](Python/features/flight_sim/user_docs/index.md)
- [Inspect paths and remove Python bytecode](Python/features/file_tools/user_docs/index.md)
- [Run system maintenance actions](Python/features/system_tools/user_docs/index.md)

Holding **Alt** when opening any Markdown window enables editing, including documentation buttons. In formatted editing, Ctrl/Cmd-click follows standard Markdown links or local `[[Page|Label]]` / `[Page|Label]` aliases.

YAML properties appear above the body in a compact panel. In Formatted edit mode,
use **+ Add property**, double-click a row to edit it, select a row and choose
**Remove**, or right-click a row for its actions. With no properties, the panel
stays hidden; use the toolbar's corner **… → Add YAML property…** to create the
first one. **… → Edit YAML…** opens the raw header. Property edits retain the body
and unrelated metadata, and require the usual explicit Save.

## Bulk rename

On **Debug**, choose **Bulk Rename…** and select a folder. Select files or folders,
adjust the filename rules, and inspect **New name** before clicking **Rename
selected**. Scanning and previews do not change files. **Undo last rename** restores
the last batch's names if the files and original destinations are unchanged.
See the [bulk rename guide](Python/ui_new/bulk_rename/README.md)
for filters, numbering, presets, cancellation and recovery details.

## Settings

Select a category on the left to see its settings on the right. **Features**
controls saved feature defaults through a bounded list of toggle cards with dependency
details. Each feature has its own settings category and a User Guide button in
the upper-right corner. **rclone** separates **INI files** from **Credential packages**
in tabs; switching retains edits and package state. **Configuration** edits the launcher,
shared app settings and folder-protection INI files with section tabs and key rows.
Use **Source** for plain-text edits. Feature INI files
appear with their feature settings. Save explicitly; some changes require restart.
Unsaved edits are retained when switching categories and checked before closing.

**Reset to defaults** enables all available features. Choices are stored in
`preferences.ini` under `~/Library/Application Support/Logistics/` on macOS,
`%APPDATA%/Logistics/` on Windows, and `$XDG_CONFIG_HOME/logistics/` (normally
`~/.config/logistics/`) on Linux. Feature package folders are never renamed.
Unknown feature IDs are ignored until those packages are installed again. Missing
or unreadable preference files use defaults. A malformed file is preserved beside
the original as `preferences.ini.broken-<timestamp>` before defaults are loaded.
If that recovery copy cannot be created, the original remains intact.

**File indexing** edits `[FileIndex]` in Logistics' `Python/configFile.ini`, with
explicit Save and checkboxes for opening folders/new tabs, recursive scanning,
validating saved results after startup, revisits, file-change notifications, and
background thread priority. Changes apply on the next request. Other configuration
sections are retained.
Cached macOS `/` indexes also remove the duplicate `/System/Volumes/Data`
traversal before loading saved totals, even when startup validation is disabled.
Opening that Data folder explicitly remains supported.

## File Browser and Folder Hub

Logistics opens in **File Browser** at your home folder. Use the browser's
navigation controls and folder entries to move through the filesystem.
Switching pages retains browser navigation and selection. Enabled features
contribute previews and right-click actions here.
The Debug button can still open a separate File Browser window.

Use **New tab** (Ctrl/Cmd+T or **+**) to create another independent browser view.
New tabs in the main explorer start at Home and can navigate up to the filesystem
root; explicitly scoped windows retain their folder boundary. Folder names
identify tabs and change as you navigate. **Close tab** (Ctrl/Cmd+W or **×**)
removes the tab immediately while background work shuts down safely. Feature
prompts that refuse closure retain the tab.

Drag a tab down from its header, then onto the left or right quarter of another
pane to split the views side by side. The drop preview shows the destination.
Drop in the center to combine tabs. Double-click a single pane's header to detach
it, or drag outside the workspace. Drop a detached tab into another browser
workspace to move that same view while preserving its history and selection.
An empty workspace remains a drop target. Each pane has a visible border, with
shared indexing status outside the panes. The inline **Size** slider follows the
breadcrumbs on the same row, before **View**, and controls tile, list and column
icon sizes. Narrow paths prioritize the current folder. Split panes enforce a
minimum usable width so the controls do not overlap as the window shrinks.
Attached tabs show a full-pane image while dragging; detached windows move normally.

Select the **magnifying glass** to show the search bar below the breadcrumbs,
inside the file-list panel. Type to search names in the current folder and its
subfolders; results appear in that same panel. Close search with its **X**, **Escape**,
or another click on the magnifying glass. **Ctrl/Cmd+F** opens and focuses search.
Opening a matching folder keeps the query and scopes the results to its
subfolders. **Show in browser** explicitly leaves search and locates an item.
The **Storage** toolbar offers Treemap and Radial views, with a largest-first
list beside the chart. Double-click a folder to drill down and use **Up** to return.
Treemap shows at most 3,000 children; Radial shares a 3,000-entry budget across four
levels, prioritizing larger entries and retaining room for later rings. Gaps may
represent omitted or incomplete data. Use List or Search for all entries.
Links and directory junctions are excluded from recursive analysis. Unreadable
entries are reported, so totals may be partial. Logical sizes differ from physical
space used by sparse files, compression, and shared hard links.

Search and storage share the saved directory index. By default, opening a new
location indexes its immediate contents without walking its descendants. Saved
results open immediately; notifications update changed folders. Subtree sizes
and search coverage remain partial until deeper folders are visited or scanned.
Search reads cached names and updates as indexing progresses. Use **Refresh index** to check
for changes beneath the current folder; incomplete results are identified in the
search summary.

**Folder Hub** keeps the managed local folders, Dropbox sources and configured
rclone remotes together with their library/server/transfer actions. Use it for
configured destinations and use File Browser for exploring arbitrary files.
For a local folder, **Browse in Logistics** switches directly to File Browser.
If the active browser is restricted to another folder, Logistics opens a new
browser tab and keeps that existing view intact.

## Opening Logistics again

Only one Logistics process can run per user. Opening the launcher again shows
“Logistics is already open” and exits successfully. Use the existing app window;
its browser tabs and detached browser windows remain available.

Radial storage charts use a short zoom when opening a folder or going up. You can
disable it in **Settings → commonUtils**, under **Storage → radial animations**.
The file browser no longer shows a pause-scan button.

## Text Editor

Choose **Settings → Text Editor → Open Text Editor** for the document workspace, or
right-click text in File Browser and select **Open in Text Editor**. Open multiple
files in draggable tabs, search/replace with regex and undo support, and edit
scripts/configuration with syntax, line numbers and indentation controls. Save
keeps the original file location and encoding; explicit status controls convert
encoding or line endings. Disk changes and unsaved tabs are checked before data
can be discarded. Markdown retains its existing reader as well as this source
editing option. See the [Text Editor guide](Python/features/text_editor/user_docs/index.md).
