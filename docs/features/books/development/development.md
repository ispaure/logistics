# EPUB reader and metadata development

Books reads EPUBs and edits their metadata on desktop. The Android and iOS
readers share the EPUB parser and location model with desktop. The Books &
Comics setting enables both readers under the existing `books` and `comics`
runtime IDs. Each format has its own engine and settings files. Calibre is
separate. See the [desktop guide](../user/user.md), [mobile guide](../user_mobile/user_mobile.md)
and [Comics development guide](../../comics/development/development.md).

## Try a chapter error message change

On desktop, open a disposable EPUB with at least two chapters in **File Browser**.
Double-click it or choose **Read EPUB…**, then select a chapter in the contents
sidebar. `Python/features/books/contributions.py:register()` routes both
browser actions to `BooksController.open()` in `ui/controller.py`. **New /
Open Document → EPUB Reader** reaches the same reader through
`services/documents/ui/readers.py:choose_reader_document()`.

In `Python/features/books/ui/reader.py`, try prefixing the error shown by
`BooksPage._show_chapter()` with “Could not open chapter.” Keep the restoration
of the previous chapter index. Update the status assertion in
`test_failed_chapter_navigation_keeps_visible_and_saved_location`. That test
generates a book and injects a read error, so you can check the change without
damaging an archive. From the repository root with the desktop environment
installed, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_books_reader.py
```

Expect the file to pass. The regression checks that contents, links, page
turns, the progress track and bookmarks keep the old chapter and saved
location when a read fails, then open the intended chapter on retry.

## Change EPUB loading or metadata

- `epub.py:EPUBBook` validates the ZIP, reads the package manifest and spine
  (reading order), and resolves EPUB 3 navigation or EPUB 2 NCX contents.
  It bounds the uncompressed archive to 512 MiB and 20,000 entries, with
  32 MiB per resource read. Archive-relative paths must stay inside the
  archive. The spine needs supported XHTML chapters. DRM-encrypted chapters
  and SVG-only fixed-layout books are unsupported. The optional provider uses
  `open(path)` and `version(path)` for virtual reads. Provider-backed books use
  the provider publication path for edits.
- `xhtml.py` resolves named entities offline. Desktop `ui/content.py` and
  `ui/text_view.py` convert inert XHTML and serve bounded archive-local
  images through the Qt resource hook. Mobile `mobile/content.py` sanitizes
  HTML and provides text for the fallback reader. Keep script, network and
  filesystem access outside these document renderers. `ui/preview.py` resolves
  covers from EPUB 3 manifest properties, EPUB 2 metadata or the cover guide
  and bounds image decoding.
- **Edit metadata…** goes through `ui/metadata_actions.py` to the appropriate
  EPUB or comic editor, including mixed selections. The browser uses
  `SelectionAction.shared_key` to show one command. `ui/metadata_window.py`
  hosts the reusable `ui/metadata_editor.py` form independently of the reader.
  Open and save use `BookTask` workers. Close waits for their retirement.

`metadata.py` owns desktop backup and replacement. `mutations.py` owns the
archive rewrite and format validation. Writes preserve unknown metadata,
comments, identifiers and retained node IDs. Changed values clear obsolete
`file-as` refinements and update EPUB 3's `dcterms:modified`. Namespace prefix
spelling and formatting can change. Signed books may need signing again.
When opening a local symlink, edit the resolved book and preserve the link.

Stage beside the EPUB, keep the source permissions and publish by atomic
replacement. A backup must match the original's SHA-256 and still have the
identity of the exclusively created backup before publication. On failure,
clean up the staged archive and remove a failed backup only if it still has
that identity. Preserve any file or link that replaced the backup. Identity,
size and nanosecond timestamp checks detect changes by other processes
optimistically. On conflict, reopen the current book before retrying.
Cancellation before publication leaves the source intact.

Run the parser and metadata regressions from the repository root. Expect the
generated EPUB 2 and 3 fixtures, resource limits, backup failure cases and
round trips to pass.

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_books_epub.py
```

The format and resource contracts follow the [EPUB specification](https://www.w3.org/TR/epub-33/)
and [Qt's rich-text resource hooks](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QTextBrowser.html).

## Change reading controls, appearance or progress

On desktop, `ui/reader_controls.py:build_controls(page)` composes the toolbar,
contents, bookmarks, search and Aa appearance controls. `BooksPage` owns
callbacks and navigation. `ui/text_view.py` paginates by screen height and
uses UTF-16 text offsets within a spine item for restoration. Legacy
proportional positions remain a fallback. Resize, search and chapter links
resolve to a page in the current layout. Manual turns clear pending resize
anchors. The reader keeps the Qt application font for Automatic to preserve
valid font metrics on macOS.

Appearance changes write sparse personal overrides to shared Styling for
reading font family/size and to Reader for the other fields. Markdown shares
the Reading font. Readers compare effective appearance before reimporting a
chapter. Mobile `mobile/typography.py` owns validated offline typography and
`themes.py` supplies colors to both hosts. Mobile Appearance opens the EPUB
Settings page with a Back target to the originating reader. The host pauses
turns for that visit and restores the current passage, reloading the chapter
when appearance changed or the native bridge was lost.

`preferences.py` saves desktop position and bookmarks by a hash of the
canonical path. Reads and writes are bounded to 128 KiB. An oversized save
keeps the last checkpoint. The thumbnail worker seeds the spine for legacy
chapter lookups, so badge drawing needs only bounded state. See the shared
[reader state contract](../../../development/reader-state.md) for provider
checkpoints, credential storage and clearing behavior.

`locations.py:LayoutPages` maps whole-book screen pages to chapters and local
pages. The progress track is disabled while counts are pending. Desktop
`ui/progress.py:BookProgress` measures hidden chapters with the live font and
geometry and reports the last visible page divided by the total. Mobile
`mobile/pagination.py:MobilePagination` reports text progress from the chapter
offset and sanitized UTF-16 chapter lengths. It measures screen-page counts
separately using hidden WebView columns with the live geometry, fonts and
images. A reflow invalidates page counts. The native text fallback can report
text progress without screen-page counts. Keep count tasks and document
references scoped to the reader.

## Change mobile chapter presentation

`Python/services/mobile_features.py` maps EPUBs to Books & Comics.
`mobile/reader_controller.py` prepares imported chapters and owns boundary
navigation, pending position writes and width observation.
`mobile/provider_controller.py` owns provider tools and width-task state.
`mobile/provider_reader.py` reuses the same bridge with the nonpersistent
WebView in `mobile/private_view.py`. That view clears content on disposal.
The host owns provider grants, storage and session lifetimes. Use the
[shared publication boundary](../../../development/mobile-runtime.md#reader-publication-boundary)
when mounting a replacement chapter. Add newly imported portable/mobile
modules to `Python/features/books/mobile_sources.json`.

`mobile/presentation.py:ChapterBridge` controls the trusted sanitized chapter.
Only the native `about:blank` bootstrap may load before chapter completion.
Stale callbacks and external navigation are rejected. Boundary turns wait for
pending location writes. Reopening an imported book reloads its current
chapter and restores the passage if the retained native WebView lost its
content. `mobile/navigation.py` supplies nested contents and chapter labels.

CSS columns reflow around a stable text anchor. Landscape viewports (at least
700 × 480 logical pixels) and active vertical folds support paired columns.
The smaller physical half bounds both page widths and the reserved crease
defines the gap. Turns and seeks snap to the spread, including its odd final
page. An active speech word has priority over selection during reflow. Delayed
images and repeat load-completion callbacks keep the current passage.
The host supplies view-local fold geometry and motion policy, including
High Contrast / E Ink. The chapter drawer retains its detail view and dismisses
on route changes, selection or retirement.

For the load policy, run this host check. Expect bootstrap, stale navigation
and turn-suppression cases to pass. Browser column and anchor checks live in
`test_epub_dom.py` and `epub_index_dom.cjs`. Native WebView layout, rotations
and physical folds require the applicable platform checks.

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_epub_load_policy.py
```

## Change read-aloud

Desktop `ui/speech.py` and mobile `mobile/speech_view.py` adapt commonUtils
speech sessions. The mobile host supplies overlays, saved voice and credential
policy through `mobile/speech_host.py`. Start from the visible page or
selection. The separate DOM highlight follows native UTF-16 word ranges
without turning into a user selection. Android can estimate ranges from the
audio-start event when the engine lacks range callbacks. Installed offline
voices are loaded on demand. A missing saved voice falls back to the system
default. A failed iOS engine discovery retries with a fresh session and
cancels pending work on disposal.

A natural completion can advance to the next chapter. Explicit Stop,
selection end, failure and retired callbacks cannot advance. A chapter change
from playback keeps the speed and listening-time budget, waits for the trusted
chapter and checks authorization again. A lock-screen grant can finish the
already loaded chapter. The next provider read requires a fresh grant.
`speech_sequence.py` resolves skip overshoot across chapters. The 15-second
control estimates distance at 180 words per minute adjusted by speed. Skip,
pause and retirement reject old callbacks. The monotonic timer pauses at
expiry and excludes paused time. Hiding the overlay keeps the timer active.
Disposal releases the text, timers and native owner.

`mobile/media_controls.py` arbitrates process-wide playback.
`mobile/media_ios.py` owns the iOS playback audio session and remote commands.
`mobile/media_android.py` and `SpeechMediaService.java` own Android audio
focus, media notification and foreground service. Let every delivered service
start acknowledge foreground startup before retiring it. Stop only the last
acknowledged start ID, so a short passage cannot cancel a pending start before
Android has acknowledged it. If a reused Android build reports missing speech,
check that `mobile_build/cloud_build.py` refreshed the configured Java roots
that supply the shared `SpeechListener`.

For ordinary books, system metadata includes at most 120 characters of the
basename and the listening timer. Protected sessions use generic metadata.
Document text stays in the playback owner. Default session-only playback
requires the foreground. An explicit background-audio preference can retain
the authorized in-memory passage, subject to credential revocation.
See [audio playback](../../../development/audio-playback.md) for host policy.
`test_epub_continuation.py` and `test_speech_overlay.py` exercise lifecycle and
recovery with silent engines. The native speech probe checks the real callbacks
and highlight cleanup. Physical audio and voice availability require devices.

## Find the mobile Books & Comics panel

Open **Books & Comics** on Android or iOS. `Python/mobile/reader_sessions.py`
and `Python/mobile/reader_ui.py` present the library route for the originating
destination. `mobile/library/catalog_panel.py:LibraryCatalogPanel` owns
**Refresh**, **Import…**, configured folder rows and **Open Workspaces**.
iOS mounts the retained Refresh and Import controls in the native toolbar.
Android displays them in the panel header. Selecting a folder opens the
Workspaces browser. A reader opens on its own route.

`mobile/library/catalog.py` coordinates discovery and refresh. The host
reads folder configuration in `Python/mobile/library_ui.py`. The visible
catalogue lists configured folders. `library/index.py` owns the disposable
SQLite index for ordinary imports and `library/metadata.py` owns portable
field mapping. Imported records still serve sessions and suggestions.
Protected providers stay outside that index. Protected import filenames may
remain searchable without loading protected metadata.

Run this host check for configured folder discovery and activation. Expect
the folder row to open its browser. Native toolbar placement and Back
navigation require native validation.

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_library_catalog.py
```

## Imported metadata publication

`Python/mobile/library_edits.py` publishes EPUB and comic metadata edits to
the managed UUID copy, preserving the external source. The host validates the
rewritten archive and checks its revision and checksum before creating a
bounded `.edits` journal. After publication starts, it finishes replacing the
archive and updating its record or leaves the journal for recovery on the next
open. Recovery compares the current digest with the before and after records
and preserves the journal if neither matches. Check cancellation before each
file enters publication. Keep provider-specific transactions and credential
policy in the owning storage adapter.
