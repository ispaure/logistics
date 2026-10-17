# Compress images and edit JPG comments

Enable **Image Tools** under **Settings → Features** to use these tools.

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
comment. Changes are validated and saved atomically. The first edit keeps the original
as `<filename>.before-comments` beside the JPEG; retain it if you need to undo. WEBP conversion can stop after the current image; completed conversions remain.

For CBZ page compression, use [Comics](../../../comics/docs/user/user.md).

## More help

See [Using Logistics](../../../../../docs/user/user.md) for navigation and settings.


System/application folders are protected by `Python/maintenance.ini`. External drives
and ordinary user folders are allowed. Additional protected paths and the system
folder policy can be configured there. Directory links are not traversed.

## Choose compression settings

Color and grayscale quality are separate values from 1 to 100 (defaults 80 and
45). Lower quality can reduce size at the cost of detail. Long-edge and height
limits resize oversized images without upscaling; a disabled limit has no effect.
The initial long-edge cap is 5120 pixels; the height cap is initially disabled.
**Always keep compressed images** bypasses the size-savings test and can produce
a larger output. It cannot be combined with preserving animated/multipage originals.
Recursion increases the number of files changed. There is no conversion Undo:
keep backups if original image bytes or formats matter.
