# Mobile PDF Reader

Open the PDF's **⋯** menu and choose **Duplicate as .rmdoc to annotate** to
create and open an editable notebook beside it. The notebook has the same base
name and embeds the original PDF as page backgrounds; the PDF stays unchanged.
An existing `.rmdoc` shows an error and is preserved. The folder must allow new
files; remote read-only locations cannot create a sibling notebook. Conversion
supports up to 1,000 pages within the notebook archive limits.

Open a `.pdf` from local files, a remote file browser, or an unlocked LocalCrypt
copy. The PDF opens directly in a document session without importing into Books.

Swipe **up** for the next page and **down** for the previous page. You can also
use the previous/next buttons. Open **Pages & search** to enter a page number in the **Page** field and tap
**Go** or submit the field. Page numbers start at 1; invalid values show an error
and keep the displayed page. The first and last pages stop navigation at the
ends of the document.

On iOS the filename is centered in the native title bar. The magnifying-glass
button opens **Pages and search**; **•••** holds the remaining PDF actions.
Previous/Next and a vertical page slider sit beside the reading pane. Progress
runs from top to bottom; drag and release the round thumb to jump to a page.
When two pages fit side by side at full reading height, the reader shows both
and Previous/Next turns by a spread. Resizing keeps the selected page visible. Fullscreen hides the
title and controls. The PDF reader does not show EPUB chapter or speech actions.

PDFs are read-only, limited to 32 MiB and 10,000 pages. Pages are fitted to the
reading pane and rasterized on demand. **× (Close document)** closes the reader
and returns to its originating folder or screen; Android Back does the same
after dismissing open search/tools. Reopening resumes the page during the app
session. Remembered provider positions clear when private readers are locked
or the app restarts.
Decrypted bytes and page images stay in memory and clear on close; remote and
LocalCrypt sessions also retire when credentials change. Password-protected and
damaged PDFs cannot be opened. PDF password entry and PDF annotation editing
are not supported.

PDFs open fullscreen. Tap the PDF page to restore the controls; tap it again to hide them.
Fullscreen fits the whole page to the largest size the screen allows while
keeping its aspect ratio, for both portrait and landscape pages. Space remains
above/below or beside the page only when its proportions differ from the screen.
**Reading mode** in the reader actions also enters fullscreen. Swiping up/down
changes pages in both modes at fit size. In fullscreen, hold the page for about
400 ms to show the shared comic/PDF magnifying bubble, drag to move it, and
release to dismiss it. Keep holding the page and tap **−** at the bottom left or **+** at the bottom right
with another finger. The compact buttons sit slightly outside the bubble’s corners,
with no zoom percentage over the page. The shared zoom levels are
**150%, 170%, 190%, 210%, 230%, 250%**, starting at **190%**. Each change saves
immediately for comics and PDFs, including after restarting. The same setting
appears in **Settings → Books & Comics → Comic & PDF magnifier zoom**.
Holding the page or tapping the magnifier buttons does not turn pages or toggle controls.
Pinch to zoom and pan; return to fit size to swipe between pages.
Pages & search starts collapsed.

## Document contents

Open **Pages & search → Document contents** to show embedded PDF bookmarks.
Tap a title to jump to its page. Use the chevron separately to expand or collapse
nested sections. The rows share EPUB and documentation navigation styling in
light and dark mode. PDFs without embedded contents show an explanation; page
numbers and search remain available. Contents are read in memory and clear when
the document session closes.

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

## Background beside side controls

When iOS uses vertical side controls, the current page can supply a decorative
background beneath them. The fitted document stays inside the unobstructed
reading area, so page text is not hidden by a toolbar. Fullscreen keeps its
existing edge-to-edge canvas. Reduce Transparency disables the decorative
extension; private-reader conceal and suspension release its image.

## Page-turn motion

Page changes use a short slide. **High Contrast / E Ink** disables page-turn
motion on mobile. System reduced-motion preferences are respected.

## External display

PDFs use the same picture-only TV output as comics. Connect an external display
or use the system's screen sharing controls; the current PDF page or spread is
shown without the app's controls. Output clears when you leave the reader or the
app becomes inactive. Protected-session gates also blank the output, including
while another protected document is retained in the app.
