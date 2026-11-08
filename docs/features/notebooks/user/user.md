# reMarkable notebooks on desktop

Choose **Notebook (.rmdoc)** in the desktop **New / Open Document** chooser.
**New** lets you name the notebook, choose its first-page template and select a
Pro or Move size for Logistics layouts. Blank paper is also available. Create
opens the editable draft; Cancel leaves the chooser unchanged. Choose a destination when you first
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

### Retrieve a notebook from a reMarkable tablet

On desktop, open **Debug → Notebooks → Retrieve RMDOC from reMarkable Tablet…**.
Connect the tablet by USB and leave it awake. The dialog shows the default
**Address** `10.11.99.1`, **Port** `22` and the tablet username `root`.
Enter the SSH host or IP address without a URL scheme and change the port if
needed. Click **Connect**, filter the list by notebook or folder, select a
document, then click **Retrieve…** and choose where to save the copy.

This tool needs working SSH access and OpenSSH on the computer. On macOS,
OpenSSH can prompt for host verification and the tablet password. Other
desktops can use SSH keys or a configured OpenSSH password prompt. On Paper Pro,
SSH requires Developer Mode to be enabled already. Enabling it factory-resets
the tablet. [reMarkable Developer Mode](https://developer.remarkable.com/documentation/developer-mode)

Close the notebook on the tablet and let any active edits or sync finish before
retrieving it. Logistics reads the source files over SSH and packages the
archive on the computer, preserving native ink, images and the embedded PDF.
The tool leaves the tablet files and any existing destination file intact.
The resulting archive can be larger than the notebook editor's import limits.

### Editing and storage

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
Single-key drawing shortcuts leave text fields alone. Select and Move draws a
dashed lasso with the mouse, pen or finger. Only fully enclosed strokes on visible
layers are selected; partly enclosed strokes are omitted. Drag inside the resulting
box to move the selection. Its four square corner handles scale uniformly; the
circle above its top edge rotates. Moving farther from the centre gives finer
rotation control. The **Copy**, **Cut** and **Delete** icons appear beside the
box, on the right when there is room and on the left otherwise.
**Paste strokes** pastes into the current page at the original page position,
regardless of zoom or scroll. This private stroke clipboard lasts until the editor
closes and is separate from Capture's image clipboard. Undo/Redo covers edits;
Copy does not change the page. On narrow windows the
toolbar wraps while the page keeps the full content width.

Use **File → Save** (`Ctrl`/`⌘ S`) and **Save As…** (`Ctrl`/`⌘ Shift S`) to save.
**Export Copy…** writes a separate `.rmdoc` copy; **Rename Notebook…** changes the
notebook's name. **New**, **Open** and **Close Document** have the platform's usual
shortcuts. The same menus follow the document into a detached window.

After you finish drawing a stroke, Logistics removes redundant samples while
preserving corners, pressure changes and stroke width within small bounds.
Calligraphy retains every sample. Opening or saving existing handwriting does
not reduce its points; the live pen preview is unchanged.

**Edit → Undo/Redo** and their standard shortcuts retain up to 50 edits in the
current editing session. Edits to an unsaved draft stay in memory until saved.
Reopening a saved notebook starts a fresh undo history.

The footer provides **Pages Overview**, page navigation, **Add Page** (`＋`) and zoom.
Open **Pages Overview** in the footer or the **Page** menu to select a page by its
numbered thumbnail. The current page is marked; **More pages** loads the next
batch of previews. Supported templates appear beneath ink; unavailable imported
artwork and unsupported content may not appear in thumbnails. **Add Page**,
including the action inside the overview, inherits the current template and inserts a new ink-free
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

Each brush starts with its first color and remembers your choice for that
notebook across reopenings. Logistics keeps the choices with the notebook's
saved page position on this device. LocalCrypt uses the same protected storage
as its page positions.

Highlighter has one **Fixed** width, matching the sampled Paper Pro firmware.
Other brushes have **Thin**, **Medium** and **Thick** widths; these labels are not
fixed physical measurements. Fineliner and mechanical pencil keep an even width.
Pressure varies the other drawing tools, and calligraphy also responds to stroke
direction. Pencil tools have a grain texture, paintbrush has softer edges,
and highlighter tints the content beneath it. Overlapping passes of the same
highlighter color share one tint. Separate Shader strokes build color when
they overlap. Textures and nominal widths remain approximations
after the November 4 Paper Pro calibration; speed, tilt and exact firmware
textures are not reproduced.

The app's Pencil uses softer, broken graphite grain; Mechanical pencil uses a
denser, finer lead texture. These original procedural textures stay aligned to
the paper through zooming and redraws. They affect the editor's appearance;
saved/exported stroke geometry, pressure, widths and native brush presets stay
unchanged. The tablet applies its own rendering when opening an exported notebook.

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
another notebook is unavailable. Page overview thumbnails show the PDF background
with ink over it.
EPUB-backed archives remain unsupported.

The page surface uses 1404 × 1872 notebook units. Supported templates render beneath
the ink; unrecognized template references remain preserved with an artwork notice.
There is no OCR, cloud sync or exact brush
texture simulation. Logistics accepts RMDOC archives up to 128 MiB compressed,
256 MiB expanded and 65,536 archive entries. Notebook page count has no separate
limit. An embedded PDF and the storage location can have their own limits.
Very long strokes or densely populated pages can
reach editing limits; rejected edits keep the previous saved content. Error
messages leave the source copy available. Expanded drawing controls scroll so
the page remains available in short windows.

A successfully encoded archive is not proof of editability on every tablet.
Physical Boox pressure/palm behavior and reMarkable import/select/move/erase checks
remain required before calling this fully tablet-verified. See the
[development guide](../development/development.md) for the current evidence scope.

## Page templates and paper sizes

Open **Page → Page Template…**, or **Page template** beside the active layer in
the toolbar, to change only the current page. These changes support Undo/Redo.

Choose Blank, lined paper (large: 21 rules; small: 41), the native
25-rule medium, or Logistics' more distinct 31-rule medium. Grid, Dots,
Restaurant review, Meeting notes, Daily planner, Checklist, Cornell notes and Weekly planner are also available.
**Template format** selects Paper Pro or Paper Pro Move for layouts with distinct
versions. It is hidden for Blank, repeating lined/grid/dot paper and imported templates.
**Show template** hides only the background in Logistics; it leaves writing intact.
These are per-page edits with Undo/Redo, Save, recovery and page-copy support.
New pages inserted after the current page inherit its template, size and
background visibility; existing pages stay unchanged. Imported PDFs keep their source background
and do not offer notebook template replacement.

**Paper view** changes the visible writing area without moving or scaling ink.
Desktop and large tablets start with Paper Pro; phones start with Paper Pro Move. Move shows a
centered, top-aligned region of the same page, expanding to include writing beyond
its left, right or bottom edges. Pro reveals the surrounding paper. Select Pro
to write in those extra margins. Paper view is a session display choice, separate
from the saved template format; changing it does not edit the notebook. Your choice
applies across all pages of the open document, including after Reset zoom. Reopening
the document starts with the automatic device framing again.

**Save / Save As** retains the original notebook with editable per-page template
settings and vector artwork. For reMarkable, use **Export Copy…** (mobile:
**Export .rmdoc**). The exported copy embeds custom backgrounds as vector PDF
pages inside the `.rmdoc`; handwriting stays separate as editable native ink.
Restaurant review, Meeting notes, Daily planner, Checklist, Cornell notes and Weekly planner use distinct Pro and Move
PDF page sizes. Repeating paper keeps a shared canvas. The export extends a
form’s page box if needed to retain handwriting beyond its nominal edges.
Hidden backgrounds also stay hidden in that copy. Stock-only lined notebooks
with visible backgrounds retain native template references instead of a PDF.

The original Logistics notebook stays unchanged. Custom-template export copies
are PDF-backed documents, so their backgrounds are fixed when reopened in either
app; reMarkable's notebook template picker cannot replace them. Keep the original
to change presets, format or visibility later. Export refuses unavailable artwork
instead of silently replacing it with blank paper; select a supported template
or hide that background first. Existing PDF-backed notebooks export their original
PDF without rebuilding it. Physical tablet geometry and stylus behavior remain
separate acceptance checks.

Portable background conversion can also refuse pages containing unsupported
native objects whose bounds cannot be determined, or ink above the page's top
edge. Save preserves the source notebook in these cases; keep it for recovery
and further work. A successful export does not certify tablet import or writing
responsiveness.

## Eraser types and sizes

Press **Erase** to select the eraser and open its settings. **Erase parts of
strokes** is the default: only ink under the eraser path is removed, leaving
the rest of a long stroke intact. Choose **Small**, **Medium** (the default) or
**Large** using the stroke previews. Desktop settings open in a compact dropdown below the eraser button;
click outside it, press Escape, click the eraser button again, or choose **Done**
to close it and keep erasing. Press the tool again to
change its size or switch to **Erase whole strokes**. Both types respect hidden
layers and support Undo/Redo. The selected type and size remain active while
you work in that editor.

## Saving from Notes Library

Writable notebooks on persistent storage save when you navigate away or close
the library. If saving fails, the notebook stays open with its draft. For
session-only storage, Notes Library asks what to do before leaving a dirty
notebook.

## Paper Pro preview

A muted color preview is enabled by default to approximate Paper Pro / Paper Pro Move color E Ink. Turn it off for vivid display colors in **Settings → Notebooks → Notebook preview**, then reopen the notebook. It applies to the page and overview thumbnails, including backgrounds. This is a display approximation, not a calibrated tablet profile; saved and exported colors remain unchanged.

Logistics draws its own template previews and custom layouts. Native lined options
are labeled reMarkable compatible; Logistics is not affiliated with or endorsed
by reMarkable. Native exports reference the tablet’s installed lined backgrounds.


## Image cutouts and protected PDFs

Choose **Capture** as a separate drawing mode. Lasso an area of the page to copy
its visible background, handwriting and images into the editor clipboard. PDF
and template backgrounds retain their displayed proportions and margins. The
lasso outline and selection handles are excluded. **Paste** places a separate
image on the active visible layer; paste again on the same page or switch pages
and paste there. The clipboard lasts until this editor closes. It is separate
from the system clipboard. **Add image** accepts PNG/JPEG through the browser
file chooser and converts it into a bounded PNG. Native mobile file-chooser
acceptance remains pending.

**New cutout** lets a lasso start inside an existing image without moving it.
In Capture mode, tap an existing image with a finger or pen to select it, then
drag to move. Drag its lower-right handle to scale or its upper handle to rotate.
The floating controls also offer size changes and 15-degree rotation. **Copy**
puts the selected image into the editor clipboard; **Cut** copies it and removes
the source instance. **Delete image** removes an instance without copying it.
Pasting onto a different page preserves the original page position, rotation and
scale, even after changing zoom or scrolling. Same-page paste keeps the existing
center placement. The source page identity remains stable when pages are reordered. Ordinary Select / Move continues to select handwriting.

**Arrange** moves the selected image one position forward/backward or to the
front/back among both handwriting and images on its layer. Layers retain their
own stacking. New pasted images and subsequent strokes start above existing
objects on that layer. Image placement, arrangement and deletion support
Undo/Redo, Save, page duplication and supported page transfers. The ink eraser
leaves image pixels intact; on pages containing images, ink erasure appears when
the gesture is acknowledged. New captures are limited to four megapixels and
roughly 3 MiB of PNG data; large captures are reduced automatically.

A password-protected embedded PDF displays an **Unlock PDF** form. An incorrect
password leaves the form open for retry. The password and decrypted rendering
copy stay in memory for that editing session. Save and Export retain the
original encrypted PDF; reopening requires its password again. This applies to
notebooks opened through Local and unlocked LocalCrypt. LocalCrypt continues
to encrypt the entire saved notebook and keeps its unsaved draft in memory.


## Internal page links

In a PDF-backed `.rmdoc`, hold **Command** on macOS or **Ctrl** on Windows/Linux while clicking an internal PDF link to follow it. **Undo page jump** appears for three seconds. Ordinary clicks and pen strokes keep editing the page. Links follow the notebook’s page order; destinations whose original PDF page was removed are unavailable.
