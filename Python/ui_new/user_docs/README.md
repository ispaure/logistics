# Files and documents in Logistics

Logistics starts with a launch chooser. Select **Open full hub with sidebar** for
all destinations, or **File Browser**, **Git**, or **IDE** to use one tool without
the sidebar. Git and IDE are available when their features are enabled.

The chooser's **Read & edit** cards open Markdown, Text Editor, EPUB Reader,
Comic Reader and Archives, according to enabled features. Use **Open…** to pick a
file or **New** where offered to create a document. Cancelling the picker keeps
the chooser visible. Opened documents use the shared workspace without the sidebar.

In a single-tool view, a small, opaque settings icon floats above the content at
the bottom-left. Click it to show **Settings**, **Return to tool** (or **Return to
documents**), **Open documents**, **Choose launch mode**, and **Open full hub with
sidebar**. The chooser also offers this icon, so
you can enable an unavailable tool. Switching modes reuses your existing pages
and workspaces. Each new app launch shows the chooser again.

The window header also keeps a **Logistics** menu in every context. **Go to Tool**
lists current destinations; **New / Open Document** lists enabled document
launchers. Settings, tool settings, launch modes and installed guides are grouped
there. The active tool's menus appear alongside it, including File Browser's
File, Edit, View, Navigate, Index and Help commands. On macOS these use the native menu bar;
Windows and Linux show them in the window header without a second embedded bar.
File Browser's **File → Selected Items** exposes the same eligible commands and
feature contributions as right-clicking the current selection.

File Browser starts at your home folder. Use it for arbitrary paths;
**Folder Hub** brings configured local folders and remote integrations together.
The **Documents** menu lists open editors/readers. Switching destinations keeps
those documents alive. Feature-specific actions appear only for eligible selections.
The compact left sidebar keeps full-size destination icons with narrow side margins.
File Browser and Folder Hub use the full page width. Indexing and folder-source
loading appear in compact bottom notice rows, leaving more room for files and
folders. Hover over a shortened indexing notice to read its full text; use
**Index details…** when shown to inspect unfinished folders and scan errors.

## Browse, search and inspect storage

Open a folder, select a file to preview it, or double-click it to use the matching
reader/editor. Right-click for operations supplied by enabled features. ZIP/TAR
opens Archives, CBZ opens Comics, EPUB opens Books, Markdown opens its reader/editor,
and recognized ordinary text opens Text Editor when enabled.

Search uses saved directory metadata, so a new or partly indexed tree can have
incomplete results. Storage charts have the same limitation; logical file sizes
are not the same as allocated disk space. Use **Refresh index** when you need a
deeper scan and allow it to finish before interpreting totals. A large tree costs
more scan time and cache storage than the visited-folder default.

**Settings → File indexing** controls automatic refresh. Saved results can appear
before a refresh finishes. Disabling automatic scanning does not remove files;
use explicit refresh when you want current metadata. Shared controls and the
individual scan settings are documented in the
[commonUtils browser guide](https://github.com/ispaure/commonUtils/blob/main/ui/file_browser/user_docs/README.md)
and [index reference](https://github.com/ispaure/commonUtils/blob/main/filesystem/index/README.md).
Logistics adds feature actions and document routing to that browser.

The Logistics indexing settings apply on the next index request after **Save**:

| Setting | Workflow effect |
| --- | --- |
| Build an index when opening an unindexed folder | Starts automatic creation when no saved data exists; off still permits explicit refresh, revisit checks and notifications |
| Include subfolders in automatic scans | Adds deeper metadata and sizes; off leaves subtree search/totals partial. Explicit Refresh index always checks the subtree |
| Recheck saved indexes on first use | Reconciles saved data once per session; requires automatic indexing on open |
| Recheck the current folder when reopened | Checks an idle index on reopening, even with scan-on-open off; depth follows the subfolder choice |
| Update after filesystem notifications | Reconciles watched locations after changes; does not continuously scan the entire tree |
| Run index jobs at background priority | Gives other work priority without changing scan scope |


## Indexing across application instances

You can launch Logistics more than once. Instances share a queue for directory
indexing, so compatible requests follow the same work and only one index writer
runs at a time. Open browsers update their progress, search data and folder sizes
as saved results become available, including work started in another instance.

Closing a browser or turning off its **Background indexing** subscription detaches
that view; it does not cancel a submitted shared job. Other instances can finish
that work even without a browser open at the original folder. Closing or crashing
the indexing owner lets another instance resume saved folder checkpoints. If every
instance closes, unfinished requests resume at the next launch. The interrupted
folder may be scanned again; completed checkpoints are retained and validated.

Explicit refreshes and filesystem notifications received during a scan run in a
subsequent pass so those changes are not lost. Unreadable/unstable folders can still
leave partial results; use **Index details…** and explicit refresh to retry. This
recovery applies to indexing, not copying, moving, compression or transfers.

## Organize files

Use the selection's copy, cut, paste, rename or removal actions. Existing paste
destinations are preserved on collisions. Use [Bulk Rename](../bulk_rename/user_docs/README.md)
for a previewed filename transformation across many items.

Trash/Recycle Bin asks for confirmation; if the location cannot use Trash, files
stay in place. Permanent deletion is a separate consequential choice with no
Logistics Undo. Specialized image, comic, archive and cleanup actions have their
own preservation rules: read the owning guide before applying a batch.

## Work in several panes

On macOS, the menu bar follows the current destination and focused document pane,
including detached windows. Switching back to a destination without document
menus restores the host's menus automatically.
Docked Markdown and Text Editor tabs refresh the visible macOS menu bar when
selected; opening or clicking the menu bar is not required.

Browser tabs let several folders remain open. Drag a tab to an edge to split,
to another pane to combine, or outside the workspace to detach. Double-click a
floating tab header to bring it back. The same shared workspace supports documents.
**Documents → Bring back** returns a detached document. Closing a floating window
closes its panes and checks their save/work state.

Documents survive switching destinations and closing their originating browser.
That does not imply that every browser tab or reader window is restored after
restarting the app. Text Editor has its own documented checkpoint recovery;
Books saves reading positions separately. Save changes according to each editor.

## Read and edit Markdown

Open a Markdown file from File Browser for rendered reading, formatted editing or
exact source editing. Use **Source** for syntax the formatted editor cannot preserve;
formatted edits can normalize unsupported constructs. Saving is explicit, and
external disk changes block overwriting. Use **Save As** to keep a separate version.
In Formatted mode, click link labels to navigate. Syntax markers appear when the
caret touches an element or a selection overlaps it; hovering keeps them hidden.

Feature **User Guide** buttons open read-only help. When a feature's documentation
folder contains only `README.md` and `index.md` as Markdown files, the button opens
`README.md` directly. With additional Markdown pages, it opens `index.md`.
Alt/Option while opening help
opts into editing; it can change the documentation file on disk if saved. Local
links navigate within the guide viewer, while web links open a browser. For shared
formatting, properties, search and read-aloud controls, use the
[commonUtils Markdown guide](https://github.com/ispaure/commonUtils/blob/main/ui/markdown/user_docs/README.md).
For plain-source editing, choose [Text Editor](../../features/text_editor/user_docs/README.md).
[Obsidian](../../features/obsidian/user_docs/README.md) launches vaults in the external app.

## Find a configured integration

Choose a source and folder on **Folder Hub**. Local folders normally live under
`~/Server/Local`; remote sources come from loaded rclone configs, and Dropbox
contributes its detected account folders. Refresh after adding folders or configs.
A Calibre library, Minecraft server or other integration must meet its feature's
detection rules before its actions appear. Discovery itself does not start servers
or mount remotes.

If an action is absent, check feature enablement, source/credential selection and
the expected folder configuration. Enabling a feature also enables required
features; disabling a required feature is refused until its dependents are disabled.
Choices persist. Existing documents/jobs can finish after disabling their feature.

[All feature guides](../../../USER_GUIDE.md) · [Configuration](../../../CONFIGURATION.md)

### Tab headers and detached creation

The normal File Browser keeps its header even with one tab. Detached browser and
Document windows may hide a single header, retaining + at the upper right; + adds
to that same window. Multiple tabs restore their headers and share the available
width. The last normal browser tab still cannot close or detach.

## Central settings

Open **Logistics Settings** from the navigation rail or a tool's settings action.
The top-left selector applies to every category: **Default Software Configuration**
edits repository INIs shipped in future releases; **Personal Settings** edits
AppData overrides. Fields indicate inheritance. Click **↶** to remove an override,
then **Save Settings**. A software-mode reset reverts an unsaved field. Pending
changes remain when switching modes; closing asks Save/Discard/Cancel.

**Appearance & shared controls → Styling** controls the accent, dark tint and
interface, browser, reading and code font roles. EPUB and Markdown share reading
fonts; IDE, Text Editor, Git hunks and Markdown code share the code font. Tool
options are in **Feature settings**. Reading positions, account data and recovery
records remain personal data, outside software defaults. The path above each
editor shows exactly which INI will change.
