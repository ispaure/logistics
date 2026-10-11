# Using Logistics

Logistics opens in **File Browser** at your home folder. Use it to explore files,
read documents and run tools on selected folders. Use **Folder Hub** for configured
libraries, servers and remote storage. Hover a sidebar icon to see its name.

## Browse and search

Use **Open folder…**, the breadcrumbs and Back/Forward to navigate. Right-click
files or folders for the available tools. Features add their actions only where
they apply; a Calibre library or Minecraft server must first be detected.

The magnifying glass, or Ctrl/Cmd+F, opens search. It searches names in the current
folder and its descendants using the saved index. Close it with Escape or its X.
**Show in browser** leaves search and selects the result in its folder.

**Storage** offers Treemap and Radial charts, with a largest-first list beside
them. Double-click a folder to explore it and use Up to return. Totals can be
partial: by default only visited folders are indexed. **Refresh index** checks
beneath the current folder. Charts omit links and may omit small entries; use List
or Search when you need every item. Logical file sizes can differ from disk space.

## Tabs and windows

Use **+** or Ctrl/Cmd+T for another browser tab. Drag a tab onto a pane's edge to
split, into its center to combine tabs, or outside the workspace to detach it.
Double-click a detached tab header to bring it back. Closing a floating window
closes its tabs, checking edits and waiting for their background work to finish.

The **Documents** icon lists open text, Markdown, comic, EPUB and archive documents.
Its New/Open buttons start the appropriate editor or reader. Select a listed
entry to return to it; **Bring back** reattaches a detached document. Documents
remain open when you switch sidebar destinations or close their originating
browser pane. Bulk Rename has its own sidebar button.

## Copy, rename and remove

Select files, then use the right-click menu or standard Cut/Copy/Paste shortcuts.
Existing destinations are preserved when names collide. Use F2 to rename one item.
**Bulk Rename** previews a batch before applying it; its Undo checks that the files
and original destinations have not changed. Read the
[bulk rename guide](Python/ui_new/bulk_rename/README.md) for rules and recovery.

**Move to Trash / Recycle Bin…** asks for confirmation. If the location cannot use
Trash, the items stay in place. A separate permanent-deletion choice cannot be
undone through Logistics.

## Read and edit Markdown

Double-click a Markdown file to open it. Choose **Read**, **Formatted** or **Source**.
Formatted mode lets you edit headings, lists, tables and ordinary text while they
remain rendered. Use Source for exact syntax or documents with unsupported HTML
and extensions; formatted edits can normalize that syntax.

Use **Contents** to jump to a heading and Find/Replace to search. Formatting buttons
apply bold, italic, code and table changes. Undo reverses edits. YAML properties
appear above the body; add or edit them from the property panel or the toolbar's
corner menu. Callout documents use Source editing to preserve their syntax.

Saving is explicit: Ctrl/Cmd+S saves, and **Save As** makes a separate copy. If the
file changed on disk, Logistics refuses to overwrite it. Closing an edited
file asks for Save, Discard or Cancel. F11 enters fullscreen; Escape leaves it.
Website links open in your browser; local guide links use Back/Forward history.

## Choose and configure tools

**Settings → Features** enables or disables features and remembers your choice.
Enabling a feature also enables its required dependencies. Existing documents and
jobs can finish when their feature is disabled. Unavailable features show an
explanation. **Reset to defaults** enables all available features.

Choose a feature's settings category to edit its configuration. Save explicitly;
some changes require a restart. Its **User Guide** button opens a read-only guide.
Hold Alt/Option while opening a guide only when you intend to edit it.

Software and credentials are separate from the app. Default resource folders are
`Software/` and `RemoteCredentials/` beside the launchers. Managed local folders
normally live in `~/Server/Local/`. Some missing tools offer verified downloads;
other integrations require an installed application. See
[configuration](CONFIGURATION.md) for setup and path overrides.

## Feature guides

| Tool | What it does |
| --- | --- |
| [Git](Python/features/git/user_docs/index.md) | Open/clone repositories, review changes, commit, manage branches and remotes |
| [Text Editor](Python/features/text_editor/user_docs/index.md) | Edit text/code, search, change encoding and recover unsaved work |
| [Books](Python/features/books/user_docs/index.md) | Read EPUBs and edit book metadata |
| [Comics](Python/features/comics/user_docs/index.md) | Read, organize, compress, convert and edit comic metadata |
| [Archives](Python/features/archives/user_docs/index.md) | Browse, create, test and extract ZIP/TAR archives |
| [Images](Python/features/images/user_docs/index.md) | Compress images and edit JPG comments |
| [rclone](Python/features/rclone/user_docs/index.md) | Configure and transfer remote folders |
| [FUSE](Python/features/fuse/user_docs/index.md) | Open remote storage as a mounted folder |
| [Calibre](Python/features/calibre/user_docs/index.md) | Open libraries and review book exports |
| [Plex](Python/features/plex/user_docs/index.md) | Back up, compare and restore server data |
| [YouTube Downloader](Python/features/youtube_downloader/user_docs/index.md) | Download configured channels and playlists |
| [Minecraft](Python/features/minecraft/user_docs/index.md) | Find and launch configured servers |
| [Perforce](Python/features/perforce/user_docs/index.md) | Launch a local Linux server and console |
| [Obsidian](Python/features/obsidian/user_docs/index.md) | Find and open vaults |
| [Dropbox](Python/features/dropbox/user_docs/index.md) | Browse account folders and review identical conflict copies |
| [Links](Python/features/links/user_docs/index.md) | Open configured website shortcuts |
| [Smart Home](Python/features/smart_home/user_docs/index.md) | Discover and control Hue rooms |
| [Aviation Tools](Python/features/aviation_tools/user_docs/index.md) | Use the supplied calculators and aircraft/airport tables |
| [Flight Simulator](Python/features/flight_sim/user_docs/index.md) | Apply X-Plane display/settings presets |
| [Media](Python/features/media/user_docs/index.md) | Rename MKA chapters from a CSV |
| [File Tools](Python/features/file_tools/user_docs/index.md) | Inspect filenames and review bytecode cleanup |
| [System Tools](Python/features/system_tools/user_docs/index.md) | Launch platform-specific maintenance commands |

## If a tool does not work

Check its guide for required software, paths and credentials. Read the operation's
result before retrying: a cancelled batch may have completed some items. Keep
recovery copies until you have checked the result in the target application.

Only one Logistics process runs per user. If a launcher says Logistics is already
open, use the existing window. First launch requires internet to set up Python
and packages; later launches reuse that environment.
