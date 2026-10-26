# reMarkable notebooks on Android and iOS

A notebook is a document type in **New document**: choose **Notebook (.rmdoc)**,
enter its name and choose a folder in ordinary Local storage or an unlocked
**LocalCrypt** location. Open existing `.rmdoc` files from the file browser,
including Workspaces. The editor opens above the current screen; Back/Close
returns to that origin. There is no separate Notebooks tab.

**Save** writes edits to the selected notebook. **Save As** uses the shared
location picker and switches the editor to the new file. **Export .rmdoc** writes
a separate copy. Ordinary notebook checkpoints support recovery; private drafts
stay in memory until Save writes verified ciphertext. Private notebooks appear
in the open Documents list while unlocked, without ordinary Recent or saved
workspace entries. Exporting or saving private content to ordinary storage asks
before creating a decrypted copy. Save or explicitly discard unsaved private
edits before closing or locking credentials. Cloud locations remain read-only.

Choose one of nine brushes including Shader, a supported Paper Pro / Move color,
Thin / Medium / Thick width and a visible layer. **Grayscale preview** changes
only the view; export keeps the native colors. The
[Paper Pro / Move brush settings](../user/user.md#paper-pro--move-brush-settings)
list the palettes and rendering limits. Write with a stylus or enable
**Draw with finger**. With finger drawing disabled, touch drags pan the page.
Pointer cancellation discards the unfinished stroke. Resize and zoom change the
view while stored points retain page coordinates. Pressure depends on what the
native WebView supplies; hardware palm rejection and tilt are not guaranteed.

On Boox, the notebook requests fast black-and-white partial updates during stylus
contact when the firmware supports view-level refresh control. After pen-up it
returns to the previous refresh mode and requests a quality partial update.
Fast preview can show fewer gray levels and some ghosting. Other Android devices
and iOS keep their normal display behavior. The canvas paints new pen segments
incrementally and keeps completed ink visible while saving.

Use **Undo**, **Redo**, whole-stroke **Erase**, and **Select / move** to edit.
The page arrows change pages; **＋ Page** inserts one after the current page.
Expand **Page and drawing options** for duplication, deletion, ordering, layers,
renaming, zoom and copying a page to another saved notebook. Import the target
notebook first. Copying preserves the source page and saves the target separately.

**Export .rmdoc** opens the native save destination picker and writes a copy.
Cancelling preserves the local notebook. Transfer and tablet import are separate
operations; export does not connect to a reMarkable account or tablet.

The [desktop guide's compatibility limits](../user/user.md#current-compatibility-limits)
also apply here. The initial canvas previews native ink, not page templates or
unsupported page objects. Physical Boox and reMarkable checks are still required;
a simulator cannot certify writing latency, palm rejection or tablet editability.
