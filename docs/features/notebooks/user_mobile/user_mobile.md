# reMarkable notebooks on Android and iOS

To annotate a PDF, open its **⋯** menu and choose **Duplicate as .rmdoc to
annotate**. This creates and opens a notebook in the PDF's folder, with the same
base name and the PDF pages behind editable ink. An existing `.rmdoc` shows an
error; neither that file nor the PDF is replaced. The folder must support
creating files. PDF-backed pages can be duplicated inside their notebook,
but cannot be copied to another notebook; overview thumbnails show ink only.

A notebook is a document type in **New document**: choose **Notebook (.rmdoc)**,
enter its name and choose a folder in ordinary Local storage or an unlocked
**LocalCrypt** location. Open existing `.rmdoc` files from the file browser,
including Workspaces. The editor opens above the current screen. **Close document (X)** uses the shared
save/discard guard and returns to Home. iOS/iPadOS has one native X, with no
additional Back arrow; Android has one X on the canvas. There is no separate Notebooks tab.

**Save** writes edits to the selected notebook. **Save As** uses the shared
location picker and switches the editor to the new file. **Export .rmdoc** writes
a separate copy. Ordinary notebook checkpoints support recovery; private drafts
stay in memory until Save writes verified ciphertext. Private notebooks appear
in the open Documents list while unlocked, without ordinary Recent or saved
workspace entries. Exporting or saving private content to ordinary storage asks
before creating a decrypted copy. Save or explicitly discard unsaved private
edits before closing or locking credentials. Cloud locations remain read-only.

The document fills the editor viewport. A small floating strip at the top provides the
current brush, **Erase**, **Select / move**, **Undo**, **Redo** and **…** in one row,
including on narrow phones. Android’s canvas X shares that row; iOS retains its
native X. The **…** button opens an anchored **Notebook actions** dropdown. There
are no permanent title, save-status or page-navigation rows. Choose
**Notebook actions → Hide tools** to
leave only a **Show tools** button on the canvas (the native iOS X stays available); showing the tools again preserves your brush,
color, width and view.

Tap the current brush icon to open **Writing tools**: choose an instrument card,
then a **Thin**, **Medium** or **Thick** stroke sample, then an ink color.
Brushes and available colors each use a three-column grid. The panel
shows Ballpoint, Fineliner, Highlighter in its first brush row; Pencil,
Mechanical pencil, Calligraphy in the second; and Marker, Shader, Paintbrush
in the third. The panel
floats below the toolbar. Tap the brush icon again, tap outside, or start a
stroke outside the panel to close it; that first stroke draws immediately. The current
brush has a dark background and check mark in the palette; the top button also
shows its nib and a small ink-color indicator. A border and check mark identify
the selected color. Colors follow the selected brush's supported palette and
remain visible in high-contrast mode and while grayscale document preview is on. The original brush icons are shared with the desktop editor.

Open **Notebook actions** for **Pages Overview**, **Layers**, saving, Save As, export,
**Show in folder** for a saved source and **Delete document…**. **View and input…**
contains zoom, **Grayscale preview** and **Draw with finger**. Rename saved files
from the file browser; an open notebook follows its renamed source and retains
unsaved ink. **Layers** selects
the visible layer to draw on, shows or hides layers, and adds a named layer.
Deletion asks before removing the source file and recovery draft, or an unsaved
draft without a source. Cancelling keeps the document editable. A source changed
elsewhere must be reopened before deletion.
Save status appears in the dropdown; errors also appear as dismissible messages
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
horizontal finger swipes change pages when the page fits the viewport width.
Vertical drags scroll; when zoomed in, finger drags pan instead of turning pages.
Pointer cancellation discards the unfinished stroke. Resize and zoom change the
view while stored points retain page coordinates. High magnification may soften
the screen preview to keep memory use bounded; saved and exported ink keeps its
full native geometry. Pressure depends on what the
device supplies; Android forwards historical pen positions and pressure directly
to the canvas, and iOS uses WebView pointer/coalesced samples. Ballpoint, Pencil,
Marker, Paintbrush, Calligraphy and Shader vary with pressure. Fineliner,
Mechanical pencil and Highlighter keep a constant width. Calligraphy uses a fixed
45-degree slanted nib; stroke direction changes its width independently of pen
tilt. Hardware palm rejection is not guaranteed.

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
also apply here. The initial canvas previews native ink, not page templates or
unsupported page objects. Physical Boox and reMarkable checks are still required;
a simulator cannot certify writing latency, palm rejection or tablet editability.

## Eraser types and sizes

Press **Erase** to select the eraser and open its settings. **Erase parts of
strokes** is the default: only ink under the eraser path is removed, leaving
the rest of a long stroke intact. Choose **Small**, **Medium** (the default) or
**Large**, or switch to **Erase whole strokes**. Settings float below the
toolbar; tap the eraser icon again, tap outside, or start erasing
outside the panel to close it. That first gesture erases immediately. Both types respect hidden
layers and support Undo/Redo. The selected type and size remain active while
you work in that editor.
