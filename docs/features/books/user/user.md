# Books & Comics

Read EPUBs and edit their metadata in Books & Comics. Use the [Comics guide](../../comics/user/user.md) for CBZs.

## Start reading

Double-click an EPUB or choose **Read EPUB…** in File Browser. Use **Open documents** to switch readers or **Detach** and **Bring back** to move one between windows.

Use the chapter list, **Previous chapter** and **Next chapter** or **Alt+Left/Right**. Turn pages with arrows, Page Up/Page Down, Space/Shift+Space or the wheel. Wide panes show spreads. **Navigate → Go to page…** (**Ctrl/⌘+G**) jumps within the chapter. The footer track jumps within the whole book after counting finishes. Resizing follows your text position.

**Edit → Find…** (**Ctrl/⌘+F**) searches the current chapter. **Aa** adjusts appearance. **View → Show sidebar** toggles the chapter list. **F11** enters fullscreen and **Escape** closes search or leaves fullscreen.

## Read aloud

Open the speaker or **View → Read aloud…**, choose speed and press **Play**. Select a passage to read only that text. Otherwise, speech continues from the visible page through later chapters. The 15-second skips follow that scope and preserve pause. Hiding controls keeps speech running. Opening another chapter manually or closing stops it.

Automatic language detection uses installed system voices and falls back to book metadata for uncertain text. Choose another language or voice in the panel. See [shared read-aloud controls](../../../../Python/commonUtils/docs/user/markdown/markdown.md#read-aloud).

## Keep your place

Reopen the same path to resume at your passage. Use **Navigate → Add bookmark…** and the sidebar **Bookmarks** tab, up to 50 per book. Moving the book starts a new history. Disable `remember_position_bool` in Books & Comics settings to stop saving and restoring positions in new readers.

## Edit the book's metadata

Right-click an EPUB and choose **Edit metadata…**. Put each author and tag on a separate line and use language codes such as `en`. **Save** rewrites metadata in the EPUB and keeps `book.epub.bak`, then numbered backups. Reopen if another app changes the file. To restore a backup, close the reader, keep any current copy you need and rename the backup to the original EPUB filename.

## Supported books

Ordinary EPUB 2 and 3 text books support nested contents, internal links and images. Fixed layouts, SVG-only chapters, media, scripts, embedded fonts and DRM-protected text are unsupported.

## Reading defaults

**Appearance & shared controls → Styling** sets the reading font and size shared with Markdown. **Feature settings → Books & Comics → Options** controls spacing, width, theme and Remember Position. **Aa** saves personal overrides, and **↶** restores inheritance.

## If a book will not open

Check for damage or DRM. Limits are 20,000 archive entries, 512 MiB expanded and 32 MiB per resource. Keep the original if another reader is needed to inspect it.

## Mobile development builds

See [Books mobile workflows](../user_mobile/reading.md#mobile-development-builds).

## Metadata inside LocalCrypt

Choose **Edit EPUB metadata…** in the LocalCrypt browser or **Edit metadata…** on mobile. Saves update the encrypted offline copy and preserve the inner ZIP password. There is no plaintext backup. Push separately to update the remote. See [LocalCrypt editing](../../rclone/user/user.md#read-and-edit-a-localcrypt-copy-on-desktop).

Private readers are absent from ordinary Recent. Positions and bookmarks use credential ZIP encryption where available and stay in memory for passwordless sessions. Retry a wrong password in the same prompt.

## Native mobile reading

See [Books mobile workflows](../user_mobile/reading.md#native-mobile-reading) and the [mobile guide](../../../user_mobile/user_mobile.md).

## Page-turn motion

A short slide animates turns within and between chapters.
