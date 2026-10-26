# reMarkable notebooks on desktop

Choose **Notebook (.rmdoc)** in the desktop **New / Open Document** chooser.
**New** opens a blank notebook immediately. Choose a destination when you first
use **Save** or **Save As**; cancelling leaves the draft open. Closing an edited,
unsaved notebook asks whether to save, discard or cancel. **Open** chooses an
existing `.rmdoc` file.
You can also activate `.rmdoc` files in the file browser. Notebooks open as
ordinary document tabs in Documents, with the same detach/close controls as
other document types. There is no separate Notebooks navigation destination.
New unsaved drafts stay in memory until saved. Local recovery copies support
existing notebooks; private notebooks keep edits in memory until explicitly saved.
Use **Export** to write an updated `.rmdoc` file copy. The standalone editor's
saved-copy list remains available when running without the application host.


**Open**, **Save** and **Save As** use the shared storage chooser, including
unlocked LocalCrypt copies. Saving a private notebook publishes verified
ciphertext; its unsaved draft stays in memory and does not use ordinary recovery.
Saving or exporting private content to ordinary storage asks before writing a
decrypted copy. Cloud notebook opening and editing remain unavailable.

Choose Fineliner, Ballpoint, Pencil, Mechanical pencil, Marker, Paintbrush,
Calligraphy, Highlighter or Shader, plus a supported ink color and
Thin / Medium / Thick width. Drag on the page to draw.
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

## Paper Pro / Move brush settings

The writing pens, pencils and paintbrush offer black, gray, white, blue, red,
green, yellow, cyan and magenta. Highlighter offers yellow, green, pink, blue,
orange and gray. Shader offers gray, blue, red, green, yellow, cyan, magenta
and orange, each with its own native transparency; it has no black or white
choice.

Each brush has **Thin**, **Medium** and **Thick** widths; these labels are not
fixed physical measurements. Fineliner and mechanical pencil keep an even width.
Pressure varies the other drawing tools, and calligraphy also responds to stroke
direction. Pencil tools have a grain texture, paintbrush has softer edges,
highlighter darkens the content beneath it, and separate Shader strokes build
color when they overlap. Textures and nominal widths remain approximations
pending comparison with strokes made on the tablet.

**Grayscale preview** approximates monochrome readability using luminance. It
does not emulate a particular screen or firmware, or certify older-device import.
Saved/exported ink keeps its native color IDs and RGBA overrides, including
orange highlights and translucent Shader ink.

## Current compatibility limits

This is experimental format support. It edits ordinary v6 native ink in notebook
archives with legacy page lists or modern `cPages` metadata. It preserves opaque
archive members and untouched scene frames. Typed text, text-anchored ink, image
objects, native eraser objects, nested ink groups, invalid scene geometry,
unknown scene types and older
ink versions show a preservation warning
and disable ink editing on that page. Cross-notebook copying of unsupported pages
is disabled because their resource dependencies cannot yet be guaranteed.
PDF/EPUB-backed archives are rejected without changing the source.

The page surface uses 1404 × 1872 notebook units. Existing templates are preserved
but are not rendered behind the ink. Stroke selection currently moves one stroke;
there is no multi-stroke lasso, partial eraser, OCR, cloud sync or exact brush
texture simulation. Archives are limited to 32 MiB compressed, 128 MiB expanded,
4096 members and 1000 pages. Very long strokes or densely populated pages can
reach editing limits; rejected edits keep the previous saved content. Error
messages leave the source copy available. Expanded drawing controls scroll so
the page remains available in short windows.

A successfully encoded archive is not proof of editability on every tablet.
Physical Boox pressure/palm behavior and reMarkable import/select/move/erase checks
remain required before calling this fully tablet-verified. See the
[development guide](../development/development.md) for the current evidence scope.
