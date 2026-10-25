# reMarkable notebooks on Android and iOS

**Notebooks** appears after **Home**, before **Workspaces**. Choose **New notebook**
or **Open .rmdoc**. Open uses the Android document provider or iOS Files picker.
An ordinary local `.rmdoc` file can also be opened from Workspaces. Imports become
private app-owned notebook copies; the original is unchanged. Completed strokes
and page commands are saved on this device for reopening from Notebooks.

Choose a brush, color, width and visible layer. Write with a stylus or enable
**Draw with finger**. With finger drawing disabled, touch drags pan the page.
Pointer cancellation discards the unfinished stroke. Resize and zoom change the
view while stored points retain page coordinates. Pressure depends on what the
native WebView supplies; hardware palm rejection and tilt are not guaranteed.

Use **Undo**, **Redo**, whole-stroke **Erase**, and **Select / move** to edit.
The page arrows change pages; **＋ Page** inserts one after the current page.
Expand **Page and drawing options** for duplication, deletion, ordering, layers,
renaming, zoom and copying a page to another saved notebook. Import the target
notebook first. Copying preserves the source page and saves the target separately.

**Export .rmdoc** opens the native save destination picker and writes a copy.
Cancelling preserves the local notebook. Transfer and tablet import are separate
operations; export does not connect to a reMarkable account or tablet.
On compact iPhones, UIKit may place later destinations in its native **More** menu.

The [desktop guide's compatibility limits](../user/user.md#current-compatibility-limits)
also apply here. The initial canvas previews native ink, not page templates or
unsupported page objects. Physical Boox and reMarkable checks are still required;
a simulator cannot certify writing latency, palm rejection or tablet editability.
