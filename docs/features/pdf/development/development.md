# PDF reader development

The PDF feature opens and renders PDFs on desktop, Android and iOS. It owns
page links, text search and the command to duplicate a PDF as an editable
notebook. The [desktop](../user/user.md) and [mobile](../user_mobile/user_mobile.md)
guides describe the reading controls.

## Try changing the page link undo duration

On desktop, open a disposable PDF with an internal page link from **File
Browser** and click the link. `Python/features/pdf/__init__.py:register()`
declares PDF activation, which calls `ui/reader.py:open_pdf()`. The **PDF
Reader** option in **New / Open Document** uses
`services/documents/ui/readers.py:choose_reader_document()`.

Try changing the timer from 3000 to 5000 milliseconds in
`Python/features/pdf/ui/reader.py:PDFWindow.offer_link_return()`. Update the
timer assertion in `test_desktop_real_plain_click_and_undo`. The test creates
its own linked PDF, so you can verify the change without a personal document.
From the repository root with the desktop environment installed, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_pdf_links.py
```

Expect a link click to move from page 1 to page 3. **Undo page jump** should
return to page 1 and clear the offer. The timer should report 5000 milliseconds
with the example edit. An explicit page jump clears the pending link return.

## Open or render a PDF

`document.py:PDFDocument` owns bounded input and lifetime. It accepts memory
bytes or reads at most 32 MiB plus one byte from a stream. It rejects
unsupported, locked or oversized input and enforces a 10,000-page limit.
`limits.py` supplies the 2048-pixel longest edge for raster output.
`backends/qt.py`, `backends/apple.py` and `backends/android.py` own lazy
QtPdf, PDFKit and PdfRenderer adapters. Android uses an anonymous memory
descriptor. If construction fails, close either the acquired renderer or
the descriptor that was never transferred. Use Chaquopy `jint(-1)` for the
bitmap's white fill to select the integer color overload.

The desktop chooser passes local paths to `open_pdf()`. For remote and
LocalCrypt choices, its cancellable worker reads through the provider and
keeps its lease until the window closes. `PrivateViewGuard` applies
credential revocation. On mobile, `services.documents.readers.PrivateReader`
adapts local, remote and LocalCrypt sources. The host excludes private PDF
contents from recovery, clears pixels on suspension and releases bytes on
close or credential revocation. Update `Python/features/pdf/mobile_sources.json`
for new portable or mobile imports.

## Continuous pages

Desktop `ui/reader.py:PDFWindow` and Notes Library preview use
`ui/continuous.py:ContinuousPDFView`, a memory-backed Qt multi-page view.
The viewport renders visible pages and bounds cached images. Wheel and
trackpad input update the visible page, while the numeric control and
toolbar issue explicit jumps. The desktop checkpoint stores the page and
vertical scroll fraction.

Mobile `mobile/continuous.py:PDFScroll` uses native PDF page dimensions
to lay out a memory-backed WebView before rasterizing. A single asynchronous
worker renders the viewport pages and a neighbor on either side. Publication
drops distant DOM nodes and pixels and rejects stale work on a jump or
retirement. A scroll observation updates controls without seeking or
recording a jump. The mobile checkpoint restores page, within-page offset
and zoom, with a fallback for older page-only records. See the
[reader state contract](../../../development/reader-state.md).

Mobile paged presentation lives in `mobile/canvas.py`. `PDFNavigation`
prepares up to two pages before committing their indices. `PDFCanvas`
handles vertical gestures. Page numbers shown to the reader start at one,
while navigation indices start at zero. A number submitted during refresh
waits for idle and is discarded after navigation, retirement or a reader
switch. A refresh of the same page retains a number still being typed.
The shared ReadingFrame handles fullscreen chrome and hold magnification.
`mobile.magnifier.bind` saves a requested zoom before applying it and
disposal clears callbacks and the lens.

Run these host checks for desktop loading/navigation and mobile viewport
invalidation. The mobile file uses fixture rendering. The managed native
`pdf_probe.py` exercises PDFKit and PdfRenderer, viewport bounds and mixed
page sizes. Physical gestures still require devices.

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_pdf_reader.py
python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_pdf_scroll.py
```

## Internal page links and contents

`links.py:page_links()` reads up to 2,000 annotations per rendered page.
It resolves explicit and named internal destinations and converts
crop-relative rectangles through page rotation to normalized display
coordinates. Mobile places link targets over the rendered page. Desktop
uses Qt's internal link handling. Both offer a three-second page return.

`contents.py:contents()` resolves embedded outline destinations from
memory with pypdf and returns zero-based page targets. It omits invalid
destinations and rejects more than 2,000 nodes or depth 32. `mobile/contents.py`
loads the outline on demand and checks session identity before publication
or navigation. Parsing failure leaves page jump and search available.
`test_contents_hierarchy.py` covers real destinations and stale sessions.

## Text search

`search.py` uses pypdf over in-memory bytes for literal case-insensitive
matches after whitespace normalization. Results hold page indices and
snippets. Image-only pages require an existing OCR layer. Limits are
256 query characters, 1,000 matches, 10,000 pages and 8 MiB extracted text.
Oversized content streams stop the search with visible feedback.

`search_controller.py` owns query revision, request identity, results,
navigation wrap and cancellation. Qt `ui/search.py` polls an executor.
Toga `mobile/search.py` awaits a worker and checks session identity before
showing results or navigating. Query edits clear results immediately and
signal cancellation. Keep the busy owner until extraction retires. Mobile
uses `services.worker_retirement.drain_worker()` to wait through repeated
cancellation. A worker-start failure leaves retry available. Disposal
clears query, snippets and worker input references when their owners
retire. Stale results and navigation errors cannot update a newer query.

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_pdf_search_controller.py
```

Expect the state tests to pass, including wrap, retry, cancelled queries
and disposal. The reader test also searches embedded text in a generated PDF.

## Duplicate for annotation

`annotation.py:duplicate_pdf()` reads a bounded, revision-checked
`DocumentResource`, embeds the original bytes in a sibling `.rmdoc` and
maps native page IDs to PDF pages. It publishes without replacing an
existing name and checks collisions again at provider publication.
Private providers retain their encryption and read-only providers reject
creation. Notebooks owns editable ink and the lazily rendered PDF
background. `Python/tests/notebooks/test_pdf_annotation.py` exercises
round trips, collision races and desktop menu dispatch. The managed
`pdf-annotation` probe uses a disposable app and synthetic PDF for native
menu, ink and reopening checks. Synthetic pen input measures the app path
without establishing physical Pencil latency.
