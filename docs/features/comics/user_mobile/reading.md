# Comics mobile workflows

**Settings → Books & Comics → Comic cover on outer display** uses the first comic page on iPhone Duo. See [outer display requirements and battery impact](../../books/user_mobile/reading.md#book-cover-on-iphone-duo).

On Android, choose **Appearance → Volume buttons turn pages → Apply and return**. Volume down advances and volume up goes back. This off-by-default setting is separate from EPUB.

## Mobile development builds

iOS and Android read CBZ/ZIP with PNG, JPEG or static WebP pages. Each page is limited to 8 MiB, 8192 pixels per axis and 16 megapixels. See the [mobile guide](../../../user_mobile/user_mobile.md) for validation. Compression, CBR conversion and collection organization are desktop tools.

## Native mobile library

Browse configured Local or unlocked LocalCrypt libraries in **Books & Comics**. Local comics open from their source. Use **Import…** for standalone copies, including AES and ZipCrypto. Enter the comic ZIP password at **Unlock comic**. See [imports and password retries](../../books/user_mobile/library.md#books-and-comics).

Tap the page for controls. Use **Comic pages…** or the footer slider to jump to a page. Use the separate buttons above the image for neighboring comics. Manga reverses reading order. **Close comic** keeps the file. **Show in folder** reveals its location when available, and **… → Info…** shows the current path.

Use **Appearance → Comic page layout** for Single, Automatic or Two pages. Automatic uses a spread in wide panes. Landscape and ComicInfo DoublePage pages display alone. **Split wide pages in portrait** shows wide art as two overlapping halves, in reading order, with source-page numbers and a **1/2** or **2/2** badge. Use **Fit comic page** to resume swipes after panning. See [comic gestures](gestures.md) for the magnifier and boundary swipes.

To inspect retained imports, open **Settings → Reset → Clear cached documents**. **Clear redundant copies…** removes verified duplicate copies and their reading records after confirmation. Changed copies, drafts and originals are kept.

### Mobile collection search and folder batches

Use **Edit metadata…** in an ordinary imported reader. Successful saves preserve page images and the external import source. Standalone encrypted imports support reading and have no metadata writer.

For Local or unlocked LocalCrypt folders, choose **Files → Actions → Edit comics in this folder…**. Check only intended fields, then **Apply selected fields**. An empty checked field clears it. The scan includes descendants up to 200 comics, 10,000 entries and 16 folder levels. Changed or unsupported archives fail preflight. **Cancel after current comic** keeps completed saves and leaves remaining files untouched. Inspect results and reopen the batch if revisions cannot refresh.

Unlocked LocalCrypt needs the configured inner password for protected archives. Saves update ciphertext locally. Push separately to update the remote. Closing, backgrounding or locking clears draft fields and suggestions. Already published edits remain saved.

### iOS edge-to-edge reading

Tap the fullscreen page to restore controls. An active Duo fold keeps the divider clear between paired pages or places the picture above a horizontal fold. **Reduce Transparency** disables the artwork behind side controls.

## Reading on a TV

Use AirPlay Screen Mirroring on iOS or Android system casting. A dedicated output shows only the picture when the system supplies a presentation display. While sharing, comic readers temporarily use paired portrait pages and complete wide pages. Disconnect to restore the saved layout. Active session-only credentials or retained protected views blank output even for an ordinary comic. Close protected views and clear session-only credentials to release the gate.

## Returning after sleep

When Android releases memory, the visible comic reloads at its current page. A private session requires unlocking first. If loading fails, controls return so you can navigate or close.
