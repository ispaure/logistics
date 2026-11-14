# Files and documents in Logistics

Use **File Browser** for files anywhere on your computer and **Workspaces** for
configured folders, remote accounts and managed copies. On the landing page,
**Read & edit** offers **Open…** and, for supported formats, **New**.

Choose **Logistics → New / Open Document…** or use **+** in a document workspace
to open another file there. Cancelling keeps the chooser open. **Logistics →
Go to Tool** switches tools while keeping open documents available. Use the house
icon to return to the landing page and **F11** to toggle fullscreen.

## Browse, search and inspect storage

Select a file to preview it, double-click to open it, or right-click for actions.
ZIP/TAR opens Archives, CBZ opens Comics, EPUB opens Books, and Markdown opens
in reading mode. Available actions depend on enabled features.

Search and size charts use saved folder metadata. If results are incomplete,
run **Refresh index** and wait for it to finish. Explicit refresh checks the
whole subtree. Use **Index details…** for scan errors and **Measure** on the
size chart to switch between allocated disk space and file contents.
**Settings → File indexing** controls automatic scan depth and refreshes.

For an ordinary local SQLite database, choose **Inspect SQLite…**. It opens
read-only. Supported primary-key tables allow staged edits through
**Enable editing → Save changes**. A failed save keeps the database and pending
edits. Managed databases stay read-only. See the
[SQLite guide](../../Python/commonUtils/docs/user/sqlite_browser/sqlite_browser.md).

## Remote tabs

Use **File → Open Remote…** or open a loaded remote in **Workspaces**. Remote
tabs offer read-only previews and current-folder search. Right-click a file or
folder and choose **Download locally…** to save a readable copy, with confirmation
for encrypted remotes. Use a managed **Pull** for a linked Local or LocalCrypt
copy. See [remote browsing and download limits](../features/rclone/user/user.md#browse-remote-files-directly).

## Indexing across application instances

Open instances share indexing jobs. Closing a browser stops its live updates
while the job can continue in another instance or resume on the next launch.
Use **Index details…** and refresh to retry unreadable folders. Copying,
moving and transfers have separate recovery rules.

## Organize files

Right-click a selection for copy, cut, paste, rename or removal. A paste keeps an
existing item if the name collides. Use [Bulk Rename](../features/bulk_rename/user/user.md)
to preview a batch rename. Trash or Recycle Bin requires confirmation. If the
location cannot use Trash, the originals stay in place. Permanent deletion has
no Undo.

## Work in several panes

Drag a tab to a pane edge to split, onto another pane to combine, or outside
the workspace to detach. Double-click the detached tab header to bring it back,
or use **Documents → Bring back**. Closing a window checks for unsaved edits.

### Tab headers and detached creation

Use **+** in a detached window to open another tab there. A window with only one
tab may hide its header. The last main File Browser tab stays in place.

## Read and edit Markdown

Open Markdown to read it. Hold **Alt/Option** while opening, or use the
**Markdown Editor** launcher, to edit. Use **Source** for syntax that Formatted
mode may normalize. Save explicitly. If the file changed outside Logistics,
use **Save As** to preserve both versions. See [Text Editor](../features/text_editor/user/user.md)
for plain-text editing and [Obsidian](../features/obsidian/user/user.md) for external vaults.

## Find a configured integration

In **Workspaces**, select a source and folder. **Local** offers **Dropbox**,
**Rclone Copies** and **On This Computer**. **Cloud** offers **Rclone Remotes**
from loaded credentials. **Home Server** groups packages named **Network shares**
or **Session network shares** and can show **Pending Implementation**.

Use **Credential** to narrow copies or remotes. If a remote is missing, use
**+ rclone** to open credential settings or unlock its package. **Refresh
folders** reloads the source. **Settings → Workspaces → Show Legacy (session
only)** reveals hidden legacy names until the next launch.

Selecting a folder fills **Files**. **Info** shows its locations and availability.
**Actions** contains workspace commands. Push and Pull target the workspace
named there, even when Files shows a subfolder. Right-click a local folder to
reveal it in your system file manager.

**Locked** and **Unlocked** describe access. **Session-Only** describes the
private open view. An ordinary copy stays readable after locking. An encrypted
LocalCrypt copy still needs the matching credentials. Enter its password in
the Files pane to browse.

## Central settings

Open **Logistics Settings** from the rail or floating Settings button. Use
**Features** if a tool is missing. **Appearance & shared controls → Menus →
Launch with sidebar** controls the next landing-page selection. Use **Open full
hub with sidebar** to restore the rail from a focused workspace.

Under **Styling**, separate font roles cover the interface, browser, reading and
code. Preview changes and use **Save Settings**. **↶** removes an override.
**Reset All Personal Settings…** resets personal categories and discards pending
personal configuration edits. It keeps documents, accounts, reading progress
and Blender presets.

Use **Configuration → configFile.ini → Updates** to choose a published release
channel. **Update Logistics** appears on the landing page when a release is
offered. It follows the normal close/save flow and restarts after installation.
Local changes or collisions stop the update. Older extracted releases may need
a fresh extraction. Git checkouts need clean tracked files and initialized
submodules. See [Configuration](configuration.md).

## Documentation browsing

Feature **User Guide** buttons open read-only Help. Expand folders, select a
page, or search names, titles and text. Relative Markdown links stay in the
viewer. Web links open your browser. Local code links open Text Editor. Hold
**Alt/Option** only when you intend to edit the guide.

## Notes Library

Choose **Notes Library → Open Library** and select a local folder or unlocked
LocalCrypt copy. A marked workspace also offers **Open as Notes Library**.
Download or sync cloud-only libraries first. Use **Edit Markdown** to change a
note. Save or discard private drafts before locking credentials.
See the [Notes Library guide](../features/notes_library/user/user.md).

## Favourite files

On a document's storage row, choose **… → Favourite file**. Adding it from
Notes Library remembers the library and note. Use **×** on the landing page to
remove a favourite. Session-only favourites appear after unlocking their
credentials. **Settings → Reader history → Clear all recent files** clears the
recent list and keeps favourites and files.
