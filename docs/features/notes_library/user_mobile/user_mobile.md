# Notes Library on mobile

[Notes Library guides](../notes_library.md)

Open discovered libraries from Documents or use existing folder and favourite
entry points. Mobile navigation remains in Documents. **Settings → Features →
Notes Library** controls libraries independently of Text Editor. Existing users
inherit their former Text Editor selection once; later changes are independent.
Close an open library before turning its feature off. Markdown and embedded text
editing remain usable with Text Editor disabled. Notebooks controls drawing opens
and creation separately.

Use Files, Calendar and Links to navigate, and the library's close control to
leave. Unsaved changes retain their save/discard/cancel choices. Folder-backed
Markdown uses the [shared mobile editing controls](../../text_editor/user_mobile/user_mobile.md).

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
current library page stays available when you return. Markdown video embeds
keep simple inline controls and start paused at zero; they do not autoplay or
preload the whole video when you open a page.
Unsupported formats
show file information in that pane. Image previews allow up to 8 MiB and 16
megapixels; PDFs allow up to 32 MiB. Back and forward retrace files opened in the
library; switching files asks about unsaved changes.

Folders with a same-named `Folder/Folder.md` page have underlined names in Files;
tap the name to open that page, or use the arrow to expand the folder.
A compact breadcrumb row below the document controls shows the path for every
open file type, including images and PDFs. Underlined folders open their page;
plain folder names have no action. Ancestor names shorten first on narrow
screens so the current filename keeps priority.


## Notes Library and Documentation Library

Open **Documents → Notes Library** to see libraries found in Local and unlocked
LocalCrypt storage. Discovery looks for an `.obsidian` directory at the storage
root and up to two folders below it. Use **Refresh libraries** after adding or
moving one. Unlock credentials first to see encrypted libraries. Workspaces
opens folders directly without a Notes Library prompt or menu choice. Notes
Library keeps actual filenames in its sidebar.

In writable libraries, **••• → New folder…** creates a folder beside the selected
note or inside the selected folder. **Rename / move selected…** accepts a new
path inside the library, with existing folders. These actions also work on
selected folders. Moves preserve navigation history and do not overwrite existing
entries. Links in other notes are not rewritten.

An unopened library shows **Open Document** and **New Document** cards. New Document
first offers **Remarkable Document** and **Markdown**, followed by the name and a
folder picker confined to this library. It cannot publish outside the library.
Markdown and drawing documents open inside the same library pane. The file and
link drawers remain available while editing. Changing document or closing the
library asks to save or discard unsaved edits; cancelling keeps the draft open.
Malformed drawings and failed saves retain the current document.

The first mobile header row contains Close, the left-pane button, the filename,
and the right-pane button. Note history, edit/view and the actions menu are on a
second row, hidden during folder browsing. Single-line wiki headings such as
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


From **Documents → Notes Library**, choose a Local or unlocked LocalCrypt library
when the folder contains an `.obsidian` directory. Cloud folders never offer
library mode; download or sync a local copy first. Individual cloud Markdown
files can still be opened in the standalone read-only viewer.

On narrow screens, **Files** opens over the full-width document. Use the
upper-left Files button or swipe right across the document to browse; swipe left
in the drawer or tap outside it to return to reading. Choose a note to close the
drawer. The upper-right Links button, or a left swipe across the document,
opens **Backlinks** and **Outgoing links**. Swipe right in that drawer to
close it. At 864 usable points of library width or more, Files and Calendar stay
beside the document; Links always opens on demand. Resizing preserves the current
note and the selected Files or Calendar tab.
Horizontal tables, selected text and zoomed pages retain their ordinary gestures.

Floating Files and Links panels dim the content behind them and block its controls until the
panel closes. Tap the dimmed area to dismiss either panel; there is no panel X.
The storage/editability caption in Files uses a subdued italic style.

The left drawer has **Files** and **Calendar** tabs. Calendar starts on the current
month; use its arrows to browse months. A dot marks a day with a note named
`YYYY-MM-DD.md` anywhere in the library. Tap to open it, choosing a folder if
several notes share that date. A missing day offers confirmation before creating
its Markdown file in the library root. Read-only libraries can open existing
daily notes. Refresh daily notes after files are changed outside the library.
Calendar reads filenames only and keeps its index in memory, with a 10,000-entry
and 100-folder-level limit; a failed scan does not offer creation.

In Files, hold a file or folder for **Move / rename…**, **Copy…**, or **Delete…**,
as supported by the location. Destinations stay inside this library and must have
existing parent folders. Copy and move refuse existing names; delete asks for
confirmation and permanently removes the selected item and its contents. Links
are not rewritten. The search choices are **Search in File Names** and
**Search within Documents**. Searches also inspect unopened folders, excluding
hidden configuration.

Opening a Markdown document shows a full-pane **Opening document…** screen with
**Cancel**. Cancelling keeps the current document and ignores late loading results.

Connections are scanned locally when opening Links, with progress feedback,
clickable note paths, unresolved links and word/character counts. Scans are
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

Each Notes Library file/folder row has **…** actions for Move / rename, Copy and
Delete when supported by its storage. Hold and drag a filename onto a folder
to move it, or onto **Library root** to move it to the top level. Folder actions apply to the folder and its contents; deletion asks for
confirmation and existing copy/move destinations are preserved.
