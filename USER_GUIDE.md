# Using Logistics

Logistics gathers folder, library, remote-storage and maintenance tools in one
desktop application. Tools appear according to enabled features and the selected
folder's contents or configuration.

## Find a tool

| Page | Use it for |
| --- | --- |
| Folders | Choose a source/folder and use detected library, server or remote actions |
| rclone | Load credential packages and manage remote configs |
| Debug | Standalone file/media/maintenance tools and Open File Browser |
| Features | Enable/disable integrations and open each feature's User guide |
| Links / Smart Home | Controls provided by those enabled features |

Disabling a feature removes its new actions; existing windows/jobs can finish.
Enabling also enables required dependencies. Changes last for the current session.
A user guide remains accessible when its feature is disabled or lacks a dependency.

## Read documentation

Choose **User guide** beside a feature on Features to read it. Hold **Alt**
(**Option** on macOS) while clicking to open it with editing enabled. The reader supports headings,
lists, tables and code examples. Click a Markdown link to navigate to another guide
or a heading, and use Back/Forward to retrace your steps. Website links open in
your default browser. Unsupported or missing documents show an explanation while
keeping the current page available.

Guides opened normally from Features are preview-only: they offer no editing or saving.
Links followed inside a preview-only window remain preview-only.

Double-click `.md` or `.markdown` files in the file browser to open a window that
permits editing and starts in Formatted edit mode. Reading does not modify a document. **Contents** opens a floating list of headings
on the right; select a heading to jump, or click outside to dismiss it. Editable
windows let you type directly in the formatted document. Headings, bold text, lists and
tables stay rendered while you type. Choose **Source** in the editing-mode selector
for precise Markdown syntax, or **Read** to return to reading. Formatted edits can
normalize Markdown and lose unsupported HTML/extensions; use Source when those
need to be preserved.

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
