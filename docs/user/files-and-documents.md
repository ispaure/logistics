# Files and documents in Logistics

Use **File Browser** to find files in a folder on your computer. Use
**Documents** to get back to the readers and editors you have open, even after
browsing somewhere else. If you are new to the app, [make and reopen a local
note](user.md#make-a-note-and-reopen-it) to see both views in action.

## Browse and organize a folder

Select a file to preview it, double-click to open it, or right-click to see
the available actions. For example, with the corresponding features enabled,
an EPUB opens in Books, a CBZ opens in Comics, and a ZIP or TAR opens in
Archives.

Select one or more files or folders and drag them onto a folder, another tab,
or a detached File Browser window. The highlighted folder or tab pulses twice
before opening. Move away to stop the timer or press **Escape** to cancel the
drag.

Use **Cut** and **Paste** from the context or Edit menu, or press **Ctrl/⌘+X**
and **Ctrl/⌘+V**. A move leaves both items in place when the destination already
has that name. A batch can finish some items before a conflict or cancellation.
Unlocked LocalCrypt folders accept moves. Moving out to ordinary storage asks
before creating decrypted files. Browsed rclone remotes are read-only.

Use the context menu to copy, rename or remove items. Use [Bulk
Rename](../features/bulk_rename/user/user.md) to preview a rename across many
files. Trash or Recycle Bin requires confirmation. If the location cannot
use Trash, the originals stay in place. Permanent deletion has no Undo.

An ordinary local SQLite database also has an **Inspect SQLite…** action.
The inspector opens read-only. Supported primary-key tables allow staged
edits through **Enable editing → Save changes**. A failed save keeps the
database and pending edits. Managed databases stay read-only. See the
[SQLite guide](../../Python/commonUtils/docs/user/sqlite_browser/sqlite_browser.md).

### Exchange files with your file manager

Drag existing local files and folders between File Browser and Finder,
Explorer, or Dolphin. You can drop them on a folder, a File Browser tab, or the
folder you are viewing. For drops into Logistics, hold **Option** to copy or
**Command** to move on macOS. On Windows and Linux, hold **Ctrl** to copy or
**Shift** to move. Without a modifier, ordinary drops on macOS and Windows
move items on the same volume and copy across volumes. On Linux the desktop
proposes the action. Drops into unlocked LocalCrypt default to copying.

Open **Workspace actions** to see transfer progress and errors or to cancel.
An incoming drop preserves any destination with the same name. A batch can
leave some items transferred after cancellation or a conflict. For a drop
into a file manager, check that file manager for progress, conflict prompts,
and the final result.

To export from a remote or LocalCrypt tab, select items and choose
**File → Prepare Selected Items to Drag…**. Choose a local folder and approve
creating readable copies there. Drag the prepared selection from its transfer
view. The files in your chosen folder remain there if you cancel that second
drag or lock the source. Remote tabs accept browsing and export, and remain
read-only.

## Clipboard in protected sessions

Enable **Logistics Settings → Privacy & Security → Restrict clipboard in
protected sessions** to block supported Cut, Copy and Paste commands in
editors, selectable readers and chat. The setting is off by default. When
enabled, protection applies across every window in the current Logistics
process as soon as session-only credentials are active. Locking or removing the
last credentials restores these commands when the last retained protected view
has released its content.

Existing clipboard contents stay available to other apps. Clipboard history
and device sync are controlled by the operating system. On Linux desktops
with a primary selection, selecting text can still publish it there. File Browser
copy and move commands remain available and can use the file-manager clipboard.

## Search and inspect storage

Search and size charts use saved folder metadata. If you can see a file in
its folder and cannot find it in search, choose **Refresh index** and let the
scan finish. That checks the whole subtree and takes priority over automatic
indexing once the current work can yield. **Queued for indexing** appears while
the refresh is waiting its turn. Open **Index details…** to
find scan errors, and use **Measure** in the size chart to switch between
allocated disk space and file contents. **Settings → File indexing** controls
automatic scan depth and refreshes.

## Indexing across application instances

Open Logistics instances share indexing jobs. When you close a browser, its
live updates stop. The job can continue in another instance or resume on
the next launch. If **Index details…** reports an unreadable folder, restore
access and refresh to try again.

## Work in several panes

From the landing page, the **Read & edit** cards have **Open…** and, for
formats you can create, **New**. Use **Logistics → New / Open Document…**, or
**+** in a document workspace, to open the same chooser without going home.
Cancelling the file picker returns to the chooser. Use **Logistics → Go to
Tool** to switch tools while leaving your documents open. **F11** toggles
fullscreen.

Drag a tab to a pane edge to split the view, onto another pane to combine
them, or out of the workspace to open a separate window. Double-click the
detached tab header or choose **Documents → Bring back** to return the tab.
Closing a window checks for unsaved edits.

### Tab headers and detached creation

Use **+** in a detached window to open another tab there. A window with only
one tab may hide its header. The last main File Browser tab stays in place.

## Read and edit Markdown

Open Markdown from File Browser to read it. Hold **Alt/Option** while
opening, or use the **Markdown Editor** launcher, when you want to edit. Use
**Source** when you need to preserve syntax that Formatted mode may
normalize. Save when you are ready to write the file. If the file changed
outside Logistics, use **Save As** to keep both versions. See [Text
Editor](../features/text_editor/user/user.md) for plain-text editing or
[Obsidian](../features/obsidian/user/user.md) for opening an external vault.

## Find a configured integration

Use **Workspaces** to browse folders you use with an integration. **Local**
offers **Dropbox**, **Rclone Copies** and **On This Computer**. A managed
rclone copy is a separate folder on your computer. Its contents can differ
from the online folder until you sync them. **Cloud → Rclone Remotes** lists
online folders from loaded credentials. **Server** lets you add an SMB
server and open its shared folders in **Files**. It also lists remotes from
packages named **Network shares** or **Session network shares**.

Use **Credential** to narrow the list of copies or remotes. If the one you
want is missing, use **+ rclone** to open credential settings or unlock the
matching package. **Refresh folders** reloads the source. **Settings →
Workspaces → Show Legacy (session only)** reveals hidden legacy names until
the next launch.

Select a workspace to fill **Files**, then open any subfolders you need.
**Info** shows the workspace locations and their availability. **Actions**
contains commands for the selected workspace. Push and Pull use the
workspace named in **Actions**, even if **Files** is showing a subfolder.
Right-click a local folder to reveal it in your system file manager.

### Browse an SMB server

1. Open **Workspaces → Server → Add server…**. Enter a connection name and
   the server hostname or IP address. Use your SMB account or choose **Connect
   as guest** if the server allows it. Change the domain or port if your server
   uses different settings.
2. Choose **Connect & browse** and open a share in **Files**. Open supported
   documents read-only. To keep a local copy, right-click a file or folder and
   choose **Download locally…**. You can also prepare readable copies for
   dragging to another window from the browser's **File** menu.
3. Choose **Server actions → Disconnect** to lock the connection in every
   browser window. Select the server and choose **Reconnect…** to sign in
   again. **Forget connection…** removes the connection and any saved
   credentials from this device.

Session-only connections remember their name and ask you to enter the server
address and sign-in again after disconnecting or quitting. To keep the
connection details and account credentials, select **Save credentials on this
device** and choose a credential passphrase. Logistics encrypts those details
and asks for the passphrase when reconnecting.

If the server is unreachable, check its address, port and network connection.
If it declines sign-in, check the account, domain and guest setting. If a
share is missing, return to the server root and refresh the listing.

**Locked** and **Unlocked** tell you whether the protected source is
accessible. A **Session-Only** view needs an unlock again after the session
ends. An ordinary offline copy stays readable after locking. An encrypted
**LocalCrypt** copy requires the matching credentials. Enter its password
in the Files pane to browse. See [where your changes go](working-safely.md)
before moving or syncing either kind of copy.

## Remote tabs

Use **File → Open Remote…** or open a loaded remote in Workspaces. Remote
tabs search the current folder and open supported previews read-only. To
download a file or work offline, see [browsing remote
files](../features/rclone/user/user.md#browse-remote-files-directly).

## Notes Library

Choose **Notes Library → Open Library** or use **Open as Notes Library** on
a marked workspace. See the [Notes Library
guide](../features/notes_library/user/user.md) for supported locations and
editing controls.

## Favourite files

Right-click a single file in File Browser or use **…** on its Recent row
on the landing page. Choose **Add to Favourites** or **Remove from Favourites**.
On an open document’s storage row, **… → Favourite file** adds that document.
Favouriting a note from Notes Library remembers both the library and the note.
Use **×** on the landing page to remove a favourite. Session-only favourites
appear after you unlock their credentials. See [reader history](reader-history.md)
for clearing Recent.

Choose **Drag File to App…** on an ordinary file, then drag it from the
handoff window to an app or file manager. In a remote or LocalCrypt browser,
choose **Prepare File to Drag…** to save a readable copy to a folder you choose.

## Central settings

Open **Logistics Settings** from the rail or floating Settings button. Use
**Features** if a tool is missing. See [Configuration](configuration.md)
for appearance, personal settings and updates.

## Documentation browsing

Feature **User Guide** buttons open read-only Help. Expand folders or search
by filename, title or page text. Relative Markdown links stay in Help.
Web links open your browser, and local code links open Text Editor. Hold
**Alt/Option** when you intend to edit a guide.
