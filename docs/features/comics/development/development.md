# Comic reader and archive development

Comics requires Images and shares the Books & Comics enablement with EPUB. See the [desktop guide](../user/user.md), [mobile guide](../user_mobile/user_mobile.md) and [compression contract](compression.md).

## Try a compression threshold change

On desktop, choose **File Browser → Compress Comics…** for a fresh disposable CBZ. In `Python/features/comics/cbz.py`, raise `cbz_img_min_allowed_compression_percentage` from 75 to 76 and update `test_threshold_is_strict_and_override_is_preserved`. From the checkout root:

```sh
python3 dev.py test desktop --exact-file Python/tests/comics/test_comics.py
```

For a 100-byte source page, expect 75-byte WebP to win, 76 bytes to retain the original, and always-keep to accept 76 bytes. Batch skips root `CompressionLog.txt` markers.

## Find the desktop edit point

- `ui_contributions.py` routes activation to `ui/reader_opening.py:open_reader` (retained Qt windows), compression to `ui/dialogs.py:CompressCbzDialog`, and folder collections to `ui/library.py`. `[LogisticsComics] libraries` orders immediate child tabs. The catalog stays rooted at the collection.
- `comicinfo.py` and `ui/metadata_editor.py` patch only explicit fields, preserving unknown XML, image bytes and page records. Numbers may include suffixes. Batch preflight enforces 4 MiB ComicInfo, rejects links and atomically replaces each archive. Retry against refreshed baselines. `catalog.py` rebuilds invalid suggestion caches and excludes protected metadata. See the [ComicRack compression policy](compression.md#comicrack-compatibility-rebuilding-page-records).
- `conversion.py` uses patool's external RAR extractor. Verify the new CBZ before deleting the source. Folder organization copies before deleting and stops on failure.

## Password-protected CBZs

Readers prompt when needed and cache unlocks in memory. Batch compression uses the configured password. Rewrites require uniform encryption with one valid password and upgrade ZipCrypto to AES-256. Member names remain visible. **Encrypt unencrypted comics…** checks ancestor configuration before processing and skips encrypted inputs. See the [Archives password policy](../../archives/development/development.md#password-policy-and-the-two-creation-flows).

## Mobile navigation and output

`pages.py` sorts decimal runs naturally. `reading_state.py` restores by member name then clamped index. `mobile/navigation.py:ComicNavigation` prepares page, spread and half before commit. Failed composition or sibling opening preserves the current view. Follow the [publication contract](../../../development/architecture/mobile-runtime.md#reader-publication-boundary).

Wide pages default to split in portrait, with 8% overlap and manga traversal. Older checkpoints start at the first half. The RAM-only spread caps at 16 megapixels and 8192 per side. Preserve the selected page through hinge relayout. Run `python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_comic_split.py`. For sibling traversal and corrupt-target recovery, see `test_comic_file_navigation.py`.

`mobile/private_batch.py` keeps bounded private edit baselines in memory and wipes them on revocation. See [managed-copy publication](../../books/development/development.md#imported-metadata-publication). Add new mobile imports to `mobile_sources.json`.

`Python/mobile/external_display.py` blanks on privacy gates and temporarily chooses paired whole pages. Disconnect restores saved layout. iOS 27 registers the current host's `UISceneAccessory`. Android uses Presentation. Check `test_external_display.py` and `test_comic_sharing.py`. Wireless receiver page-turn synchronization remains open.
