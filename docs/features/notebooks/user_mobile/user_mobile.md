# reMarkable notebooks on Android and iOS

Choose **New document → Notebook (.rmdoc)**, enter a name and select a template, size and Local or unlocked LocalCrypt folder. Open an existing notebook from Files. To annotate a PDF, choose **⋯ → Duplicate as .rmdoc to annotate** in a writable folder. The notebook opens beside the source with its same base name. Existing files are preserved.

**Save** updates the file. **Save As** saves and switches to a new location. **Export .rmdoc** writes a separate copy. Close offers Save, Quit without saving or Cancel when dirty. **Quit without saving** also discards the recovery draft. If discard fails, the editor stays open. Ordinary notebooks recover completed edits when reopened after an unexpected close. If the original changed or vanished, save the recovered draft to a new location. LocalCrypt drafts stay in memory until saved. Save before locking. Saving or exporting to ordinary storage asks before writing a decrypted copy.

- Tap a brush slot to select it, then tap again for **Writing tools**. Choose brush, color and width. Tap **+** to add a preset, up to three slots. Hold a preset for **Delete preset**.
- Use a stylus or turn on **Notebook actions → View and input → Draw with finger**. Choose **Constant stylus pressure (this open document)** for pens without pressure sensitivity. The choice resets on reopen. **Finishing pen input; try again** means wait and retry Save.
- With finger drawing disabled, swipe horizontally to change pages and use two fingers to pan. Swipe beyond the last page for **+ Page**. Pinch to zoom 10%–400%. **Reset** restores layout framing. Pen contact takes priority over finger gestures. Physical pressure and palm behavior depend on hardware.
- Use **Select / move** to lasso fully enclosed visible ink and images. Drag the selection, a corner or the rotation handle. Copy, Cut, Delete and **Paste selection** operate on the selection. A successful paste consumes this clipboard. Capture has its own reusable image clipboard.
- **Notebook actions → Pages Overview** opens thumbnails, **Go to page** and add, duplicate, delete, reorder and copy actions. Open or import the target notebook first. **Layers** adds, selects or hides layers. **Hide tools** maximizes the canvas. Use **Show tools** to restore them.

**Notebook actions → Delete document…** requests confirmation before removing the source and recovery draft. Reopen an externally changed source before deletion. See [desktop compatibility limits](../user/user.md#current-compatibility-limits) and [brush settings](../user/user.md#paper-pro--move-brush-settings). Physical Boox, iPad Pencil and reMarkable behavior remain under validation.

## Page templates

Use **Notebook actions → Layers** or **Pages Overview → Page template…** to select a template, Pro or Move format where supported, and background visibility. Added pages inherit the current settings. PDF-backed pages keep their PDF background and can be duplicated within that notebook.

Choose **Paper view** in Layers for framing across the open notebook. Phones default to Move framing. Larger screens and Duo layouts adapt to size and posture. Reset keeps a manual choice and reopening restores automatic framing. See [page templates and paper sizes](../user/user.md#page-templates-and-paper-sizes).

**Save / Save As** retains editable template settings. **Export .rmdoc** uses fixed PDF backgrounds for custom and hidden templates, with separate native ink. Keep the original to change templates later. Export can refuse unavailable artwork, unsupported object bounds or ink above the top edge.

## Eraser types and sizes

Tap **Erase** again for settings. Choose **Erase parts of strokes** or **Erase whole strokes**, then Small, Medium or Large. Tap outside or begin erasing to close. Hidden layers are protected. Undo/Redo applies. Eraser type is remembered per notebook.

## Saving from Notes Library

Writable persistent notebooks save when leaving. A failed save keeps the draft open, and session-only storage prompts when dirty. Use **Note actions → Save and Close** or **Save a copy…** for a separate copy.

## Paper Pro preview

Use **Aa → View and input → Notebook colors** or **Settings → Features → Notebook preview** for Muted or Vivid. The device preference changes display colors. Exports keep native colors.

## Image cutouts and protected PDFs

Tap **Select / move** twice and choose **Capture cutouts and arrange images**. Lasso visible content and **Paste** it on a visible layer. Use **New cutout** to start over an image. Tap an image to move, resize, rotate, copy, cut, delete or **Arrange** it. The editor clipboard clears on close. Captures are capped at four megapixels and about 3 MiB. Native **Add image** picker acceptance is pending.

Use **Unlock PDF** for an encrypted embedded PDF. Retry a wrong password in the same form. Save and Export keep the encrypted PDF and the password stays in session memory.

## Internal page links

Tap an internal PDF link with a finger. Pen input draws. **Undo page jump** is available for three seconds.
