# Text editing on mobile

The mobile app provides its text editor in Documents and Workspaces.
See the [Documents and editing](../../../user_mobile/documents/documents.md) guide for opening, editing, saving and exporting files.

Markdown opens in preview. The top **pencil** icon (**Edit Markdown**) opens
directly editable, formatted text. Use **••• → Source editing** for exact syntax,
or **••• → Formatted editing** to return to styled writing. These commands remain
available with the keyboard open. The mode selector is shown only in Source;
formatted editing has its own compact formatting toolbar. The top **page** icon returns to preview. Save is shown
only after text changes, and disappears after saving or reverting. Reading uses
one compact top toolbar in portrait and landscape on iOS and Android, with no
separate edit/save footer or duplicate file-drawer row.
In Markdown preview and Notes Library, choose **••• → Find in this page…**
to highlight text in the open note. A compact panel above the page shows the
current match and total, with Previous/Next arrows and **Done**. Done clears page
marks. Notes Library's **Filter loaded file names** field filters the loaded
filename list; it does not search the contents of every note. In the editor,
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
Choose **New document** from Home to enter a name
and select the file type before creating it. The filename remains independent of the headings you add while editing.
For a new Markdown document, tap anywhere in the blank writing area below the
formatting toolbar to place the cursor and open the keyboard.
The formatting toolbar stays above the writing area while the document scrolls.
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
In a very short formatted writing area, **Format** becomes a floating button;
its scrollable panel keeps formatting and link controls reachable above the keyboard. Source mode stays
inside the app in landscape. The formatting page is anchored to its viewport,
and tight layouts reduce padding around the writing line.
The main toolbar uses a compact row while the keyboard is open in a tight window.
In the shortest writing areas, **Format** opens a popup containing the formatting
commands, leaving the full height available for text.
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

Markdown opened from Local or LocalCrypt displays animated GIFs and static
WebP, PNG and JPEG images in preview and formatted editing. Use a path relative to the Markdown
file, for example `![Photo](../../../../Python/features/text_editor/docs/user_mobile/images/photo.webp)` or `![[images/photo.webp]]`.
Parent-folder paths work within the same storage root. Bare filenames refer to
the Markdown file's folder; there is no vault-wide filename search.

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

## Notes Library

From a Local, LocalCrypt or Remote location's actions page, choose **Open Notes
Library** when the root contains an `.obsidian` directory. The reader opens in
Documents with a folder/page sidebar, note history and read-aloud controls.
Folder and file icons identify each sidebar entry; the selected row is highlighted.
When the sidebar and page appear side by side, navigation, edit and read-aloud
controls sit above the Markdown page.
Remote libraries have no filename filter or recursive index; folders load only
when expanded. Local filtering searches only loaded note names. Reading is
limited to 2 MiB. Hidden configuration is excluded and links stay inside the library.

Local and unlocked LocalCrypt libraries support editing. Tap the pencil to open
the current note in formatted editing, or choose **••• → New note…** to create a
Markdown file in the current note’s folder. Existing names are never overwritten.
Choose **Return to Notes Library** from the editor’s actions to return to the same
note; unsaved edits offer Save, Discard changes and Cancel. A failed save keeps the draft.
The library refreshes the saved note and retains its reading position. Cloud
remotes, including encrypted remotes, remain read-only in both the library and
standalone Markdown viewer. Source inspection does not enable editing.

On iOS, opening the keyboard preserves the document’s native title and actions
while resizing the writing area. Keyboard dismissal restores the previous
navigation visibility; destination tabs can remain hidden while a document is open.
