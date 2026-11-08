# reMarkable notebooks on Android and iOS

To annotate a PDF, open its **⋯** menu and choose **Duplicate as .rmdoc to
annotate**. This creates and opens a notebook in the PDF's folder, with the same
base name and the PDF pages behind editable ink. An existing `.rmdoc` shows an
error; neither that file nor the PDF is replaced. The folder must support
creating files. PDF-backed pages can be duplicated inside their notebook,
but cannot be copied to another notebook. PDF overview thumbnails show ink at
the page's scale.

A notebook is a document type in **New document**: choose **Notebook (.rmdoc)**,
enter its name, choose **First page template** and its template size, then choose a folder in ordinary Local storage or an unlocked
**LocalCrypt** location. Open existing `.rmdoc` files from the file browser,
including Workspaces. The editor opens above the current screen. **Close document (X)** uses the shared
save/discard guard and returns to Home. Android and iOS/iPadOS have one X in the
editor: iOS/iPadOS keeps the native Close and title, while Android uses the
canvas toolbar. There is no separate Notebooks tab.

**Save** writes edits to the selected notebook. **Save As** uses the shared
location picker and switches the editor to the new file. **Export .rmdoc** writes
a separate copy. **Quit without saving** discards edits since the last Save, including
the recovery draft, so reopening shows the saved file. Cancel keeps editing. If
discard cannot update recovery, the notebook stays open with an error.
If an ordinary recovered draft's original file is missing or has changed, Save
asks for a new location and preserves the draft. Save As offers **Local files**,
**Shared files**, **Received Files** and available unlocked locations. Two files
with the same name in different folders remain separate documents. Explicitly
choosing **Quit without saving** discards only that draft.
Ordinary notebook checkpoints support recovery; private drafts
stay in memory until Save writes verified ciphertext. Private notebooks appear
in the open Documents list while unlocked, without ordinary Recent or saved
workspace entries. Exporting or saving private content to ordinary storage asks
before creating a decrypted copy. Save or explicitly discard unsaved private
edits before closing or locking credentials. Cloud locations remain read-only.

After pen or finger contact ends, Logistics removes redundant samples from new
strokes while preserving corners, pressure changes and stroke width within small
bounds. Calligraphy retains every sample. Opening or saving existing handwriting
does not reduce its points; the live pen preview is unchanged.

The document fills the area beneath a canvas header containing the filename,
storage location and a compact drawing toolbar with the
working brush, **Add current brush preset (+)**, **Erase**, **Select / move**,
**Undo** and **Redo**. The toolbar
stays above the paper instead of covering handwriting. Swipe the drawing strip
horizontally on narrow phones to reach every tool. Android's **Close (X)** and
**Notebook actions (… )** share that row. iOS/iPadOS retains native Close, page
overview, template/layers, view/input and actions controls; Duo places these in
its side rail when applicable. The filename and drawing tools share a row when
there is room. Narrow screens place the filename and storage label above the
tools. Tap the filename to see its location. Every orientation uses the same
canvas brush icons and color indicators, without switching to a native drawing
strip. The swipe-to-add-page control stays inside
the area beside the side rail.

Notebooks opened inside Notes Library keep these drawing tools and all three
panels: **Pages Overview**, **Page template and layers**, and **View and input**.
They are available from the library's Note actions menu and the canvas's Notebook
actions menu, with native action buttons in the iOS/iPadOS navigation bar or Duo
side rail. **Save a copy…** leaves the library file and current draft attached;
**Show in folder** reveals the containing library folder.
Tap the active brush to open the drawer for brush and ink color choices. The reader accounts
for space occupied by system activity. Choose **Notebook actions → Hide tools**
to leave **Show tools** on the canvas. Hiding and restoring tools keeps the
paper in place and preserves your brush, color and width. The native iOS Close remains available.

In iPhone Duo laptop posture, the upper screen keeps brushes, stroke widths,
colors, view/input settings and layers open in a scrollable tool area. The lower
screen holds the drawing canvas, with the hinge kept clear. The page initially
fits the lower screen's width; use Zoom above it for closer work. Drawing does not dismiss
the tools. Opening, closing, rotating and entering or leaving laptop mode keep
a deliberate zoom and the viewed paper position where the page edges allow.
At the default zoom, the page adapts to the new layout instead.

Tap a brush slot with a finger or pen to select it. The active slot is
highlighted. Tap that slot again to open the **Writing tools** drawer below it.
All nine brushes appear in one row on wide screens and in two full-width rows
of five and four on narrow screens. The ink strip shows the selected brush’s
colors, and the stroke sample sits next to **Thin**, **Medium**, and **Thick**
(Highlighter has one **Fixed** width). The width buttons show the approximate
thickness of a horizontal finger stroke for the chosen brush. Tap the opener again, tap outside, or
start a stroke outside the drawer to close it. That first stroke draws immediately.
A border and check mark identify the selected color. Colors follow the selected brush's supported palette and
remain visible in high-contrast mode and while grayscale document preview is on.
Each brush starts with its first color and remembers your choice for that
notebook across reopenings. Choices follow the notebook's saved page position
on this device, including protected page position storage for LocalCrypt.
The original brush icons are shared with the desktop editor.

Tap **+** in the drawing toolbar to save the current brush, ink color, and width
as a preset. Presets appear between the working brush and **+** in the same row.
Once there are three brush slots, **+** disappears. Touch and hold a saved brush
to open **Delete preset**. Changing the brush, color, or width in the drawer
updates the selected slot in place. Presets are shared across
notebooks on this device and persist after restarting the app.

Open **Notebook actions** for **Pages Overview**, **Layers** (the **Page template
and layers** panel), saving, Save As, export,
**Show in folder** for a saved source and **Delete document…**. **View and input…**
contains zoom, **Grayscale preview**, **Draw with finger** and **Constant stylus
pressure (this open document)**. Enable constant pressure for a pen without
pressure sensitivity, including Apple Pencil (USB-C). The choice applies only
while this document stays open; reopening restores pressure-sensitive input.
It cannot change during a stroke or a pending action. If Save reports
**Finishing pen input; try again**, wait for the pending ink and choose Save
again. Close waits briefly for pending input before offering Save or Quit without saving.
If the canvas is unresponsive, the same decision remains available; Quit without
saving intentionally discards unsubmitted ink. Rename saved files
from the file browser; an open notebook follows its renamed source and retains
unsaved ink. **Layers** selects
the visible layer to draw on, shows or hides layers, and adds a named layer.

Controls follow the device's light or dark appearance using the app's Slate
colors. Paper and PDF backgrounds stay white with a thin black page outline.
The mobile page starts just below the drawing tools. The iOS canvas extends to
the bottom of the display. Where iOS shows a side
rail, the canvas extends behind its soft blur. Drawing tools, page controls,
and floating menus stay within the tappable area beside the rail. The ink colors follow the notebook format.
The bottom zoom bar is hidden initially. Pinching or changing zoom reveals **−**,
**+**, the current percentage and **Reset** for three seconds after the last zoom
change. Showing or hiding it does not move the paper. **Reset** restores the
current layout's default zoom and position. Changing pages also
resets zoom, including when returning to a page. Pinch with two
fingers to zoom from 10% to 400%; this
also works with **Draw with finger** enabled. Starting a pinch cancels the
unfinished finger stroke. The fingers remaining after a pinch do not draw or
turn pages until lifted. **Hide tools** also hides the zoom bar.

Deletion asks before removing the source file and recovery draft, or an unsaved
draft without a source. Cancelling keeps the document editable. A source changed
elsewhere must be reopened before deletion.
On Android, save status appears in the dropdown. Errors appear as dismissible messages
above the document.
Grayscale approximates monochrome readability while retaining export colors; it
does not emulate a specific older screen or certify firmware compatibility.
The [Paper Pro / Move brush settings](../user/user.md#paper-pro--move-brush-settings)
list the nine tools, per-brush palettes and rendering limits.
On supported Boox tablets, Fineliner and Ballpoint use the native handwriting
preview for its nine opaque writing colors: Black, Gray, White, Blue, Red,
Green, Yellow, Cyan and Magenta. Grayscale preview also applies to the temporary
native stroke without changing the saved color. Final ink retains Logistics'
brush shape, pressure widths and saving behavior. Ballpoint's native preview
uses its pressure-dependent widths so thickness stays consistent when the pen
is lifted and the document is reopened. The other brushes retain the existing renderer;
menus and editing tools also leave the native preview. Unsupported firmware
falls back automatically.

Write with a stylus or enable **Draw with finger**. With finger drawing disabled,
horizontal finger swipes change pages at any zoom. Pan in either direction with
**two fingers**; one-finger vertical drags leave the page still. Swiping left past
the final page reveals a **+ Page** button at the right of the page view. Tap it
to create the next page. Select / move and Capture keep their explicit editing
gestures. Inside Notes Library, notebook swipes stay in the editor; use the
left-pane and right-pane buttons to open those panels.
When finger drawing is enabled, stylus contact cancels an unfinished finger
stroke and begins pen input with the supplied pressure.
Pointer cancellation discards the unfinished stroke. Resize and zoom change the
view while stored points retain page coordinates. The drawing surface suppresses
browser page selection and long-press callouts, including extra contacts during
a stroke; text fields remain editable and the Select / move tool remains available.
High magnification may soften
the screen preview to keep memory use bounded; saved and exported ink keeps its
full native geometry. Pencil has softer, broken graphite grain in the app; Mechanical
pencil has a denser, finer lead texture. This appearance is shared with desktop
and leaves saved/exported stroke geometry and brush presets unchanged. Pressure
depends on what the device supplies; Android forwards historical pen positions and pressure directly
to the canvas, and iOS uses WebView pointer/coalesced samples. Ballpoint, Pencil,
Marker, Paintbrush, Calligraphy and Shader vary with pressure. Fineliner,
Mechanical pencil and Highlighter keep a constant width. Calligraphy uses a fixed
45-degree slanted nib; stroke direction changes its width independently of pen
tilt. Finger drawing, panning and pinching are blocked while a pen is drawing or
detected near the paper, and for 250 milliseconds after release. Proximity needs
hardware/OS support; contact-based protection works without hover. Physical palm
classification still depends on the device.

On iPad, the editor accepts pen events through the native **WKWebView** canvas.
This is the Apple Pencil input path; the editor does not embed PencilKit or its
system tool picker. Pen pressure and coalesced movement samples feed the same
native `.rmdoc` stroke model as Android. Pen contact cancels an existing finger
pan, and further finger movement cannot pan the document during that pen stroke.
Finger drawing stays optional. The iOS simulator checks this software behavior
with synthetic pen events; physical Pencil pressure, latency and palm behavior
still require an actual iPad/Pencil check. Tilt, double-tap and squeeze actions
are not mapped to editor tools.

On Boox, the notebook requests fast black-and-white partial updates during stylus
contact when the firmware supports view-level refresh control. After pen-up it
returns to the previous refresh mode and requests a quality partial update.
Fast preview can show fewer gray levels and some ghosting. Other Android devices
and iOS keep their normal display behavior. The canvas paints new pen segments
incrementally and keeps completed ink visible while saving. Short strokes can
continue while earlier strokes are saved in order, with undo and recovery
updated after each successful checkpoint.
Android requests unbuffered pen delivery, retains each delivered history sample,
and paints each batch immediately. A desynchronized canvas is requested where
the browser supports it. This removes software waits without changing the
digitizer's hardware sampling rate or promising native-app latency. Boox's
unused status strip is reclaimed across the app; Android still reserves actual
camera cutouts, navigation and keyboard space.

Use **Undo**, **Redo**, **Erase**, and **Select / move** to edit.
In **Select / move**, draw a dashed lasso with your finger or pen, even when
**Draw with finger** is off. Only fully enclosed visible strokes are selected.
Drag inside the selection box to move it; drag a square corner to scale uniformly
or the upper circle to rotate. Moving farther from the centre makes rotation
finer. **Copy**, **Cut** and **Delete** appear below the box. **Paste strokes**
pastes into the current page at the original page position, independently of zoom
or scroll. A successful mobile paste consumes the stroke clipboard and hides
**Paste strokes**; Copy again to paste another selection. A failed save keeps the
clipboard available for retry. This is separate from Capture's reusable image
clipboard. Cancelled gestures do not save edits.
Open **Notebook actions → Pages Overview** for selectable ink thumbnails, the
page count, previous/next arrows, **Go to page**, and commands to add, duplicate,
delete, reorder or copy the current page to
another saved notebook.
**Add page**, at the bottom of the dropdown, inserts immediately after the current
page and opens the new page. The overview also has **＋ Page**. **More pages**
loads another batch of thumbnails. Import the target notebook before copying a page.
Panels scroll on small screens and can be dismissed with their close button,
a tap outside, or Escape on an attached keyboard. Copying preserves the source
page and saves the target separately.

**Export .rmdoc** opens the native save destination picker and writes a copy.
Cancelling preserves the local notebook. Transfer and tablet import are separate
operations; export does not connect to a reMarkable account or tablet.

The [desktop guide's compatibility limits](../user/user.md#current-compatibility-limits)
also apply here. Supported page templates appear beneath native ink; unsupported
template references and page objects remain preserved. Physical Boox and reMarkable checks are still required;
a simulator cannot certify writing latency, palm rejection or tablet editability.

## Page templates

Open **Notebook actions → Layers**, or **Pages Overview → Page template…**, to
select the current page's template, Paper Pro or Paper Pro Move
template format where distinct versions exist, and background visibility. The format
selector is hidden for Blank, repeating lined/grid/dot paper and imported templates. The catalog includes lined paper,
grids, dots, restaurant reviews, meeting notes, daily plans, checklists, Cornell
notes and weekly plans. Edits use the same
Save, recovery and Undo/Redo behavior as desktop. New pages inserted after the current page inherit its template, size and
background visibility. Other pages stay unchanged.
PDF-backed documents retain their embedded PDF background.

Use **Export .rmdoc** for a copy to import into reMarkable. Custom layouts and
hidden backgrounds are carried as fixed vector PDF pages, beneath editable
native ink. **Save / Save As** keeps the original Logistics template settings.
The exported copy's backgrounds cannot be changed with reMarkable's template
picker; keep the original notebook for later template changes.

Structured forms export with distinct Pro and Move PDF page sizes, extending
the page box when necessary to retain handwriting beyond the form’s edges.
Repeating paper keeps a shared canvas.

Export can refuse unavailable visible artwork, unsupported native objects whose
bounds cannot be determined, or ink above the page's top edge. Keep the original
with **Save**; export failure does not require replacing it with a blank page.
These restrictions apply when converting notebook templates to PDF backgrounds;
an existing PDF-backed notebook retains its embedded PDF.

Portrait phones and the closed Duo fit the centered **Paper Pro Move** width.
Portrait iPads and the open Duo fit the whole page. In open Duo landscape,
the compact page height fills the available space. A larger page opens centered
at the top and you can scroll down to see the rest. Other landscape layouts
fit the available width. The mobile zoom readout shows **1.0×** when the
current page height matches the available height.

Zooming in from the default Move view exposes
the surrounding page while keeping the viewed paper position. Choose a manual
**Paper view** in Layers to use the same framing across all pages of the open
document. Page changes and Reset zoom retain this choice; reopening restores
automatic framing. An explicit Paper view takes precedence over the template’s format.
See [page templates and paper sizes](../user/user.md#page-templates-and-paper-sizes)
for line counts, saved-format versus viewing choices and reMarkable compatibility.

## Eraser types and sizes

Press **Erase** to select the eraser. Press it again to open its settings.
**Erase parts of strokes** is the default. It removes ink under the eraser path, leaving
the rest of a long stroke intact. Choose **Small**, **Medium** (the default) or
**Large**, or switch to **Erase whole strokes**. Settings float below the
toolbar; tap the eraser icon again, tap outside, or start erasing
outside the panel to close it. That first gesture erases immediately. Both types respect hidden
layers and support Undo/Redo. The notebook remembers the selected eraser type
across reopenings. The size remains active while you work in the editor.

## Saving from Notes Library

In wide iPhone Duo and iPad landscape windows, the drawing tools share the row
with previous and next note when the document pane has room. In smaller panes
the drawing strip stays just above the paper. Writable notebooks on persistent
storage save when you open another document or close the library. A failed save keeps the drawing open so you can retry. Session-only
storage still asks before leaving a dirty drawing. For writable notebooks, use
**Note actions → Save and Close** to save pending edits and close the library.

## Paper Pro preview

A muted color preview is enabled by default to approximate Paper Pro / Paper Pro Move color E Ink. Turn it off for vivid display colors in **Settings → Features → Notebook preview**, then reopen the notebook. It applies to the page and overview thumbnails, including backgrounds. This is a display approximation, not a calibrated tablet profile; saved and exported colors remain unchanged.

Logistics draws its own template previews and custom layouts. Native lined options
are labeled reMarkable compatible; Logistics is not affiliated with or endorsed
by reMarkable. Native exports reference the tablet’s installed lined backgrounds.


## Image cutouts and protected PDFs

Choose **Notebook actions → View and input → Capture cutouts and arrange images**
to enter the separate Capture mode. Lasso an area of the page to copy
its visible background, handwriting and images into the editor clipboard. The
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

In a PDF-backed `.rmdoc`, tap an internal PDF link with a **finger** to follow it, including when finger drawing is enabled. Pen input keeps drawing. Swipes, pinches and holds do not activate links. **Undo page jump** appears over the bottom of the editor for three seconds; tap it to return.
