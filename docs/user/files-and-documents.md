# Files and documents in Logistics

Logistics starts with a launch chooser. **Open full hub with sidebar** opens all
available destinations. Below it, File Browser is always available; Folder Hub,
Bulk Rename and enabled features with their own navigation buttons open workspaces
with the sidebar by default. **Appearance & shared controls → Menus → Launch with
sidebar** can switch launch-page choices to focused workspaces without it. Disabled features are absent. Use Settings to
enable them, and their cards appear without restarting the app.

On Windows, the launch terminal minimizes once the chooser is displayed. You can
restore it from the taskbar to inspect startup output.

The **Read & edit** section always includes Markdown Editor. Enabled features add
their registered document tools, such as Text Editor, EPUB Reader, Comic Reader and
Archives. **Open…** picks a file; **New** appears where creation is supported.
Cancelling keeps the chooser visible. Opened documents use the shared workspace.

Cards adapt to the available width: up to three per row in landscape windows,
fewer columns in narrower windows. Wider views give cards more room. Cards
settle into their layout before the chooser first appears. Long lists
scroll vertically with the scrollbar or mouse wheel. The New / Open Document
chooser is a utility tab and is omitted from the document list and document counts.

In a single-tool view, a small, opaque settings icon floats above the content at
the bottom-left. Click it to show **Settings**, **Return to tool** (or **Return to
documents**), **Open Documents**, **Landing Page**, and **Open full hub with
sidebar**. The sidebar's Settings icon opens the same menu. Actions for the current
page or launch mode are hidden. **Landing Page** returns to the initial chooser.
Settings reset messages stay above the category panel without taking its available
height. Bottom status lines across tools use the same compact, greyed-out style
as File Browser. Long messages are shortened on screen; hover to read the complete
message. The chooser also offers this icon, so
you can enable a tool that is absent from the chooser. Switching modes reuses your existing pages
and workspaces. Each new app launch shows the chooser again.

The window header also keeps a **Logistics** menu in every context. **Go to Tool**
lists current destinations; **New / Open Document…** opens a chooser tab with
cards for the enabled document types. Empty document workspaces also show these
cards. Click **+** or use the new-tab shortcut to show the chooser in that same
workspace, including detached windows. **New** appears only for formats that
support creation; **Open…** opens a file picker. Cancelling keeps the chooser open;
a successful open replaces the chooser tab with your document. Settings, tool settings, launch modes and installed guides are grouped
there. The active tool's menus appear alongside it, including File Browser's
File, Edit, View, Navigate, Index and Help commands. On macOS these use the native menu bar;
Windows and Linux show them in the window header without a second embedded bar.
**F11** toggles the main window's fullscreen mode from any tool, including after
switching away from a book or comic. **Logistics → Full screen / Exit full screen**
provides the same command. A previously maximized window returns to maximized.
On keyboards that assign a system function to F11, use Fn+F11 or the menu.
File Browser's **File → Selected Items** exposes the same eligible commands and
feature contributions as right-clicking the current selection.

File Browser starts at your home folder. Use it for arbitrary paths;
**Folder Hub** brings configured local folders and remote integrations together.
The **Documents** menu lists open editors/readers. Switching destinations keeps
those documents alive. Feature-specific actions appear only for eligible selections.
The compact left sidebar keeps full-size destination icons with narrow side margins
and 40-pixel vertical steps, fitting more destinations in the available height.
File Browser and Folder Hub use the full page width. Indexing and folder-source
loading appear in compact bottom notice rows, leaving more room for files and
folders. Hover over a shortened indexing notice to read its full text; use
**Index details…** when shown to inspect unfinished folders and scan errors.

The desktop File Browser's size maps default to **Size on disk (allocated space)**.
Use **Measure** above the chart to switch to **Size (file contents)**. The chart and
ranked list share that choice, using both measures from the saved index.

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


## Remote tabs

Choose **File → Open Remote…** to browse a loaded rclone account, or choose
**Browse** on a Folder Hub remote. These tabs have their own read-only actions,
current-folder search and memory-only previews. Supported files open directly;
other files show a dialog asking you to manually make a local copy. There are no standalone file or folder download actions. Use managed Pull
workflows for offline Local or LocalCrypt folders.
See the [rclone guide](../../Python/features/rclone/docs/user/user.md#browse-remote-files-directly)
for limits, destinations and credential handling.

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
destinations are preserved on collisions. Use [Bulk Rename](../../Python/ui_new/bulk_rename/docs/user/user.md)
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
For plain-source editing, choose [Text Editor](../../Python/features/text_editor/docs/user/user.md).
[Obsidian](../../Python/features/obsidian/docs/user/user.md) launches vaults in the external app.

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

[All feature guides](user.md) · [Configuration](configuration.md)

### Tab headers and detached creation

The normal File Browser keeps its header even with one tab. Detached browser and
Document windows may hide a single header, retaining + at the upper right; + adds
to that same window. Multiple tabs restore their headers and share the available
width. The last normal browser tab still cannot close or detach.

## Central settings

Open **Logistics Settings** from the navigation rail or a tool's settings action.
Mouse-wheel gestures scroll the page without changing numeric fields, dropdowns,
date/time fields, sliders or dials under the pointer, even when focused. Edit with
typing, keyboard arrows or clicks; open dropdown lists still scroll their choices.
Settings opens in **Personal Settings**. Its feature-settings list includes only
enabled features; the **Features** page lists installed features so you can enable
or disable them. Hidden feature editors retain pending edits until you close or reset them. **Default Software Configuration** is
available only when the current user's home folder is named `marca`.
For **Features**, choose **Default Software Configuration** to change which tools
are enabled by default in shipped releases, or **Personal Settings** to change your
own selection. The file path above the feature controls identifies the file being
edited and updates when you switch scope. Feature toggles save immediately;
default changes affect future launches, while personal changes apply immediately.
Each feature card includes a short description. The **Personal overrides** heading
and **Inherited / Override** indicators show the source of each feature choice.
Toggling a feature saves only its explicit personal choice, including when you
toggle it back to the current software default. Untouched features remain inherited
and follow future default changes. **↶** removes that feature's personal choice;
**Use software defaults** removes all feature overrides. Enabling a feature also
saves enabled choices for dependencies that had to be turned on. Toggles keep the current
scroll position and keyboard focus.

In **Personal Settings**, the upper-right **Reset All Personal Settings…** button
is available from every category. Its confirmation applies to **all categories**,
including feature choices, appearance, editor options, indexing and other personal
configuration overrides. It also discards unsaved personal configuration edits;
unsaved software-default edits are retained. Settings panels reload and feature
navigation/appearance update immediately. Open editor, reader and Git views reload
preferences automatically; launcher settings apply on the next launch.

This resets only personal configuration. Separate migration metadata prevents old
preferences from being imported again. Documents, accounts, IDE workspaces, reading
progress, installed software and Blender presets are kept. A failed reset restores
the previous configuration where possible; if recovery fails, the error identifies
the retained recovery folder. A refresh failure after a successful reset asks you
to restart Logistics to finish applying the defaults.

The settings category list stays just wide enough for its labels, with a small
padding allowance. It adapts to the interface font; wider windows give the extra
space to the selected settings panel.

The top-left selector applies to every category: **Default Software Configuration**
edits repository INIs shipped in future releases; **Personal Settings** edits
AppData overrides. Fields indicate inheritance. Click **↶** to remove an override,
then **Save Settings**. A software-mode reset reverts an unsaved field. Pending
changes remain when switching modes; closing asks Save/Discard/Cancel.

**Appearance & shared controls → Styling** controls the accent, dark tint and
interface, browser, reading and code font roles. Each font name in the dropdown
is shown in its own typeface for a preview while browsing, including the selected
field. Samples underneath preview pending font and size changes before saving.
All four font sizes allow 7–24 pt. The code font list is limited to monospace fonts with equal character widths.
Font sizes use a common 96-DPI reference, so the same setting gives comparable
text and control proportions on macOS, Windows and Linux. macOS text is larger
than in earlier builds at the same setting. Retina and display scaling still
follow the operating system. Preview sizes and editor zoom use that same scale;
your saved size values are preserved.
Defaults are 10 for interface/browser/reading and 8 for code, keeping the previous
macOS text proportions on every platform. Personal font-size overrides still apply.
On Windows, moving a normal window between displays with different scaling
preserves its logical width and height if the native transition changes them.
Intentional resize gestures and maximized/fullscreen windows retain normal sizing.
On Windows, font lists exclude legacy bitmap/vector families such as Terminal
and Fixedsys. Unsupported typed choices show an error on Save and use a safe
preview; existing unsupported saved choices fall back automatically.
The interface font covers settings navigation and application menus. The file
browser font covers text within browser panels: file lists and headers, tiles,
folder columns, storage labels, paths, search controls and file details.
EPUB and Markdown share reading fonts; IDE, Text Editor, Git hunks and Markdown
code share the code font. Tool
options are in **Feature settings**. Reading positions, account data and recovery
records remain personal data, outside software defaults. The path above each
editor shows exactly which INI will change.

Launch and Documents pages keep their central content compact on wide windows,
with a maximum width of 880 pixels. Cards retain their compact 88-pixel minimum height, grow to fit wrapped text, and share the tallest height within each tool or document group. They recalculate after font and width changes.

The upper right of the launch page shows a subdued grey release tag, short commit
and commit time in your local timezone. Hover over it for the full commit and
original timestamp. Releases include this
information automatically, including ZIP installations without Git. A checkout
shows its exact tag or branch and marks tracked local changes as **modified**.

New/Open document choices use the same 88-pixel base card height and horizontal
presentation as launch choices, with compact New/Open actions on the right.

Opening an app or document from the launch screen keeps the sidebar by default.
Under **Settings → Appearance & shared controls → Menus**, **Launch with sidebar**
controls this behavior beside **macOS native**. Turn it off to open focused app
workspaces without the sidebar; the floating settings button remains available.
The setting applies on the next launch-page selection. Opening the full hub always
shows the sidebar.

The house icon at the top of the left toolbar returns to the landing page.
Open tools and documents remain available when you choose a workspace again.

The Bulk Rename (A→B) rail button uses the accent color while Bulk Rename is the
active destination, matching the other destination buttons.

Logistics checks for updates by default. In **Settings → Configuration**, choose
**configFile.ini**; **Updates** sits alongside the other configuration section tabs.
The Updates controls
let you disable checks or select **main**, **beta** or **alpha** (main by default).
These are published release channels: main uses stable releases, beta and alpha
use tags with those suffixes. Unpublished branch commits are not offered.

When a newer eligible release exists, **Update Logistics** appears at the upper
right of the landing (welcome) page below the version, using your accent color. The offer is shown
only on that page. Clicking it prepares the update, follows the normal close/save
flow, installs after Logistics exits, and restarts through the platform launcher.
Offline checks stay quiet. A failed preparation leaves Logistics open. Software,
Credentials, .env files, ignored files and personal AppData remain protected.
Local changes or file collisions stop an update rather than overwrite your work.

Extracted releases need the installed-file manifest included in newly packaged
releases. Older ZIP installations need a fresh release extraction first. Git
checkouts must have clean tracked files and initialized submodules at their pins;
a successful update checks out the release commit and dependencies detached.
Blue Hole separately checks its selected GitHub branch on each Blender launch.


Opening or expanding a LocalCrypt copy in File Browser automatically opens its
private tab with resolved names. The ordinary tab stays available at its previous
location. Folder Hub lists each encrypted copy once; separate Local and LocalCrypt
copies have distinct labels, with full source details available on hover.

Private File Browser tabs and their detached windows begin with **🕵️ Private -**. Their navigation, list, tile and column views share the regular browser’s presentation. Selecting a file shows File Information and supported comic/book metadata in the right Preview panel, or in the final column. Private views omit storage maps; thumbnails stay in memory. Editor Open/Save As omits Preview and retains its Local/LocalCrypt storage picker at the top.

Folder Hub shows backend-aware tools for private LocalCrypt copies, including rclone Pull and Push. Ordinary local-folder detection does not run against their ciphertext paths.

EPUB Reader and Comic Reader **Open** buttons in New Document, and their reader File menus, use the shared Local/LocalCrypt picker with format-specific filters. Cancelling leaves the current document or chooser in place. Private selections open separate readers with **🕵️ Private -** titles.

## Documentation browsing

Settings guide buttons open an inline documentation sidebar beside the Markdown
reader. Expand folders, select a page, or search by file names/titles or page text.
Folders with a same-named Markdown file open that page when selected. A heading
at the start of the body, after optional YAML properties and blank lines, supplies
its navigation label. Editing-enabled Markdown windows
also support this directory view; changing pages uses the existing unsaved-change
prompt.

Documentation links resolve relative paths such as `../folder/page.md` and
extensionless Markdown pages. Links to local text/code files (including `.py`
and `.txt`) open Text Editor separately, keeping documentation history intact.

In desktop reading mode, hover a local Markdown/text/code link to see a short
source snippet in a preview window. Moving off the link closes it immediately.
This does not open the file or change your reading history. Editing mode does
not show hover previews. Missing, binary and external web links have no preview.
