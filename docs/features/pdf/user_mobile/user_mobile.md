# Mobile PDF Reader

Open the PDF's **⋯** menu and choose **Duplicate as .rmdoc to annotate** to
create and open an editable notebook beside it. The notebook has the same base
name and embeds the original PDF as page backgrounds; the PDF stays unchanged.
An existing `.rmdoc` shows an error and is preserved. The folder must allow new
files; remote read-only locations cannot create a sibling notebook. Conversion
supports up to 1,000 pages within the notebook archive limits.

Open a `.pdf` from local files, a remote file browser, or an unlocked LocalCrypt
copy. The PDF opens directly in a document session without importing into Books.

Drag up or down to scroll through the PDF. You can pause at the gap between
pages or reverse direction. The page indicator follows your position. Use
the previous/next buttons to jump by one page. Open **Pages & search**, enter a
number in the **Page** field and tap **Go** or submit the field. Page numbers start at 1; invalid values show an error
and keep the displayed page. The first and last pages stop navigation at the
ends of the document.

On iOS the filename is centered in the native title bar. The magnifying-glass
button opens **Pages and search**; **•••** holds the remaining PDF actions.
Previous/Next and a vertical page slider sit beside the reading pane. Progress
runs from top to bottom; drag and release the round thumb to jump to a page.
Pages form one vertical column, and resizing keeps the reading position.
Fullscreen hides the title and controls. The PDF reader does not show EPUB chapter or speech actions.

PDFs are read-only, limited to 32 MiB and 10,000 pages. Pages are fitted to the
reading pane and rasterized on demand. **× (Close document)** closes the reader
and returns to its originating folder or screen; Android Back does the same
after dismissing open search and tools. Reopening can resume the saved page,
scroll position and zoom. Credential-backed remote and LocalCrypt positions can
persist encrypted with the owning credential ZIP password. Unlock that
credential again to restore them. Passwordless private sessions retain
positions only in memory. Locking retires the active reader, rather than deleting
its encrypted checkpoint. See [reader state and history clearing](../../../development/architecture/reader-state.md)
for password migration and clearing behavior.
Decrypted bytes and page images stay in memory and clear on close; remote and
LocalCrypt sessions also retire when credentials change. Password-protected and
damaged PDFs cannot be opened. PDF password entry and editing annotations directly in the original PDF
are not supported. Use the duplicate-to-notebook action for editable ink.

PDFs open fullscreen. Tap the PDF page to restore the controls; tap it again to hide them.
Fullscreen fits each page to the available reading area, retaining its aspect
ratio. **Reading mode** in the reader actions also enters fullscreen. In
fullscreen, hold the page for about 400 ms to show the magnifier, drag to move
it, and release to dismiss it. Keep holding the page and tap **+** or **−** on
the magnifier with another finger. Zoom ranges from **150% to 300%** in 10 percentage point steps, starting at **190%**. Each change saves
immediately for comics and PDFs, including after restarting. The same setting
appears in **Settings → Books & Comics → Comic & PDF magnifier zoom**.
Holding the page or tapping the magnifier buttons does not turn pages or toggle controls.
Pinch to zoom. You can pan a magnified page and keep scrolling into adjacent pages.
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
ignores case, treats repeated whitespace as a single space, and searches literal
text across the whole document. Queries are limited to 256 characters; regular
expressions are not supported. Next match and Previous match wrap
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

Explicit page jumps use a short slide. **High Contrast / E Ink** disables page-turn
motion on mobile. System reduced-motion preferences are respected.

## External display

PDFs use the same picture-only TV output as comics. Connect an external display
or use the system's screen sharing controls; the current PDF page is
shown without the app's controls. On iOS, ordinary app navigation mirrors
before you open the reader and after you leave it. The dedicated picture clears
when the app becomes inactive. Protected-session gates blank the output,
including while another protected document is retained in the app.


## Internal page links

Tap an internal PDF link with a finger to open its destination page. Swipes, pinches and holds keep their existing gestures. **Undo page jump** appears below the page for three seconds; tap it to return.
