# Compress images and edit JPG comments

WEBP compression opens from a folder’s File Browser context menu. EXIF comments
remain a Debug tool. Comics uses the
same image encoder through its own workflow.

## Compress images

1. Right-click a folder in **File Browser → Batch Compress Images to WEBP…**.
2. Select the target folder and whether to include subfolders.
3. Review quality, resize limits and retention options.
4. Start compression and review the results table, including individual failures.
   The window stays open. Cancel stops after the current image.

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
to undo. WEBP conversion can stop after the current image; completed conversions remain.

For CBZ page compression, use [Comics](../../comics/user_docs/index.md).

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.

System/application folders are protected by `Python/maintenance.ini`. External drives
and ordinary user folders are allowed. Additional protected paths and the system
folder policy can be configured there. Directory links are not traversed.
