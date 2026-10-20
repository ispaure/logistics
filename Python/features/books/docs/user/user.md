# Books & Comics

Read EPUB books and CBZ comics directly in Logistics, and edit their metadata.
This feature works independently of Calibre and does not need a Calibre library
or installation. See the [comic guide](../../../comics/docs/user/user.md) for comic
reading, compression and encryption tools.

## Start reading

Double-click an EPUB in **File Browser**, or right-click it and choose **Read EPUB…**.
EPUB books and CBZ comics have separate readers. Each reader's Open dialog and
recent-file menu show only its own format; double-click a CBZ to use the comic reader.
Right-clicking an EPUB offers **Read EPUB…** and **Edit metadata…**.
The same **Edit metadata…** action works for comics and mixed selections.
It opens the appropriate editors without opening a reader.

In the main app, readers open as tabs in **Open documents**. Metadata editors
open in separate popup windows. Reader headers and window titles show the EPUB
filename with its extension, including after metadata edits.
Use **Detach** for a separate window and **Bring back** to return it to the same
workspace. Switching to File Browser or Workspaces retains your open documents.

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

Choose **Aa** or **View → Reading appearance…** to customize the font, text size,
spacing, width and theme in a compact popup. Changes save immediately as personal
settings and use the same values as the central Settings controls.
Line spacing, reading width and reading theme are under **Feature settings →
Books & Comics → Options**. Font and text size are under **Appearance & shared
controls → Styling**, shared with Markdown.
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
and speed, then press **Play**. The same button changes to **Pause** while speaking
and **Resume** while paused. If the system engine cannot pause/resume, the button
is disabled during playback; **Stop** ends playback. Closing the panel, opening another chapter
or closing the reader also stops playback. Turning a page within the same chapter
lets speech continue.

Speech uses PySide6's platform text-to-speech engine. Available voices depend on
your operating system; no separate speech API account is needed. An unavailable
engine produces a message in the panel. Markdown uses the same controls.

## Keep your place

Your chapter, text location and bookmarks are saved for each book. Appearance
follows central software defaults and personal overrides, across all books.
Open the same file again to continue reading. **Navigate → Add bookmark…** adds
a named place; choose it from the sidebar's **Bookmarks** tab to return, or use
**Remove** to delete it.
Each book can have up to 50 bookmarks.

Settings are available under **Logistics Settings → Feature settings → Books &
Comics**, using the feature's `config.ini` and personal AppData overrides. Select
software defaults or personal settings at the top left; **↶** resets personal
fields to inheritance. Legacy per-book appearance is no longer applied. Disable
`remember_position_bool` to stop saving/restoring reading state in new readers,
for both books and comics.
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

Wide reading panes display two consecutive pages; narrower panes display one.
Page turns advance past the displayed pages, and resizing follows the current
text location. The bottom track shows estimated whole-book progress, weighted
by chapter resource size. Taller ticks mark higher-level contents entries;
click anywhere on the track to jump to that part of the book.

Read aloud opens a compact panel anchored to its toolbar button. The reader
highlights the spoken word when the platform engine reports word progress;
otherwise it highlights the current utterance. During speech, the reading pane
follows that pointer and keeps it near the center, including after resizing.
Closing the panel, changing chapters, or closing the reader stops playback.

## Reading defaults

In **Logistics Settings → Appearance & shared controls → Styling**, the shared
reading font and size (7–24) apply to EPUB and Markdown. Sizes use a common
96-DPI reference across macOS, Windows and Linux, while display scaling follows
the operating system. The default is Arial
at 10 pt, a neutral sans serif for books and technical documentation. Automatic uses the
application text font. Changes made through Aa appear here too. **Feature settings → Books
& Comics → Options** exposes `line_spacing_int` (100–220), `reading_width_int`
(480–1400), `theme_mode` and `remember_position_bool`. Larger text or spacing means
fewer words per page. Appearance is global; positions and bookmarks remain per
book. Software mode edits the tracked defaults; personal mode writes AppData
overrides, with ↶ reset. These settings do not rewrite the EPUB.

## If a book will not open

The reader rejects EPUBs with more than 20,000 archive members or more than
512 MiB of declared uncompressed content. A single resource is limited to 32 MiB;
an oversized chapter/image can therefore fail even when the overall book is smaller.
These are uncompressed-content limits, not the `.epub` file's size on disk. Corrupt
or protected content can also prevent loading. Keep the original and use another
reader to investigate; Logistics does not repair or remove protection from EPUBs.

File Browser tile covers show your last saved reading-order chapter as a badge,
for example **Ch 4/12**. Unread books have no badge. It updates as the reader saves
your position, without changing the EPUB. Chapter numbering matches the reader's
chapter counter, including front matter in its reading order. Disabling Remember
Position hides the badge. Existing saved positions work once the cover is loaded.

## Mobile development builds

See [Books mobile workflows](../user_mobile/reading.md#mobile-development-builds).

## Metadata inside LocalCrypt

On desktop, open the LocalCrypt browser and choose **Edit EPUB metadata…** for a
book. On mobile, open its encrypted offline copy and choose **Edit metadata…**.
Both save metadata to the encrypted local copy, preserve unrelated resources and
retain any inner ZIP password. No plaintext backup is made in this workflow, and
saving does not upload the book. See the [LocalCrypt guide](../../../rclone/docs/user/user.md#read-and-edit-a-localcrypt-copy-on-desktop).

EPUB metadata windows opened from private storage begin their titles with **🕵️ Private -**.

Desktop **Open EPUB…**, including the New Document launcher, uses the shared Local/LocalCrypt file picker with an EPUB filter. Local books keep ordinary reading history. LocalCrypt books open in separate **🕵️ Private -** readers without recent-file records or saved reading positions; bookmarks stay in the session. Metadata saves update the encrypted copy without plaintext backups.

Desktop private-book unlocks keep the password prompt open after a wrong attempt,
show an inline error and clear and focus the field for retry. Enter submits once;
Cancel abandons that open or metadata unlock.

On mobile, ordinary EPUB chapter rendering and comic presentation share portable
format models with desktop while retaining their own native interface. Reader
contents/appearance screens return to reading through Back; a book opened from
Files then returns to its originating folder. Provider-backed bookmarks keep
their existing session-only policy. See the [mobile guide](../../../../../docs/user_mobile/user_mobile.md)
for supported reading and storage workflows.

## Native mobile reading

See [Books mobile workflows](../user_mobile/reading.md#native-mobile-reading).

