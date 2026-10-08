# Compress images and edit JPG comments

These tools work on an input folder selected in a Debug dialog. Comics uses the
same image encoder through its own workflow.

## Compress images

1. Choose **Debug → Batch Compress Images…**.
2. Select the target folder and whether to include subfolders.
3. Review quality, resize limits and retention options.
4. Start compression and read the final result, including individual failures.

**Exclude existing WebP images** is checked initially. Animated/multipage originals
are preserved by default. That option cannot be combined with **Always keep
compressed images**; disabling preservation permits first-frame conversion.
Normally, the WebP must be strictly under 75% of the original's size to be retained.
Successful retained outputs replace their source images; unsuccessful candidates
leave the original in place. Existing unrelated outputs are refused.

WebP transparency is preserved. Color profiles and EXIF are carried into encoded
output, with orientation/dimensions adjusted for the processed image. Invalid
profiles can cause a file to fail safely.

## Set JPG comments

Choose **Debug → JPG EXIF - Set Comments…**, select your folder and enter the
comment. This edits JPG metadata in place. Use a backup for changes you may need
to undo. These image dialogs do not offer the comic batch's after-current-comic
cancellation controls.

For CBZ page compression, use [Comics](../../comics/user_docs/index.md).

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
