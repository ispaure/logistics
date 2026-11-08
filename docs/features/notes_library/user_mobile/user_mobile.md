# Notes Library on mobile

[Notes Library guides](../notes_library.md)

Open discovered libraries from Documents or use existing folder and favourite
entry points. Mobile navigation remains in Documents. **Settings → Features →
Notes Library** controls libraries independently of Text Editor. Existing users
inherit their former Text Editor selection once; later changes are independent.
Close an open library before turning its feature off. Markdown and embedded text
editing remain usable with Text Editor disabled. Notebooks controls drawing opens
and creation separately.

Use Files, Search, Calendar and Links to navigate, and the library's close
control to leave. Close returns to Documents or Workspaces, depending on where
you opened the library. The New Document, New Folder and Collapse All controls appear
in Files. Unsaved changes retain their save/discard/cancel choices. Folder-backed
Markdown uses the [shared mobile editing controls](../../text_editor/user_mobile/user_mobile.md).

Markdown callouts such as `[!NOTE]` display as titled panels with their
headings, paragraphs, and lists inside. Tap the title of a foldable callout to
expand or collapse it. Reading and folding leave the source unchanged.

Notes Library accepts Markdown files up to 16 MiB. Reading allows up to 96 MiB
of rendered HTML and 128 MiB for the final private page. Embedded images share a
48 MiB file-byte budget per render; each image remains limited to 8 MiB and 16
megapixels. Images request lazy loading as you scroll. Formatted editing retains
its 1 MiB source limit; larger notes open in Source mode for editing. Preview
errors appear in a popup and retain the current document.

The landing page offers **Open Document** and, for writable libraries,
**New Document**. On iOS, the title sits between the Files and Links pane buttons;
long names pan within that space, respecting the system's motion preferences.
Swipe right across the article or empty landing area to open Files, or left to
open Links. Swipe the open panel toward its edge to close it. Panels slide in
and out; Reduce Motion and Android E Ink mode suppress this motion.

Notes Library also runs [JSON data views and reusable `dv.view` scripts](../user/user.md#json-data-views-in-notes-library)
in reading mode, enabled by default. The same API subset and file/path limits
apply on desktop and mobile. Editing retains the authored code blocks.

JSON, JavaScript and [other supported source files](../user/user.md#embedded-source-files-in-notes-library)
appear in Files and open in the same library detail pane using the normal native
code input. Use **••• → Save** or **Find / replace…**. Switching files retains the
library history and asks before discarding unsaved edits.

Images and documents in Files open inside the library detail pane. PDFs have
Previous page and Next page controls. Videos such as MP4 open the full native
mobile Video Player with its resume, autoplay, tracks and playback tools. The
current library page stays available when you return. In a Markdown note's
reading view, use the embedded clip's Play button and timeline to watch it in
place. Tap **Play fullscreen video** to open it in the native Video Player.
The reading view resolves the video attachment when you choose playback.
Unsupported formats
show file information in that pane. Image previews allow up to 8 MiB and 16
megapixels; PDFs allow up to 32 MiB. Back and forward retrace files opened in the
library; switching files asks about unsaved changes.

Folders with a same-named `Folder/Folder.md` page have underlined names in Files;
tap the name to open that page, or use the arrow to expand the folder.
Renaming the folder also renames its matching landing note. Renaming the note
directly leaves its parent folder in place.
A horizontally scrollable breadcrumb shows the folders below the library root
for every open file type, including images and PDFs. Long paths initially show
their end. The trail uses Files icons with `>` between entries and ends in a
file icon. Swipe horizontally to reach earlier folders. Tap a folder to open
its same-named page. If that page is already open or the folder has no landing
page, the tap reveals the folder in Files. Hold the filename in the title to
see its full location.

On iPhone, iPad and Android, previous/next note, edit/view and Note actions stay
in the content row below the title, beside the breadcrumb. Close, Files and
Links share the filename row, including in Duo layouts. In wide layouts, note
controls follow the document pane when Files is visible alongside it.


## Notes Library and Documentation Library

Open **Documents → Libraries** to see Notes Libraries. To create one, choose
**New Notes Library…**, pick a storage location, browse to the parent folder,
and enter a name for your library folder. Use **New folder** if you need to add
a parent folder first. **Create library here** makes the named folder, writes
an empty `.noteslibrary` marker inside it, and opens the library. The storage
picker offers the same locations as New document, including on-device rclone
sync copies. Local copies are plaintext. Selecting a locked LocalCrypt copy
with a retained credential ZIP prompts for the ZIP password.

Discovery checks the storage root and up to two folders below it. A
`.noteslibrary` file or an existing `.obsidian` directory marks a library.
For a library deeper in storage, open its folder from the File Browser.
Encrypted library buttons show an open lock alongside the local disk icon.
Notes Library keeps actual filenames in its sidebar.

In writable libraries, **••• → New folder…** creates a folder beside the selected
note or inside the selected folder. **Rename selected…** changes the name in its current folder.
**Move selected…** opens a folder picker within this library; browse to the
destination and choose **Move here**. The filename stays the same. These actions also work on
selected folders. Moves preserve navigation history and do not overwrite existing
entries. Links in other notes are not rewritten.

An unopened library shows **Open Document** and **New Document** cards. New Document
first offers **Remarkable Document** and **Markdown**, followed by the name and a
folder picker confined to this library. It cannot publish outside the library.
Markdown and drawing documents open inside the same library pane. The file and
link drawers remain available while editing. Changing document or closing the
library asks to save or discard unsaved edits; cancelling keeps the draft open.
Malformed drawings and failed saves retain the current document.

Drawing documents keep the full canvas toolbar beside the filename, or below it
on narrow screens. **Note actions** includes **Pages Overview**, **Page template
and layers**, **View and input…**, and **Notebook actions…**. The canvas also has
its own notebook actions menu; iOS/iPadOS exposes the panel buttons in native
navigation, including the Duo side rail. **Save a copy…** exports a separate
editable notebook without changing the current file or discarding unsaved edits.
**Show in folder** reveals the containing library folder.

The first mobile header row contains Close, the left-pane button, the filename
(or library name while editing a drawing), and the right-pane button.
Note history, edit/view and the actions menu are on a
second row, hidden during folder browsing. Back and Forward sit on the left;
edit/view and the actions menu sit on the right. The folder breadcrumb fills the
space between them. Short paths are centered. Long paths start at the end.
Swipe either way on the strip to scroll between folders without opening a
side panel. Single-line wiki headings such as
`# [[Tech]]` and wiki aliases are editable in formatted mode and keep their syntax.
Other protected constructs remain available in Source editing.

**••• → Contents…** jumps to a heading. In reading mode it scrolls the rendered
note; while editing it selects the heading in Source, including unsaved headings.
**Find / replace…** while editing opens Source with the shared editor search
controls: previous/next, match case, replace and replace all. Reading mode keeps
**Find in this page…** for the rendered note.

While editing, **Properties…** lists YAML fields and supports adding, editing or
removing text, numbers, checkboxes, dates and lists. **Edit YAML…** handles the raw
frontmatter, including complex values. Apply updates the current draft and keeps
the body; use Save to publish it. Invalid values stay in the form with an error.
A form opened against an older draft cannot replace newer edits.

Search runs away from the UI thread. Updates are coalesced and matching rows are
paged, so changing the search mode cancels the previous result stream.

**Documentation Library** is the shared viewer for built-in guides. It uses each
page's opening Markdown heading as its sidebar title, with a filename fallback.
Its sidebar supports browsing and search; page editing does not enable sidebar
creation, renaming or moving. Notes editing and file organization belong to
Logistics' Notes Library.


Open a discovered library from **Documents → Libraries**. For a cloud folder,
download or sync a local copy before opening it in library mode. Individual cloud Markdown
files can still be opened in the standalone read-only viewer.

On narrow screens, **Files** opens over the full-width document. Use the
upper-left Files button or swipe right across the document to browse; swipe left
in the drawer or tap outside it to return to reading. Choose a note to close the
drawer. The upper-right Links button, or a left swipe across the document,
opens Links. Choose **Out** for outgoing links or **Back** for backlinks.
Swipe right in that drawer to close it. At 864 usable points of library width
or more, Files opens beside the document and its toggle collapses the pane.
On a partially folded iPhone Duo in landscape, the divider follows the crease
and leaves its reserved strip clear. Links opens on demand. Resizing preserves
the current note and the selected panel tab.
Touches that start inside Markdown tables scroll the table without opening either
side panel. Selected text and zoomed pages retain their ordinary gestures.

Floating Files and Links panels dim the content behind them and block its controls until the
panel closes. Tap the dimmed area to dismiss either panel; there is no panel X.
When a protected session locks during app switching, floating panels close
immediately. Reopen them after unlocking.
Both drawers use the same width and full usable screen height. On iOS, both have
rounded corners. The Files drawer tabs stay at the top;
a centered row directly below them contains New document, New folder and
Collapse all folders. The panel has no library identity/status footer or redundant
library actions menu. The Files tab accepts drops to the library root.
File rows keep the existing font size and touch height.

Tap a folder icon or its enlarged disclosure triangle in Files to expand or collapse
the folder. Tapping a folder name opens its landing note when one exists. Hold the
icon to drag the folder.

The left panel has **Files**, **Search** and **Calendar** tabs. Files uses the
available height for its folder tree. Search keeps its query and results in a
separate tab, with **File names** selected by default and **In documents** available
for content searches. Files and Search retain separate rows and scroll positions;
returning to either tab restores its own list immediately. New result batches replace
the visible rows together. Returning to Files shows the tree even while a search query is retained.

**File names** and **In documents** also keep independent query fields, result
lists, scroll positions and **Show more notes** limits. Switching between them
restores that scope's query and completed results. An unfinished search is cancelled
and resumes when you return to its scope.

For ordinary local libraries, **File names** can show saved results from the
Files directory index while it refreshes in the background. Search in documents
reads supported files for the current query. Unlocked LocalCrypt libraries use
the protected filename cache described in the [LocalCrypt guide](../../rclone/user_mobile/localcrypt.md).
Closing a library reopened from Recent returns to the Home or Documents screen
that opened it.

Calendar starts on the current
month; use its arrows to browse months. A dot marks a day with a note named
`YYYY-MM-DD.md` anywhere in the library. Tap to open it, choosing a folder if
several notes share that date. A missing day offers confirmation before creating
its Markdown file in the library root. Read-only libraries can open existing
daily notes. Refresh daily notes after files are changed outside the library.
Calendar reads filenames only and keeps its index in memory, with a 10,000-entry
and 100-folder-level limit; a failed scan does not offer creation.

In Files, hold a file or folder name for the same **Rename…**, **Move…**, **Copy…**,
or **Delete…** options as its **…** button,
as supported by the location. Destinations stay inside this library and must have
existing parent folders. Copy defaults beside the source as “Filename - Copy”, retaining the extension,
and numbers repeated copies “(2)”, “(3)”, and so on. Custom copy paths and moves refuse existing names; delete asks for
confirmation and permanently removes the selected item and its contents. Links
are not rewritten. Cancelling the action menu or its move/copy form returns to
the pane that opened it. Android Back does the same, keeping the open document
and its history unchanged. Search offers **File names** and **In documents**.
Searches also inspect unopened folders, excluding
hidden configuration.

Documents opened inside a Notes Library appear in Home and Documents **Recent**.
Selecting one returns to that library at the selected document, reusing the loaded
library when possible. LocalCrypt references follow the existing credential history
policy; Session-Only visits remain available in memory while the library is loaded
and disappear when it closes or locks.

Opening a Markdown document shows a full-pane **Opening document…** screen with
**Cancel**. Cancelling keeps the current document and ignores late loading results.

Connections are scanned locally when opening Links, with progress feedback,
clickable filenames and unresolved links. When multiple links have the same
filename, their folder names distinguish them. Scans are
cancelled when the panel closes or the library locks. The scan is limited to
5,000 notes, 10,000 entries and 64 MiB; an exceeded limit shows an error instead
of incomplete backlinks. No plaintext index is saved. Hidden configuration is
excluded and links stay inside the library.

Links such as `[[Tech]]` can open `Tech.md` in an unloaded subfolder. The current
folder and library root take priority; otherwise following the link searches for
a unique match across subfolders, up to 10,000 entries. Use an explicit path such
as `[[Topics/Tech]]` when more than one note has that name.

Local and unlocked LocalCrypt libraries support editing in place. Tap the pencil
to edit the current Markdown document, then the view icon to return to reading.
The file and link drawers remain available. **New Document** offers Markdown or
Remarkable Document before the name and library folder. Existing names are never
overwritten. Leaving an unsaved document offers Save, Discard changes and Cancel;
a failed save keeps the draft open. The library refreshes the saved note and
retains its reading position. Cloud
remotes, including encrypted remotes, remain read-only in the standalone
Markdown viewer and cannot open as libraries. Source inspection does not enable editing.

On iOS, opening the keyboard preserves the document’s native title and actions
while resizing the writing area. Keyboard dismissal restores the previous
navigation visibility; destination tabs can remain hidden while a document is open.

Each Notes Library file/folder row has **…** actions for Rename, Move, Copy and
Delete when supported by its storage. Hold and drag its icon onto a folder
to move it, or onto the Files tab to move it to the top level. Folder actions apply to the folder and its contents; deletion asks for
confirmation and existing copy/move destinations are preserved.

Panel swipes also work over the empty document area containing the New/Open cards.
Swipe right for Files or left for Links; ordinary card taps and vertical scrolling
retain their actions. Wide layouts keep Files visible.
