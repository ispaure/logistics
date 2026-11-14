# EPUB reader and metadata development

Books shares EPUB parsing across desktop, Android and iOS. Books & Comics enables the two reader engines under their existing IDs. See the [desktop guide](../user/user.md), [mobile guide](../user_mobile/user_mobile.md) and [Comics development guide](../../comics/development/development.md).

## Try a chapter error message change

On desktop, open a disposable EPUB in **File Browser → Read EPUB…** and use its contents sidebar. In `Python/features/books/ui/reader.py:BooksPage._show_chapter()`, prefix the read error with “Could not open chapter.” Keep the previous-chapter restoration. Update `test_failed_chapter_navigation_keeps_visible_and_saved_location` and run from the configured checkout root:

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_books_reader.py
```

The injected error should show the new message and preserve the visible chapter and saved location until a successful retry.

## Format, rendering and navigation

| Change | Owner and contract |
| --- | --- |
| Archive loading | `epub.py:EPUBBook` validates paths, manifest, spine, EPUB 2 NCX and EPUB 3 navigation. Limits are 512 MiB expanded, 20,000 entries and 32 MiB per resource. Requires supported XHTML chapters. |
| Chapter content | `xhtml.py`, desktop `ui/content.py` and `mobile/content.py` resolve entities offline and render inert XHTML with bounded local resources. Keep scripts and external access disabled. |
| Progress | Desktop `ui/text_view.py` and mobile `mobile/pagination.py` preserve UTF-16 anchors through reflow. Desktop falls back to legacy proportions. Invalidate screen-page counts on reflow. See [reader state](../../../development/architecture/reader-state.md). |
| Mobile view | `mobile/presentation.py:ChapterBridge` accepts its native blank bootstrap and rejects stale callbacks and external navigation. Boundary turns wait for position writes. Columns preserve the passage through delayed loads and geometry changes. Paired pages honor physical folds. Follow the [publication boundary](../../../development/architecture/mobile-runtime.md#reader-publication-boundary) and update `mobile_sources.json` for new imports. |
| Speech | `ui/speech.py` and `mobile/speech_view.py` adapt commonUtils. Natural completion can advance with a fresh provider grant. Stop, failure and stale callbacks cannot advance. See [audio playback](../../../development/architecture/audio-playback.md). |

For format changes, run `python3 dev.py test desktop --exact-file Python/tests/readers/test_books_epub.py` for EPUB 2/3 fixtures, resource limits and rewrite failures. Mobile load-policy checks use `mobile_build/tests/reading/test_epub_load_policy.py`. Native layout, folds and speech require platform checks.

## Metadata publication

`ui/metadata_actions.py` dispatches mixed EPUB and CBZ selections. `mutations.py` validates the rewritten EPUB and preserves unknown fields and retained IDs. `metadata.py` stages beside the resolved source and replaces atomically after validating its revision and the backup's digest and identity. On conflict reopen the current book. Failed cleanup preserves a replacement with a different identity. Signed books may need signing again.

## Find the mobile Books & Comics panel

`Python/mobile/reader_sessions.py` and `reader_ui.py` route to `features/books/mobile/library/catalog_panel.py`. Refresh and Import live in the native toolbar on iOS and the header on Android. Folder rows open Workspaces. `library/index.py` indexes ordinary imports and excludes protected metadata. `test_library_catalog.py` checks discovery and activation.

## Imported metadata publication

`Python/mobile/library_edits.py` replaces the managed UUID copy after revision and checksum validation. A bounded journal recovers matching before/after digests on open and stays available on conflict. Check cancellation before each file enters publication. Provider adapters own their transactions and credentials.
