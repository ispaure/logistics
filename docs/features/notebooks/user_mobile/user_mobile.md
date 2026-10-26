# reMarkable notebooks on Android and iOS

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
current brush, **Erase**, **Select / move**, **Undo**, **Redo** and **Hide tools**.
The **…** corner button opens **Notebook actions**.
On narrow phones the strip sits immediately below these corner buttons to avoid
overlap. There are
no permanent title, save-status or page-navigation rows. Tap **Hide tools** to
leave only a **Show tools** button on the canvas (the native iOS X stays available); showing the tools again preserves your brush,
color, width and view.

Tap the current brush icon to open **Writing tools**: choose an instrument card,
a color swatch and a **Thin**, **Medium** or **Thick** stroke sample. The current
brush has a dark background and check mark in the palette; the top button also
shows its nib and a small ink-color indicator. A border and check mark identify
the selected color. Colors follow the selected brush's supported palette and
remain visible in high-contrast mode and while grayscale document preview is on. The original brush icons are shared with the desktop editor.

Open **Notebook actions** for compact **Pages** and **Layers** shortcuts, saving, Save As, export,
naming, **Show in folder** for a saved source, **Delete document…**, zoom, **Grayscale preview** and **Draw with finger**. **Layers** selects
the visible layer to draw on, shows or hides layers, and adds a named layer.
Deletion asks before removing the source file and recovery draft, or an unsaved
draft without a source. Cancelling keeps the document editable. A source changed
elsewhere must be reopened before deletion.
Save status appears in this panel; errors also appear as dismissible messages
above the document.
Grayscale approximates monochrome readability while retaining export colors; it
does not emulate a specific older screen or certify firmware compatibility.
The [Paper Pro / Move brush settings](../user/user.md#paper-pro--move-brush-settings)
list the nine tools, per-brush palettes and rendering limits.
Write with a stylus or enable **Draw with finger**. With finger drawing disabled,
touch drags pan the page.
Pointer cancellation discards the unfinished stroke. Resize and zoom change the
view while stored points retain page coordinates. Pressure depends on what the
native WebView supplies; hardware palm rejection and tilt are not guaranteed.

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

Use **Undo**, **Redo**, whole-stroke **Erase**, and **Select / move** to edit.
Open **Notebook actions → Pages** for the page count, previous/next arrows,
and commands to add, duplicate, delete, reorder or copy the current page to
another saved notebook.
**＋ Page** inserts a page after the current one. Import the target notebook first.
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
