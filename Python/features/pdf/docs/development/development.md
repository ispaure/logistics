# PDF Reader implementation

`features.pdf` owns PDF registration, desktop launching and native page rendering.
It declares a PDF file type and a document launcher, with lazy desktop imports.
`mobile_sources.json` is included in the mobile source owners in `Mobile/tools.py`.

`document.PDFDocument` accepts bounded memory bytes or reads at most 32 MiB plus
one byte from a provider stream. It discovers page count, enforces 10,000 pages
on mobile, and renders one page at a time to PNG with a 2048-pixel longest edge.
Desktop rendering uses QtPdf; iOS uses PDFKit; Android uses PdfRenderer with a
duplicated anonymous Linux memory descriptor. No plaintext temporary file is
created. Native renderer objects and descriptors close after each operation.
Invalid and locked PDFs fail with an opening error.

`services.documents.readers.PrivateReader` adapts PDFs to the existing mobile
provider contract. Local PDFCopies, RemoteReaders and LocalCryptCopies all use
this contract. ProviderUI routes PDF pages directly rather than through comic
spread decoding. PDFCanvas owns vertical gestures; page-number conversion is
one-based at the UI boundary and zero-based internally. PrivateSessions retains
transient PDF sessions, excludes their content from recovery, clears native
pixels on suspension, and drops PDF bytes on close or credential revocation.

`mobile.canvas.PDFTools` exposes an optional `on_state_change` callback so the
host can keep its native pages/search icon and accessible name in sync when the
panel opens or closes. The feature does not import host toolbar policy. The host
places this panel above the page canvas and page navigation below it; invalid
numeric jumps retain feedback inside the panel even when filename labels are
detached for the native title bar.

Desktop `ui.reader.PDFWindow` uses QPdfView SinglePage/FitInView and a numeric page
control. Remote and LocalCrypt ResourceChoice sessions load through their provider
in the existing cancellable worker and retain the provider lease until window
destruction. PrivateViewGuard supplies the existing credential revocation policy.

Validation:

- `Python/tests/test_pdf_reader.py`: real PDF rendering, bounds, registration,
  provider reads, desktop page jumps and dragging, and document buffer release.
- `Mobile/tests/test_pdf_reader.py`: Toga dummy UI integration for local, remote
  and offline LocalCrypt reading, numeric navigation, vertical gesture dispatch,
  credential revocation and no plaintext persistence. Native rasterization is
  replaced by a small fixture in these mobile UI tests.

Native PDFKit/PdfRenderer execution and physical-device gestures require device
validation; dummy backend tests do not establish that coverage.

## Text search

`search.py` extracts embedded text with the pinned pure-Python pypdf dependency
from an in-memory BytesIO stream on every platform. It performs literal,
case-insensitive matching after normalizing whitespace. Results contain only
page indices and snippets; the PDF text is not indexed on disk. Search is limited
to 256 query characters, 1,000 matches, 10,000 pages, and 8 MiB of extracted
text. Oversized content streams also stop search with a visible error. Image-only
PDFs require an existing OCR text layer.

The Qt search bar runs work in an executor and polls completion through a Qt
timer; the Toga bar uses asyncio.to_thread. Query changes and close signal
cancellation, checked between pages. Disposed or inactive mobile sessions reject
late results. Closing clears query, snippets and worker input references. A
currently running extraction finishes its current page before cancellation can
release the remaining worker references. Search does not require Android native
text extraction APIs or additional native mobile wheels.

PDF tests cover real embedded text, repeated matches, case handling, no matches,
result limits, next/previous wrapping, desktop navigation, and mobile search over
local, remote and offline LocalCrypt sessions.

## Mobile opening and compact controls

PrivateSessions initializes the cloud/provider controls without presenting them
before opening its first document. This allows local PDFs to open from a cold
Documents session. Page jump and PDF search share a collapsible Pages & search
panel. PDFCanvas specializes the shared ImageCanvas with vertical paging.
Tapping toggles fullscreen; the ReadingFrame hides header/footer/navigation and
enables the shared hold magnifier only while fullscreen.
`logisticsmobile.magnifier.bind` connects PDF and comic canvases to the same
validated `magnifier_zoom` preference. Native lens-button requests save before applying;
failed saves preserve the displayed zoom. Live canvases and Settings selectors
share updates by preference path, including independent app windows. Page replacement keeps
that eligibility, and disposal clears both callbacks and the lens. Swipes at fit
scale work in both modes; pinch/pan and hold/tap arbitration use the same native
backends as comics. Fullscreen removes reader margins and fits the entire page
using the smaller viewport-to-image scale factor, preserving aspect ratio. The
native PDF probe checks actual rendered bounds and centering for portrait and
landscape pages on both platforms, alongside fullscreen gestures and the lens.
`Mobile/native_tests/tests/logisticsmobile/pdf_probe.py` exercises actual platform
rasterization, navigation, search and memory release in an isolated test app.

Native verification on 2026-10-17 passed PDFKit and Android PdfRenderer opening,
rasterization, page jumps, embedded-text search, reading mode and memory release.
Android bitmap background fill explicitly uses Chaquopy jint(-1), preventing the
long color-space overload from raising Invalid ID: 63. Reports and screenshots
are in the root development mobile-evidence/2026-10-17-pdf-search folder.

## Mobile contents hierarchy

`contents.contents` reads embedded bookmark destinations through the existing
pypdf dependency, using memory bytes and zero-based page targets. The traversal
rejects more than 2,000 outline nodes or depth beyond 32. Invalid destinations
are omitted; PDFs without contents return an empty tuple.
`mobile.contents.PDFContents` loads on demand in a worker, checks the owning
session before publishing or navigating, and keeps page jump/search available
when parsing fails. It uses `commonUtils.ui.native.presentation.HierarchyList`;
the host injects colours through `hierarchy_row_style`. `Mobile/tests/test_contents_hierarchy.py`
covers real PDF destinations, disclosure independence and stale-session guards.

## Backend layout

`document.py` retains bounded input and document lifetime. `backends/qt.py`,
`backends/apple.py` and `backends/android.py` own the platform rasterizers;
`limits.py` supplies the shared render edge. Backend toolkit imports stay lazy
inside adapter construction, so a mobile import does not load Qt. Existing public
backend class imports and the document facade remain available.
