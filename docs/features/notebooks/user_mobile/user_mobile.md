# reMarkable notebooks on Android and iOS

Choose **New document → Notebook (.rmdoc)** and enter a name. Tap **First page template** to open the picker, preview the pattern at Paper Pro or Paper Pro Move size, and tap **Use template**. Then choose a Local or unlocked LocalCrypt folder. Open an existing notebook from Files. To annotate a PDF, choose **⋯ → Duplicate as .rmdoc to annotate** in a writable folder. The notebook opens beside the source with its same base name. Existing files are preserved.

**Save** updates the file. **Save As** saves and switches to a new location. **Export .rmdoc** writes a separate copy. Close offers Save, Quit without saving or Cancel when dirty. **Quit without saving** also discards the recovery draft. If discard fails, the editor stays open. Ordinary notebooks recover completed edits when reopened after an unexpected close. If the original changed or vanished, save the recovered draft to a new location. LocalCrypt drafts stay in memory until saved. Save before locking. Saving or exporting to ordinary storage asks before writing a decrypted copy.

In **Documents → Recent**, the notebook row shows its filename and a thumbnail when available. **Unsaved edits** means opening that row resumes the draft.

The top navigation bar shows the filename and storage location between the document controls. The drawing strip sits below. On iPhone Duo with the document controls on the side, open landscape puts the filename to the left of the drawing tools. Closed front portrait puts it above them.

- Tap a brush slot to select it, then tap again for **Writing tools**. Choose brush, color and width. Brushes that respond to pressure offer an **Intensity** slider for fixed-pressure input, including stylus input on iPhone Duo. Pencil starts at 80% and Mechanical Pencil at 95%. Each notebook remembers the intensity per brush. Boox uses the pen’s pressure throughout the stroke. Tap **+** to add a preset, up to three slots. Hold a preset for **Delete preset**.
- Use a stylus or turn on **Notebook actions → View and input → Draw with finger**. On compatible devices, choose **Constant stylus pressure (this open document)** for pens without pressure sensitivity. The choice resets on reopen. **Finishing pen input; try again** means wait and retry Save.
- With finger drawing disabled, swipe horizontally to change pages and use two fingers to pan. Swipe beyond the last page for **+ Page**. The button clears after three seconds or when you write or tap elsewhere. Pinch to zoom 10%–400%. Use **Fit page** to see the whole page or **Fill screen** to cover the drawing area and pan to the rest. **Reset** restores automatic framing. Pen contact takes priority over finger gestures. Physical pressure and palm behavior depend on hardware.
- Use **Select / move** to lasso fully enclosed visible ink and images. Drag the selection, a corner or the rotation handle. Copy, Cut, Delete and **Paste selection** operate on the selection. A successful paste consumes this clipboard. Capture has its own reusable image clipboard.
- **Notebook actions → Pages Overview** opens thumbnails, **Go to page** and add, duplicate, delete, reorder and copy actions. Open or import the target notebook first. In **Layers**, hold a grip and drag to reorder. Tap the red minus and confirm to delete a layer and its contents. **Undo** restores it. Each page keeps at least one layer. **Hide tools** maximizes the canvas. Use **Show tools** to restore them.

**Notebook actions → Delete document…** requests confirmation before removing the source and recovery draft. Reopen an externally changed source before deletion. See [desktop compatibility limits](../user/user.md#current-compatibility-limits) and [brush settings](../user/user.md#paper-pro--move-brush-settings). Physical Boox, iPad Pencil and reMarkable behavior remain under validation.

## Page templates

Open **Change Template…** from **Notebook actions → Layers** or **Pages Overview**. On wider screens, choose a template from the list on the left and review it on the right. Narrow screens use a dropdown above the preview. Choose the size and background visibility, then tap **Apply** to change the current page and preserve handwriting. **Cancel** leaves the page as it was. If imported artwork is unavailable, the picker shows its name and preserves the original until you apply a replacement. Added pages inherit the current settings. PDF-backed pages keep their PDF background and can be duplicated within that notebook.

Choose **Paper view** in Layers for framing across the open notebook. Automatic framing fits the saved Pro or Move format for pages sized in the template picker. Other pages adapt to screen size and posture, with Move framing on narrow portrait phones. Reset keeps a manual choice and reopening restores automatic framing. See [page templates and paper sizes](../user/user.md#page-templates-and-paper-sizes).

When a saved preset differs from the current design, tap **Update to latest layout** to update that preset on the indicated pages. This keeps page sizes, visibility and handwriting in place and supports Undo.

**Save / Save As** retains editable template settings and embeds supported custom layouts as vector PDF backgrounds with separate native ink. Reopening in Logistics uses the saved layout even if the template for new notebooks has changed. You can import the saved file directly on reMarkable, where the layout appears as a PDF background. An older Logistics notebook gets the PDF on its next save. **Export .rmdoc** makes a separate file with a fixed background. Unsupported imported artwork or ink is preserved on Save and can prevent a portable export.

A file re-exported by reMarkable may lose the editable template data. Logistics can still open its PDF background and retained handwriting.

## Eraser types and sizes

Tap **Erase** again for settings. Choose **Erase parts of strokes** or **Erase whole strokes**, then Small, Medium or Large. Tap outside or begin erasing to close. Hidden layers are protected. Undo/Redo applies. Eraser type is remembered per notebook.

## Saving from Notes Library

Writable persistent notebooks save when leaving. A failed save keeps the draft open, and session-only storage prompts when dirty. Use **Note actions → Save and Close** or **Save a copy…** for a separate copy.

## Paper Pro preview

Use **Aa → View and input → Notebook colors** or **Settings → Features → Notebook preview** for Muted or Vivid. The device preference changes display colors. Exports keep native colors.

Use **Aa → View and input → Paper appearance** to choose Follow system (the default), Light or Dark for every notebook. The setting also applies to thumbnails in Files, Favourites, Recent and Pages Overview. Dark inverts the page background, swaps displayed black and white ink, and dims highlighter fills to keep white writing legible. Other colored ink and pasted images retain their own colors. Saves, exports and cutouts use the original colors.

## Image cutouts and protected PDFs

Tap **Select / move** twice and choose **Capture cutouts and arrange images**. Lasso visible content and **Paste** it on a visible layer. Use **New cutout** to start over an image. Tap an image to move, resize, rotate, copy, cut, delete or **Arrange** it. The editor clipboard clears on close. Captures are capped at four megapixels and about 3 MiB.

On iPhone and iPad, use **Choose from Photos…** or **Take a photo…** from the same **Select / move** menu. The photo goes on the active layer as a standard-dynamic-range PNG, with a long edge up to 1,600 pixels and a size up to 1.25 MiB. A picture taken here is stored in the notebook when you save.

Use **Unlock PDF** for an encrypted embedded PDF. Retry a wrong password in the same form. Save and Export keep the encrypted PDF and the password stays in session memory.

## Internal page links

Tap an internal PDF link with a finger. Pen input draws. **Undo page jump** is available for three seconds.
