# Books & Comics

Read EPUB books and CBZ comics directly in Logistics, and edit their metadata.
This feature works independently of Calibre and does not need a Calibre library
or installation. See the [comic guide](../../comics/user_docs/index.md) for comic
reading, compression and encryption tools.

## Start reading

Double-click an EPUB in **File Browser**, or right-click it and choose **Read EPUB…**.
EPUB books and CBZ comics have separate readers. Each reader's Open dialog and
recent-file menu show only its own format; double-click a CBZ to use the comic reader.
Right-clicking an EPUB offers **Read EPUB…** and **Edit metadata…**.
The same **Edit metadata…** action works for comics and mixed selections.
It opens the appropriate editors without opening a reader.

Choose a chapter or nested section in the chapter list. **Previous chapter** and
**Next chapter** follow the book's reading order. Links to another chapter or
section work inside the reader. Use Left/Right arrows or Page Up/Page Down to
turn screen-sized pages; Space moves forward and Shift+Space moves back. The
footer arrows also turn pages. **Navigate → Go to page…** (Ctrl+G, Command+G on
macOS) jumps to a screen page in the current chapter. At a chapter boundary, a page turn continues
into the next or previous chapter. The reading area does not scroll. Left/Right also work while the chapter or
bookmark list has focus. Up/Down in the reading area do nothing; in the sidebar
they still move through the list. Mouse-wheel notches turn one page at a time.
Touchpad sensitivity and cooldown use the same **commonUtils → Wheel navigation**
settings as the comic reader.

Page counts adapt to the window size, font and spacing. The footer shows the
chapter and current page; its tooltip shows a text location. Saved positions and
new bookmarks follow a position in the chapter's text rather than a fixed page
number, so changing the layout keeps you near the same passage.

Selecting an EPUB in File Browser shows its cover and metadata in the **Book
Metadata** preview panel, just like a comic. Tile thumbnails use the cover too.
Books without an embedded cover still show their metadata.

Choose the **Aa** button or **View → Reading appearance…** to adjust font, text
size, line spacing and reading width.
**Light**, **Dark**, **Sepia** and **Slate** change the reading area. Drag the
divider to resize the sidebar, or use **View → Show sidebar** to hide it.
The fullscreen button or **View → Full screen** (F11) gives the book more room.
Escape closes search first, then exits fullscreen. A maximized window returns
to its maximized state after fullscreen.

**Find next** searches the current chapter, ignores letter case and wraps back
to its beginning. **Edit → Find…**, or Ctrl+F (Command+F on macOS), opens search;
Escape hides it again. **File → Open recent** returns to recently opened files.
Alt+Left/Right moves between chapters.

## Read aloud

Choose **Read aloud** in the toolbar or **View → Read aloud…**. Select a passage
first to read only that passage; otherwise reading starts at the visible page
and continues through the current chapter. Choose a language, installed voice
and speed, then press **Read**. **Pause / Resume** appears when the system engine
supports it; **Stop** ends playback. Closing the panel, opening another chapter
or closing the reader also stops playback. Turning a page within the same chapter
lets speech continue.

Speech uses PySide6's platform text-to-speech engine. Available voices depend on
your operating system; no separate speech API account is needed. An unavailable
engine produces a message in the panel. Markdown uses the same controls.

## Keep your place

Your chapter, text location and reading preferences are saved for each book.
Open the same file again to continue reading. **Navigate → Add bookmark…** adds
a named place; choose it from the sidebar's **Bookmarks** tab to return, or use
**Remove** to delete it.
Each book can have up to 50 bookmarks.

Defaults are available under **Settings → Books & Comics**, using the feature's
`config.ini`. Saved preferences for a particular book take precedence. Disable
`remember_position_bool` to stop saving/restoring reading state in new readers.
Moving a book to another path starts a separate reading history.
Shortcuts or symbolic links to the same book share its reading history.

On macOS, reading state lives in
`~/Library/Application Support/commonUtils/Cache/Books/`. Other platforms use
the commonUtils cache directory. These small files store preferences and
bookmarks, not the book's contents.

## Edit the book's metadata

Use **Edit metadata…** to change the title, authors, language, publisher, tags or
description. Enter authors and tags on separate lines. Language normally uses a
code such as `en` or `fr`. Identifiers are shown for reference and preserved.

**Save** writes the changes into the EPUB itself. It keeps the original beside
the book as `book.epub.bak`; subsequent saves use `.bak.1`, `.bak.2`, and so on.
Backups are never overwritten. Chapters, images and unrelated metadata are kept.
Cancel leaves the book unchanged. If another application changes the EPUB while
it is open, reopen it before editing or continuing to read.

To restore a backup, close the reader, keep a copy of the current EPUB if needed,
then replace it with the backup and give it the original `.epub` filename.

## Supported books

The reader supports ordinary EPUB 2 and EPUB 3 text books, including nested
tables of contents and embedded images. It uses simplified reading styles so
font controls and themes work consistently. Elaborate publisher CSS, fixed-page
layouts, SVG-only chapters, audio/video, embedded fonts, interactive content and
DRM-protected text are outside this first version. External links and resources
are not opened automatically.

EPUB files remain ZIP archives; the reader does not unpack them into a temporary
folder. Archive and resource size limits protect against accidentally opening
unreasonably large or corrupt books.
