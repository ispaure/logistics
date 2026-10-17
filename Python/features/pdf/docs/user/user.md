# PDF Reader

Open a local `.pdf` from the file browser, or choose **PDF Reader** from the
launch chooser. Its Open picker also supports unlocked LocalCrypt locations.
Remote and LocalCrypt browsers open PDFs through the same reader.

Use **Page** to enter the current page number (starting at 1), or use Previous
page and Next page. Swipe or drag upward to advance and downward to go back.
The mouse wheel and Up/Down or Page Up/Page Down keys also turn pages. The reader
shows one fitted page at a time; the page count and buttons reflect its position.

PDFs are read-only. Files up to 32 MiB are loaded into memory, including remote
and decrypted LocalCrypt documents; no plaintext PDF cache or library import is
created. Close the reader to release the document. Private windows become
unavailable when their credentials are revoked. Password-protected or damaged
PDFs report an opening error; PDF password entry is not supported.

## Search

Enter text in **Find in PDF** and submit it or choose **Next match**. Search
ignores case and covers the whole document. Next match and Previous match wrap
around the results and jump to the matching page. A result count and text snippet
identify each match, including multiple matches on the same page. Clear the
query to clear results. On desktop, Ctrl+F (Command+F on macOS) focuses search.

Search works with local, remote and LocalCrypt PDFs and creates no persistent
text index. Search text and results clear when the reader closes or its private
session is revoked. Scanned pages require an existing searchable text layer;
OCR is not included. Results are capped at 1,000 (shown with a `+` when there are
more); documents with more than 8 MiB of extracted text report a search limit.

Use **Find in PDF** or the standard Find shortcut to reveal search. The search
panel starts collapsed. Page arrows, the numeric page selector and the full-screen
button stay in the compact reader toolbar; F11 toggles full screen.
