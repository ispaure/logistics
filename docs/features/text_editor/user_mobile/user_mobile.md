# Text editing on mobile

The mobile app provides its text editor in Documents and Workspaces.
See the [Documents and editing](../../../user_mobile/documents/documents.md) guide for opening, editing, saving and exporting files.

Notes Library also runs [JSON data views and reusable `dv.view` scripts](../user/user.md#json-data-views-in-notes-library)
in reading mode, enabled by default. The same API subset and file/path limits
apply on desktop and mobile. Editing retains the authored code blocks.

JSON, JavaScript and [other supported source files](../user/user.md#embedded-source-files-in-notes-library)
appear in Files and open in the same library detail pane using the normal native
code input. Use **••• → Save** or **Find / replace…**. Switching files retains the
library history and asks before discarding unsaved edits.

Markdown opens in preview. The top **pencil** icon (**Edit Markdown**) opens
directly editable, formatted text. Use **••• → Source editing** for exact syntax,
or **••• → Formatted editing** to return to styled writing. These commands remain
available with the keyboard open. The mode selector is shown only in Source;
formatted editing has its own compact formatting toolbar. The top **page** icon returns to preview. Save is shown
only after text changes, and disappears after saving or reverting. Reading uses
one compact top toolbar in portrait and landscape on iOS and Android, with no
separate edit/save footer or duplicate file-drawer row.
In formatted editing, type `# Heading` (through six heading levels), `**bold**`,
`*italic*`, underscores or backticks to see their formatting as you write.
Select words and type `*` to surround them with emphasis; type a second `*`
while they remain selected to make them bold. Underscores and backticks also
wrap selections. Incomplete syntax, escaped markers and text inside code stay
literal. Inline markers show when the cursor touches or is inside their formatted
span, or a selection overlaps it. Heading markers show anywhere in that heading.
Moving elsewhere hides them, including within the same paragraph, following the
desktop editor’s cursor rules. Toolbar Undo/Redo and hardware keyboard shortcuts
work with these edits; Ctrl/Cmd+B and Ctrl/Cmd+I apply bold and italic.

In Markdown preview and Notes Library, choose **••• → Find in this page…**
to highlight text in the open note. A compact panel above the page shows the
current match and total, with Previous/Next arrows and **Done**. Done clears page
marks. In the Files drawer, **Search Notes Library** shows one row per matching note or
folder across the library. **Documents** searches names and Markdown text, with
name matches first. Choose **Names only** to search file and folder names.
If results share a name, their parent paths distinguish them. Enter `turtle red`
to require both words in any order, or `"this follow this"` for a phrase.
Search ignores case and treats spaces, hyphens and underscores alike in phrases.
Clear the field to return to the folder tree. In the editor,
**Find and replace…** searches Source mode and selects the current source match.

Background memory cleanup preserves the active Markdown reading or editing
surface when returning from sleep. Reading and formatted editing use the
platform's default font, including the device-selected sans-serif font on Android;
code retains a monospace font.
Markdown preview and formatted editing use the app's window background throughout
the reading area, including text margins, following light and dark mode. The text
blends into the surrounding view without a separate rectangular panel.
Pinch Markdown to change its font size and reflow the text within the view.
Markdown, EPUB and plain text retain separate font-size settings.
On iOS, text and Markdown editors share the readers' native title bar. The
filename stays centered, and **Save** appears beside the reading/actions controls
only while there are unsaved changes. Use **Actions → Rename document…** to change
a managed document's name. Notes Library shows the current note's filename and
keeps **‹ / ›** page-history buttons visible beside its reading controls. Use
**×** to close the library from any page; the parent-folder command is in **•••**.
Markdown and editable Notes Library pages put **Read aloud…** in **•••** to leave
room for their titles. When a managed editor has unsaved changes, Save takes
the primary action slot; **View document** remains available in **•••**.
Enable **Settings → Markdown → Justify text** to align paragraphs and lists to
both edges in previews and formatted editing, including folder and vault readers.
The switch defaults to off and saves on this device independently of EPUB.
It reflows the display without changing Markdown source or unsaved edits;
headings, code blocks, tables and Source mode keep their existing alignment.
Open the **three-dot Document actions** menu in the editor or Markdown preview
and choose **Delete document…** to remove an app-stored document, including an
unsaved Untitled document. Confirm the warning to close it and permanently remove
its saved content, recovery copy and Recent entry. **Cancel** keeps it open.
The document's **×** keeps the stored document. Unsaved changes open a native
popup with **Save**, **Quit without saving**, and **Cancel**. Find and Replace
changes **×** to a back arrow that dismisses search and keeps the document open.
The three-dot menu omits New, Open from Files, Import and Close. Delete uses red
destructive styling and a native **Delete / Cancel** confirmation.
Close other app windows before deleting. Files opened directly from a folder
continue to use that folder's file-management actions.
Choose **New Document** from Home, choose a document type, then enter its name
and choose where to save it. Remarkable Document (`.rmdoc`) opens the drawing editor;
Markdown (`.md`) opens the Markdown editor. The filename remains independent of the headings you add while editing.
For a new Markdown document, tap in the blank writing area to place the cursor.
While editing, Bold, Italic, Undo, Redo and Format appear below the text viewport,
above the system keyboard. The row remains available with a hardware keyboard,
alongside the usual keyboard shortcuts.
Opening the keyboard resizes that area; continuing to type scrolls only as needed
to keep the caret visible. Plain text and Markdown Source use native text inputs.
The language dropdown starts on **Automatic**, following the filename and initial
source line. A manual language stays selected through edits and renaming while
that editor remains open. **Plain Text** disables highlighting; choose Automatic
to resume detection. Changing language does not edit the document's text.
On short phone screens or with enlarged text, the space around the caret shrinks
to keep the current line inside the writing area above the keyboard.
On Android, a short keyboard-sized window hides destination navigation and
secondary mode/language controls while retaining the document action bar, including
Save and **•••**. Hidden secondary controls return when the keyboard closes.
In a short formatted writing area, the formatting row uses compact spacing;
its scrollable Format panel stays above the keyboard. Source mode stays
inside the app in landscape. The formatting page is anchored to its viewport,
and tight layouts reduce padding around the writing line.
The main toolbar uses a compact row while the keyboard is open in a tight window.
On a horizontal Duo fold, the text viewport fits above the active fold and the
formatting row stays in the lower available area, above the system keyboard.
The app does not change the system keyboard’s size.
In very short formatted editing areas, headings use body-sized text so a line
fits; their heading levels remain intact.
Formatting and source share the same
buffer, recovery and Save actions. There is no automatic preview split on phones
or tablets. See [Reading and editing](../../../user_mobile/documents/reading-and-editing.md)
for supported formatting and syntax that uses Source mode.

Rotating Android between portrait and landscape keeps the current Markdown
document open while the content reflows to the available width. A landscape
file sidebar collapses on return to portrait so the document uses the full
reading width; the hamburger can reopen the file drawer.

Tap the **speaker** icon in the Markdown preview or vault reader toolbar to open
**Read aloud** in a floating panel with speed, pause/resume and stop controls.
The panel leaves the page layout unchanged. Choose the saved offline voice in
**Settings → Read aloud → Read-aloud voice**. Select a passage to read it, or
play the whole rendered note. Speech follows the preview: links read their visible
labels without their destinations, and formatting markers are omitted. Visible
URLs and literal code remain readable.
See [Reading and editing](../../../user_mobile/documents/reading-and-editing.md#markdown-read-aloud).

Formatting controls use the same icons as desktop, including Bold, Italic, Undo,
Redo and the Format menu. Buttons keep accessible names and tooltips.
In the **Format** menu, tap the **link** icon to open the URL prompt. Enter a URL
or relative file path and choose **Insert link** (or press Enter). Selected text
becomes the link; with no selection, the editor inserts “Link”. **Cancel** keeps
the text and selection unchanged. The URL field appears only in this prompt.

## Images in folder-backed Markdown

Markdown opened from Local, LocalCrypt or a connected remote displays animated GIFs and static
WebP, PNG and JPEG images in preview and formatted editing. Use a path relative to the Markdown
file, for example `![Photo](../../../../Python/features/text_editor/docs/user_mobile/images/photo.webp)` or `![[images/photo.webp]]`.
Parent-folder paths work within the same storage root. Bare filenames refer to
the Markdown file's folder; there is no vault-wide filename search.

Obsidian embeds accept spaces and `#` in filenames, such as
`![[photo #1.png|400]]`. In a Notes Library, missing relative images are also
looked up from the library root, then in `Attachments`, `Assets` and `Images`
(with lowercase variants). Explicit `./` or `../` paths keep their relative meaning.
The first matching image is used; this does not scan the library recursively.

Images fit within the page width on phones and tablets. To request a smaller
width in pixels, use `![[images/demo.gif|200]]` or
`![Demo|200](../../../../Python/features/text_editor/docs/user_mobile/images/demo.gif)`. `|400x200` sets both dimensions; oversized requests
shrink proportionally to fit the page. Formatted editing and saving preserve the
size hint. Source mode displays the editable reference.

LocalCrypt images are decrypted into memory for display; no decrypted image file
or separate import is created. Missing, locked, unsupported or oversized images
show their alternative text. Images are limited to 8 MiB and 16 megapixels each,
with a 16 MiB image-data budget per render. Animated WebP is unsupported.
Network URLs and paths outside the current provider root are not loaded.
Standalone imported Markdown without its original folder cannot resolve sibling
images; open the file through Local or LocalCrypt to retain folder access.

## Lock-screen speech

Markdown read-aloud shares the system playback controls used by EPUBs, including
Play/Pause and approximate 15-second skips. Session-only credentials require an
explicit saved opt-in for background speech; it defaults to off. See
[Speech while locked](../../../user_mobile/settings/settings.md#speech-while-locked).

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

The library opens with **Files** over the full-width document. Use the upper-left
Files button or swipe right from the document's left edge to browse; swipe left
in the drawer or tap outside it to return to reading. Choose a note to close the
drawer. The upper-right Links button, or a left swipe from the document's right
edge, opens **Backlinks** and **Outgoing links**. Swipe right in that drawer to
close it. These floating panels work on phones, tablets and Duo in both orientations.
Horizontal tables, selected text and zoomed pages retain their ordinary gestures.

Files and Links dim the content behind them and block its controls until the
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
Delete when supported by its storage. Long-pressing the filename opens the same
menu. Folder actions apply to the folder and its contents; deletion asks for
confirmation and existing copy/move destinations are preserved.
