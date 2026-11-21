# Comic reader and archive development

The comic reader opens image pages from an archive and tracks the reader's
place by member name and page index. The desktop archive tools also compress
pages, edit ComicInfo and convert CBR files. These operations build and
validate a replacement archive before publishing it.

Comics requires Images and shares the Books & Comics switch with EPUB. For
reader controls see the [desktop guide](../user/user.md) or
[mobile guide](../user_mobile/user_mobile.md).

## Check a compression decision

On desktop, open **Compress Comics…** from File Browser with a disposable
CBZ. The dialog sends its WebP options to the compression workflow in
`Python/features/comics/cbz.py`. By default a WebP candidate must be smaller
than 75% of the source page to replace it. The regression supplies a
100-byte source page and checks that a 74-byte WebP replaces it. With a
75-byte WebP the original stays in the archive. The test also exercises the
always-keep override.
Use the [compression contract](compression.md) for archive verification,
batch handling of `CompressionLog.txt` and rebuilding ComicRack page records.

```sh
python3 dev.py test desktop --exact-file Python/tests/comics/test_comics.py
```

## Find the desktop edit point

- `ui_contributions.py` routes activation to `ui/reader_opening.py:open_reader` (retained Qt windows), compression to `ui/dialogs.py:CompressCbzDialog`, and folder collections to `ui/library.py`. `[LogisticsComics] libraries` orders immediate child tabs. The catalog stays rooted at the collection.
- `comicinfo.py` and `ui/metadata_editor.py` patch only explicit fields, preserving unknown XML, image bytes and page records. Numbers may include suffixes. Batch preflight enforces 4 MiB ComicInfo, rejects links and atomically replaces each archive. Retry against refreshed baselines. `catalog.py` rebuilds invalid suggestion caches and excludes protected metadata. See the [ComicRack compression policy](compression.md#comicrack-compatibility-rebuilding-page-records).
- `conversion.py` uses patool's external RAR extractor. Verify the new CBZ before deleting the source. Folder organization copies before deleting and stops on failure.

## Password-protected CBZs

Readers prompt when needed and cache unlocks in memory. Batch compression uses the configured password. Rewrites require uniform encryption with one valid password and upgrade ZipCrypto to AES-256. Member names remain visible. **Encrypt unencrypted comics…** checks ancestor configuration before processing and skips encrypted inputs. See the [Archives password policy](../../archives/development/development.md#password-policy-and-the-two-creation-flows).

## Mobile navigation and output

`pages.py` sorts decimal runs naturally. `reading_state.py` restores by member name then clamped index. `mobile/navigation.py:ComicNavigation` prepares page, spread and half before commit. Failed composition or sibling opening preserves the current view. Follow the [publication contract](../../../development/architecture/mobile-runtime.md#reader-publication-boundary).

Wide pages default to split in portrait, with 8% overlap and manga traversal. Older checkpoints start at the first half. The RAM-only spread caps at 16 megapixels and 8192 per side. Preserve the selected page through hinge relayout. Run `python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_comic_split.py`. For sibling traversal and corrupt-target recovery, see `test_comic_file_navigation.py`.

`mobile/private_batch.py` keeps bounded private edit baselines in memory and wipes them on revocation. See [managed-copy publication](../../../development/architecture/document-storage.md#imported-metadata-publication). Add new mobile imports to `mobile_sources.json`.

`Python/mobile/external_display.py` blanks on privacy gates and temporarily chooses paired whole pages. Disconnect restores saved layout. iOS 27 registers the current host's `UISceneAccessory`. Android uses Presentation. Check `test_external_display.py` and `test_comic_sharing.py`. Wireless receiver page-turn synchronization remains open.

`mobile/presentation.py` builds comic pages and spreads with the injected native zoom canvas. `ReaderChrome` owns controls and immersive presentation. Fit-size gates page gestures; fullscreen enables the hold magnifier for imported/provider comics and spreads. Android fullscreen releases hidden rail width. Auto spread uses measured landscape geometry, manga direction and standalone landscape/DoublePage metadata. Use `comic_viewport_probe.py` and `comic_spread_probe.py` for focused QA, and verify native touch and fullscreen restoration.

Provider-backed Appearance keeps the current spread and its gesture handlers
while the form is open. Back discards unapplied changes. Applying a layout
refreshes the selected page. If memory pressure releases the page, returning to
the reader reloads it once the session is available and unlocked.
Run the focused Manager probe with disposable files and a disposable device.
Use a fresh output directory and repeat with `android` for the shared route.

```sh
python -m mobile_build.validation.document_storage_tools ios --probe reader-appearance \
  --output tmp/test-results/RUN_ID/ios
```

The probe covers changed settings, unchanged Apply, Back, page input, and
reopen for ordinary local and LocalCrypt comics. It also checks the session-only
lock during Appearance, EPUB Settings return, and PDF return from its document
actions.
