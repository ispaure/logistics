# Read and manage comics

Enable **Books & Comics** in Settings.

## Open a library

Select a configured folder in **Workspaces → Open Comics Library…**. Put this in the collection root's `remoteConfig.ini`.

```ini
[LogisticsComics]
libraries = Comics,Mangas,Artbooks
```

Names are immediate child folders. **All** browses the root. Browse other folders through **Debug → Open File Browser…**.

## Read and edit

Double-click a CBZ or choose **File → Open comic…**. Arrow keys, page buttons and wheel turn pages. Hold a key or button to repeat within the comic. **Home/End** jump to either end and **F11** toggles fullscreen. Use **Navigate → Go to page…** (**Ctrl/⌘+G**) or the footer slider. **View → Page layout** offers Automatic, Single or Two pages, respecting manga order. Previous/Next File opens neighboring local CBZs.

## Edit metadata across a collection

Select comics or folders and choose **Books & Comics → Edit metadata…**. Folders include descendants. Change only the fields you want to write. Editing a mixed list replaces it for each comic. Clear a field to remove it. **Apply** writes immediately. **OK** saves and closes.

Page bytes are preserved. Earlier successes remain if a later save fails. Reopen externally changed files and inspect errors before retrying. Keep original copies because these edits have neither Undo nor automatic backup.

## Library suggestions and reading state

Suggestions come from the collection's disposable `LogisticsComicsData/metadata.json` cache, excluding encrypted comics. Refresh to pick up changes. Reopening resumes at the last displayed page. Moving a comic starts a separate history. Disable `remember_position_bool` in **Settings → Books & Comics** to stop saving and restoring progress. See [EPUB reading history](../../books/user/user.md#keep-your-place).

## Compress or convert

Choose **Books & Comics → Compress Comics…** or **Compress CBZ…**. Review recursion and retention options. Verified output replaces successful originals. **Cancel after current comic** preserves completed work. CBR conversion requires a compatible RAR extractor and removes originals after successful conversion. Keep backups.

## Password-protected comics

Unlock with the ZIP password when prompted. Retry in the same prompt after an error. To encrypt plain CBZs in place, configure the nearest applicable `remoteConfig.ini`.

```ini
[LogisticsZIP]
archive_password = your-password
```

Use **Books & Comics → Encrypt unencrypted comics…**. Each plain comic needs a configured password. Compression also needs that password in the INI. The INI stores plaintext and ZIP entry names stay visible. For a separate outer ZIP, use [Archives](../../archives/user/user.md).

## More help

See [Using Logistics](../../../user/user.md) and the [mobile guide](../../../user_mobile/user_mobile.md).

## Compression decisions and collection maintenance

WebP pages are normally retained below 75% of the original size. **Always keep compressed images** bypasses this test and requires disabling preservation of animated or multipage originals. That allows first-frame conversion. Compression can rename pages, flatten folders and remove sidecars. Rebuilt ComicInfo page records lose old per-page bookmarks, DoublePage flags and page types. Batches skip marked compressed comics. There is no collection-wide Undo.

## Mobile development builds

See [Comics mobile workflows](../user_mobile/reading.md#mobile-development-builds).

## Metadata inside LocalCrypt

Choose **Edit comic metadata…** (desktop) or **Edit metadata…** in a private mobile reader. Saves preserve page bytes and inner ZIP passwords and create no plaintext backup. Desktop folder batches scan up to 10,000 entries and report archives that cannot unlock. Push saved edits before pulling if you need them on the remote. Pull can replace local changes. See [mobile LocalCrypt](../../rclone/user_mobile/localcrypt.md#localcrypt-encrypted-offline-reading).

## Native mobile library

See [Comics mobile workflows](../user_mobile/reading.md#native-mobile-library).

## Page-turn motion

A short page slide follows the comic's reading direction.
