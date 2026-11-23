# Books and comics on mobile

## Browse a Calibre library

Open **Documents → Libraries → Books** and tap a library to browse it in
Workspaces. Logistics looks for a `metadata.db` file at each ordinary local
storage root and up to two folder levels below it. This includes readable
Rclone Copies. The database serves as a folder marker. Browse the author
and title folders and tap an EPUB to open it in the reader. Tap the
**Documents** tab again to rescan after adding a library.

## Browse comics and import individual files

Open **Books & Comics** and tap a configured Local or unlocked LocalCrypt library folder. In its root `remoteConfig.ini`, set `[LogisticsComics]` and `libraries = Comics,Mangas` on separate lines to list those immediate child folders. Existing ComicRack and YACReaderLibrary configurations are also detected. Use **Refresh** after changing configuration or pulling files.

Use **Import…** for a standalone EPUB or CBZ/ZIP. This creates a private copy and preserves the external source. Reopen through document sessions or Recent. **Show in folder** reveals an available original. **Show cached copy in folder** reveals the private copy when the original is unavailable.

For an AES or ZipCrypto comic import, enter the ZIP password and tap **Unlock comic**. A wrong password clears the field for retry. Cancel keeps the encrypted import. Closing clears the active password and decoded pages, so opening asks again. Entry names remain visible. Folder readers can use configured archive passwords.

EPUB imports permit up to 5,000 entries, 256 MiB for archive and expanded total, and 8 MiB per member. Chapters and rendered HTML are limited to 2 MiB. DRM, encrypted EPUBs and fixed-layout SVG books are unsupported. CBZ/ZIP imports have the 5,000-entry cap and separate [comic page limits](../../comics/user_mobile/reading.md#supported-formats-and-page-limits). See [comic gestures](../../comics/user_mobile/gestures.md).

### Reader navigation and imported metadata

Swipe or use arrows to turn pages. Use EPUB's chapter list and **Bookmark** or **Unbookmark** to navigate by passage. Comics offer **Comic pages…**, a slider and separate neighboring-comic buttons when available. Appearance controls follow the format.

**Edit metadata…** writes to ordinary imported copies and leaves their sources intact. See [EPUB reading](reading.md#native-mobile-reading) and [editing comic metadata](../../comics/user_mobile/reading.md#edit-comic-metadata).
