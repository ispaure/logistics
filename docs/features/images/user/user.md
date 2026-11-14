# View and process images

Enable **Image Tools** in **Settings → Features**.

## View images

Open a static PNG, JPEG or WebP from File Browser, LocalCrypt or a remote browser. **Previous image** and **Next image** follow natural filename order in the folder. Use **Fit image** to resize the view. Files are read-only, up to 8 MiB, 8192 pixels per axis and 16 megapixels. Decrypted and remote bytes stay in memory.

## Compress images

Right-click a folder in **File Browser → Batch Compress Images to WEBP…**. Review recursion, quality, resize and retention before starting. Cancel stops after the current image. The desktop tool reads JPEG, PNG, WebP, BMP, TIFF and GIF.

## Set JPG comments

Use **Debug → JPG EXIF - Set Comments…** and enter the Windows EXIF Comments field value. The first edit saves a `<filename>.before-comments` backup. Earlier files remain edited if a later file fails.

## More help

- [Using Logistics](../../../user/user.md)
- [Compress CBZ pages](../../comics/user/user.md)

## Choose compression settings

By default, existing WebP and animated or multipage originals are skipped. Other successful conversions replace originals only when the output is under 75% of source size. **Always keep compressed images** bypasses that threshold and requires disabling animation preservation, allowing first-frame conversion. Keep backups because there is no Undo. Long-edge and height limits only shrink images. Protected folders are configured in `Python/maintenance.ini`.
