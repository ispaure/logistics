# reMarkable notebooks on desktop

Choose **Notebook (.rmdoc)** in **New / Open Document**. Use **New** to name a draft and choose the first template and paper size. Use **Open** or activate an existing `.rmdoc` in File Browser. First Save asks for a location. Closing a modified draft offers Save, Discard or Cancel.

### Retrieve a notebook from a reMarkable tablet

1. Close the notebook on the tablet and let edits and sync finish. Connect USB and keep the tablet awake.
2. Open **Debug → Notebooks → Retrieve RMDOC from reMarkable Tablet…**. The defaults are address `10.11.99.1`, port `22` and username `root`. Enter a host or IP without a URL scheme, then click **Connect**.
3. Browse to the notebook, click **Retrieve…** and choose a `.rmdoc` filename. The destination is replaced only after successful verification and confirmation. An interrupted transfer preserves an existing destination.

OpenSSH and working SSH access are required. macOS can prompt for the password and host verification. Other desktops can use keys or a configured password prompt. Paper Pro needs Developer Mode already enabled. Enabling it factory-resets the tablet. [reMarkable Developer Mode](https://developer.remarkable.com/documentation/developer-mode)

Retrieval reads native ink, images and embedded PDF from the tablet without editing the device. A retrieved archive can exceed editor limits.

### Editing and storage

- Choose a brush with **1–9** or the toolbar. **B** draws, **E** opens eraser settings and **V** selects. Choose the active layer or use the adjacent menu to add or hide layers.
- **Select and Move** lassos fully enclosed strokes on visible layers. Drag inside the box to move, drag a corner to scale or use the round rotation handle. Use **Copy**, **Cut** or **Delete**. **Paste strokes** uses the original page position. The clipboard lasts until close.
- **Pages Overview** shows thumbnails and loads more on demand. **Add Page** inserts after the current page and inherits its template. **Page** also duplicates, deletes, reorders and copies to an open notebook. Keep at least one page.
- **Fit page** is the default. Choose **Fit width**, pinch, or use **Ctrl/⌘ +**, **Ctrl/⌘ −** and **Ctrl/⌘ 0**. Ctrl/Command while scrolling zooms around the pointer. Manual zoom spans 10%–400%. **View** controls Grayscale Preview, Draw with Finger and toolbar visibility.
- **File → Save** (**Ctrl/⌘+S**) or **Save As…** (**Ctrl/⌘+Shift+S**) uses Local or unlocked LocalCrypt. **Export Copy…** writes a separate copy. Undo/Redo keeps up to 50 edits in the current session.

Local existing notebooks support recovery. Private drafts stay in memory until saved. LocalCrypt verifies ciphertext before publication and asks before writing a decrypted export. Cloud notebook editing is unavailable.

## Paper Pro / Move brush settings

Pens, pencils and paintbrush offer nine opaque colors. Highlighter uses tints and one **Fixed** width. Shader builds translucent color with overlapping strokes and offers neither black nor white. Other brushes use **Thin**, **Medium** or **Thick**. Fineliner and mechanical pencil keep an even width. Other writing tools respond to pressure, and calligraphy responds to direction. Per-brush colors follow saved notebook positions.

Editor rendering approximates tablet brushes. **Grayscale Preview** affects display. Exports keep native geometry and colors.

## Current compatibility limits

Supported ordinary v6 ink is editable in legacy and modern `cPages` notebooks. Unsupported objects or invalid scenes are preserved and the affected page may disable ink editing and cross-notebook copying. EPUB-backed archives are unsupported.

Use **⋯ → Duplicate as .rmdoc to annotate** in a PDF Reader to create an editable sibling with the PDF as its background. A writable folder is required and an existing notebook is preserved. PDF-backed pages can be duplicated or reordered within their notebook.

RMDOC limits are 128 MiB compressed, 256 MiB expanded and 65,536 entries. Embedded PDFs and storage providers have separate limits. Physical Boox and reMarkable compatibility remains under validation. See the [development guide](../development/development.md).

## Page templates and paper sizes

Use **Page → Page Template…** or the toolbar's **Page template** to change the current page. **Template format** selects Pro or Move on supported layouts. **Show template** hides the background only. These edits support Undo and are inherited by inserted pages. PDF backgrounds are fixed.

**Paper view** selects display framing for all pages in the open notebook. Move centers the smaller writing area and expands for existing outlying ink. Pro shows the margins. Reopening restores device defaults.

**Save / Save As** keeps editable template settings. **Export Copy…** embeds custom layouts as fixed vector PDF backgrounds with separate native ink. Keep the original to change templates later. Export can refuse unavailable artwork, unsupported object bounds or ink above the top edge. Choose supported artwork or hide it when appropriate. Existing PDF-backed copies retain their original PDF.

## Eraser types and sizes

Press **Erase** and choose **Erase parts of strokes** or **Erase whole strokes**. Select Small, Medium or Large. Close settings with **Done** or Escape and keep erasing. Both respect hidden layers and support Undo.

## Saving from Notes Library

Navigating away from a writable persistent notebook saves it. A failed save keeps the draft open. Session-only storage prompts before leaving a dirty notebook.

## Paper Pro preview

**Settings → Notebooks → Notebook preview** sets muted or vivid display colors. Reopen to apply it. Exported colors retain their original values.

## Image cutouts and protected PDFs

Use **Capture** to lasso visible ink, images and background. **Paste** places the cutout on the active visible layer. **Add image** accepts PNG/JPEG. **New cutout** starts a new lasso over an existing image. Select an image to move, scale, rotate, copy, cut, delete or **Arrange** it within its layer. The editor clipboard lasts until close. Captures are capped at four megapixels and about 3 MiB.

Use **Unlock PDF** for an encrypted embedded PDF. Password and decrypted preview stay in memory, and Save/Export keep the embedded PDF encrypted. Reopen and unlock again to view it.

## Internal page links

In PDF-backed notebooks, **Command-click** on macOS or **Ctrl-click** on Windows/Linux follows a link. **Undo page jump** is available for three seconds.
