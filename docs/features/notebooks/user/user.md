# reMarkable notebooks on desktop

Open **Notebooks** in the desktop navigation, or activate an `.rmdoc` file in the
file browser. **New notebook** creates a blank notebook; **Open .rmdoc** imports
an existing notebook into a local working copy. The source file is unchanged.
The workspace lists saved copies for reopening. Use **Export .rmdoc** to save a
separate archive through the file dialog, then transfer it to your tablet using
a method supported by your reMarkable model and firmware.

Choose Fineliner, Ballpoint, Pencil, Mechanical pencil, Marker, Paintbrush,
Calligraphy or Highlighter, plus an ink color and width. Drag on the page to draw.
These tools write native stroke types; their on-screen appearance approximates
reMarkable brushes. Pressure is recorded when the input device and browser
provide it; mouse input uses constant pressure.

**Erase** removes whole strokes. **Select / move** selects the topmost stroke at
the pointer and moves it by dragging. **Undo** and **Redo** retain up to 50 edits
in the current editing session. Completed commands save locally. Closing and
reopening retains the notebook content, but starts a fresh undo history.

**＋ Page** inserts a page after the current one. Expand **Page and drawing
options** to duplicate, delete or reorder pages, rename the notebook, add layers,
show/hide layers, change zoom or copy the current page into another saved notebook.
Import or create the target notebook first. Page copying retains the source;
verify the destination before deleting the source page if you want to move it.
At least one page must remain. Copied pages receive fresh page identities.

## Current compatibility limits

This is experimental format support. It edits ordinary v6 native ink in notebook
archives with legacy page lists or modern `cPages` metadata. It preserves opaque
archive members and untouched scene frames. Typed text, text-anchored ink, image
objects, unknown scene types and older ink versions show a preservation warning
and disable ink editing on that page. Cross-notebook copying of unsupported pages
is disabled because their resource dependencies cannot yet be guaranteed.
PDF/EPUB-backed archives are rejected without changing the source.

The page surface uses 1404 × 1872 notebook units. Existing templates are preserved
but are not rendered behind the ink. Stroke selection currently moves one stroke;
there is no multi-stroke lasso, partial eraser, OCR, cloud sync or exact brush
texture simulation. Archives are limited to 32 MiB compressed, 128 MiB expanded,
4096 members and 1000 pages. Error messages leave the source copy available.

A successfully encoded archive is not proof of editability on every tablet.
Physical Boox pressure/palm behavior and reMarkable import/select/move/erase checks
remain required before calling this fully tablet-verified. See the
[development guide](../development/development.md) for the current evidence scope.
