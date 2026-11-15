# EPUB reader and metadata development

The EPUB reader turns a publication's spine into a sequence of readable
chapters and uses its navigation entries to find passages within them.
Desktop, Android and iOS share the EPUB parser. Their reader views lay out
the text and keep a reading location across page turns and changes in layout.
The Books & Comics switch also enables the
[comic reader](../../comics/development/development.md), which navigates image
pages. See the [desktop guide](../user/user.md) and
[mobile guide](../user_mobile/user_mobile.md) for reader controls.

## Follow a chapter turn

Open a sample EPUB with **Read EPUB…** from the desktop File Browser and
pick a chapter in Contents. That selection and a turn across the end of a
chapter both reach `BooksPage._show_chapter()` in
`Python/features/books/ui/reader.py`. The method restores the previous
chapter index on a read error so that the visible text and saved location
still refer to the same chapter. The reader test injects a failed
chapter read through Contents and other navigation controls, then verifies
that a retry reaches the intended chapter.

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_books_reader.py
```

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

See [imported metadata publication](../../../development/architecture/document-storage.md#imported-metadata-publication)
for mobile EPUB and CBZ copies.
