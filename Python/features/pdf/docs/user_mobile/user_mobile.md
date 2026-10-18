# Mobile PDF Reader

Open a `.pdf` from local files, a remote file browser, or an unlocked LocalCrypt
copy. The PDF opens directly in a document session without importing into Books.

Swipe **up** for the next page and **down** for the previous page. You can also
use the previous/next buttons. Open **Pages & search** to enter a page number in the **Page** field and tap
**Go** or submit the field. Page numbers start at 1; invalid values show an error
and keep the displayed page. The first and last pages stop navigation at the
ends of the document.

PDFs are read-only, limited to 32 MiB and 10,000 pages. Pages are fitted to the
reading pane and rasterized on demand. Reading positions stay in this session.
Decrypted bytes and page images stay in memory and clear on close; remote and
LocalCrypt sessions also retire when credentials change. Password-protected and
damaged PDFs cannot be opened. PDF password entry and PDF annotation editing
are not supported.

Tap the PDF page to enter fullscreen; tap it again to restore the controls.
Fullscreen fits the whole page to the largest size the screen allows while
keeping its aspect ratio, for both portrait and landscape pages. Space remains
above/below or beside the page only when its proportions differ from the screen.
**Reading mode** in the reader actions also enters fullscreen. Swiping up/down
changes pages in both modes at fit size. In fullscreen, hold the page for about
400 ms to show the shared comic/PDF magnifying bubble, drag to move it, and
release to dismiss it. Keep holding the page and tap **−** at the upper left or **+** at the upper right
with another finger. The buttons sit slightly outside the bubble’s corners. The shared zoom levels are
**150%, 170%, 190%, 210%, 230%, 250%**, starting at **190%**. Each change saves
immediately for comics and PDFs, including after restarting. The same setting
appears in **Settings → Books & Comics → Comic & PDF magnifier zoom**.
Holding the page or tapping the magnifier buttons does not turn pages or toggle controls.
Pinch to zoom and pan; return to fit size to swipe between pages.
Pages & search starts collapsed.

## Search

Open **Pages & search**. Enter text in **Find in PDF** and submit it or choose **Next match**. Search
ignores case and covers the whole document. Next match and Previous match wrap
around the results and jump to the matching page. A result count and text snippet
identify each match, including multiple matches on the same page. Clear the
query to clear results.

Search works with local, remote and LocalCrypt PDFs and creates no persistent
text index. Search text and results clear when the reader closes or its private
session is revoked. Scanned pages require an existing searchable text layer;
OCR is not included. Results are capped at 1,000 (shown with a `+` when there are
more); documents with more than 8 MiB of extracted text report a search limit.
