# Books and comics on mobile

## Books and comics

Open **Books & Comics** and tap a configured Local or unlocked LocalCrypt library folder. In its root `remoteConfig.ini`, set `[LogisticsComics]` and `libraries = Comics,Mangas` on separate lines to list those immediate child folders. Existing ComicRack and YACReaderLibrary configurations are also detected. Use **Refresh** after changing configuration or pulling files.

Use **Import…** for a standalone EPUB or CBZ/ZIP. This creates a private copy and preserves the external source. Reopen through document sessions or Recent. **Show in folder** reveals an available original. **Show cached copy in folder** reveals the private copy when the original is unavailable.

For an AES or ZipCrypto comic import, enter the ZIP password and tap **Unlock comic**. A wrong password clears the field for retry. Cancel keeps the encrypted import. Closing clears the active password and decoded pages, so opening asks again. Entry names remain visible. Folder readers can use configured archive passwords.

EPUB imports permit up to 5,000 entries, 256 MiB for archive and expanded total, and 8 MiB per member. Chapters and rendered HTML are limited to 2 MiB. DRM, encrypted EPUBs and fixed-layout SVG books are unsupported. CBZ/ZIP imports have the 5,000-entry cap and separate per-page limits. See [comic workflows](../../comics/user_mobile/reading.md#native-mobile-library) and [comic gestures](../../comics/user_mobile/gestures.md).

### Reader navigation and imported metadata

Swipe or use arrows to turn pages. Use EPUB's chapter list and **Bookmark** or **Unbookmark** to navigate by passage. Comics offer **Comic pages…**, a slider and separate neighboring-comic buttons when available. Appearance controls follow the format.

**Edit metadata…** writes to ordinary imported copies and leaves their sources intact. For Local or unlocked LocalCrypt comic folders, use **Files → Actions → Edit comics in this folder…**. See [EPUB reading](reading.md#native-mobile-reading) and [comic batch limits](../../comics/user_mobile/reading.md#mobile-collection-search-and-folder-batches).
