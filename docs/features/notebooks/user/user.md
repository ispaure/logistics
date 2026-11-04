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

The desktop editor uses the application's header menus. The document name appears
in its tab; the page has no second title bar or file-action buttons.

The compact toolbar across the top groups **Undo/Redo**, drawing modes, brush
icons, three stroke-width samples, circular ink-color swatches and the active layer.
Controls use the application's light or dark appearance, including live changes
in Settings. The paper and PDF backgrounds stay white; ink colors are unchanged.
Colors appear directly in the toolbar; the toolbar wraps when the window narrows. Hover an
icon for its name. Pick a brush directly with keys `1`–`9`, or click its icon;
use `B` for Draw, `E` for Eraser settings and `V` for Select and Move.
Single-key drawing shortcuts leave text fields alone. Select and Move picks the
topmost stroke at the pointer, then moves it by dragging. On narrow windows the
toolbar wraps while the page keeps the full content width.

Use **File → Save** (`Ctrl`/`⌘ S`) and **Save As…** (`Ctrl`/`⌘ Shift S`) to save.
**Export Copy…** writes a separate `.rmdoc` copy; **Rename Notebook…** changes the
notebook's name. **New**, **Open** and **Close Document** have the platform's usual
shortcuts. The same menus follow the document into a detached window.

**Edit → Undo/Redo** and their standard shortcuts retain up to 50 edits in the
current editing session. Edits to an unsaved draft stay in memory until saved.
Reopening a saved notebook starts a fresh undo history.

The footer provides **Pages Overview**, page navigation, **Add Page** (`＋`) and zoom.
Open **Pages Overview** in the footer or the **Page** menu to select a page by its
numbered thumbnail. The current page is marked; **More pages** loads the next
batch of previews. Preserved templates and unsupported content may not appear in
thumbnails. **Add Page**, including the action inside the overview, inherits the current template and inserts a new ink-free
page immediately after the current page and opens it. Undo restores the previous
page order and selection.
**Fit page**
is the desktop default and keeps the entire page visible as the window resizes.
Choose **Fit width** or a fixed percentage in the footer or **View → Zoom**
when you want a closer view. Use `Ctrl`/`⌘ +` (or `Ctrl`/`⌘ =`) to zoom in,
`Ctrl`/`⌘ -` to zoom out and `Ctrl`/`⌘ 0` to restore Fit Page. Hold Ctrl or
Command while scrolling the mouse wheel or trackpad over the page to zoom
around the pointer; ordinary scrolling still pans. Keyboard/menu zoom keeps
the viewport center in place. Manual zoom ranges from 10% to 400%, and the
footer shows the current percentage. The editor
also provides **−**, **+** and **Fit** buttons in the footer. Pinch on a laptop
trackpad or use two fingers on a touchscreen to zoom around that point on the
page. Two-finger zoom cancels an unfinished finger-drawn stroke; additional
finger contacts during a pen stroke do not zoom the page. The editor
uses a bounded screen-preview resolution at high magnification; saved and
exported native ink retains its full geometry. **Page** also
provides previous/next (`Alt+Left` / `Alt+Right`), add, duplicate, delete, reorder
and copy-to-notebook actions. Import or create a destination notebook before
copying a page; copying preserves the source. At least one page must remain.
Copied pages receive fresh page identities.

Choose the active layer in the toolbar; open the adjacent layer menu to add a
layer or change layer visibility. **View** contains **Grayscale Preview**,
**Draw with Finger**, zoom settings and **Drawing Toolbar**. Turn off Drawing
Toolbar to give the page more room, then restore it from the same menu.

These tools write native stroke types; their on-screen appearance approximates
reMarkable brushes. Pressure is recorded when the input device and browser
provide it; mouse input uses constant pressure.

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
PDF-backed archives display the embedded PDF beneath editable ink. In the PDF
reader's **⋯** menu, choose **Duplicate as .rmdoc to annotate** to create and open
a notebook beside the PDF with the same base name. An existing `.rmdoc` produces
an error and is preserved. The PDF itself stays unchanged. PDF-backed pages can
be duplicated and reordered within the notebook; copying their backgrounds to
another notebook is unavailable. Page overview thumbnails show ink only.
EPUB-backed archives remain unsupported.

The page surface uses 1404 × 1872 notebook units. Supported templates render beneath
the ink; unrecognized template references remain preserved with an artwork notice.
Stroke selection currently moves one stroke;
there is no multi-stroke lasso, OCR, cloud sync or exact brush
texture simulation. Archives are limited to 32 MiB compressed, 128 MiB expanded,
4096 members and 1000 pages. Very long strokes or densely populated pages can
reach editing limits; rejected edits keep the previous saved content. Error
messages leave the source copy available. Expanded drawing controls scroll so
the page remains available in short windows.

A successfully encoded archive is not proof of editability on every tablet.
Physical Boox pressure/palm behavior and reMarkable import/select/move/erase checks
remain required before calling this fully tablet-verified. See the
[development guide](../development/development.md) for the current evidence scope.

## Page templates and paper sizes

Open **Manage layers** in the desktop toolbar to choose the current page's
template. Choose Blank, lined paper (large: 21 rules; small: 41), the native
25-rule medium, or Logistics' more distinct 31-rule medium. Grid, Dots,
Restaurant review, Meeting notes and Daily planner are also available.
**Template format** selects Paper Pro or Paper Pro Move for Logistics layouts.
**Show template** hides only the background in Logistics; it leaves writing intact.
These are per-page edits with Undo/Redo, Save, recovery and page-copy support.
New pages inherit the current template. Imported PDFs keep their source background
and do not offer notebook template replacement.

**Paper view** changes the visible writing area without moving or scaling ink.
Desktop and large tablets start with Paper Pro; phones start with Paper Pro Move. Move shows a
centered, top-aligned region of the same page, expanding to include writing beyond
its left, right or bottom edges. Pro reveals the surrounding paper. Select Pro
to write in those extra margins. Paper view is a session display choice, separate
from the saved template format; changing it does not edit the notebook.

Stock lined templates remain native template-name references, rather than PDFs
or ink layers. Logistics layouts include original vector `.template` artwork in
the archive. Their appearance and per-page format/visibility are supported in
Logistics on all platforms. ReMarkable firmware discovery of these embedded custom
assets and matching tablet view behavior have not been certified; a successful
Logistics export does not prove custom backgrounds will appear on the tablet.

## Eraser types and sizes

Press **Erase** to select the eraser and open its settings. **Erase parts of
strokes** is the default: only ink under the eraser path is removed, leaving
the rest of a long stroke intact. Choose **Small**, **Medium** (the default) or
**Large**. Desktop settings open in a compact dropdown below the eraser button;
click outside it, press Escape, click the eraser button again, or choose **Done**
to close it and keep erasing. Press the tool again to
change its size or switch to **Erase whole strokes**. Both types respect hidden
layers and support Undo/Redo. The selected type and size remain active while
you work in that editor.

## Paper Pro preview

A muted color preview is enabled by default to approximate Paper Pro / Paper Pro Move color E Ink. Toggle it in **Settings → Notebooks → Notebook preview**, then reopen the notebook. It applies to the page and overview thumbnails, including backgrounds. This is a display approximation, not a calibrated tablet profile; saved and exported colors remain unchanged.
