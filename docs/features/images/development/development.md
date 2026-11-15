# Develop Image Tools

Image Tools validates images for desktop and mobile viewing. Its desktop
processing actions also convert image files to WebP and edit JPEG comments.
Conversion settings determine how the worker encodes each image, then
publication checks whether the result can replace the source.

See the [desktop guide](../user/user.md) and [mobile guide](../user_mobile/user_mobile.md) for controls.

## Follow compression options

The desktop folder action **Batch Compress Images to WEBP…** opens
`Python/features/images/ui/dialogs.py:ImageCompressDialog`. It captures options
for the folder workflow and keeps results visible when work completes. The
focused fixture uses disposable images to check that resize and recursion
choices reach the worker and produce the expected files:

```sh
python3 dev.py test desktop --exact-file Python/tests/images/test_image_folder_dialog.py
```

## Compression and publication

`actions.compress_folders()` validates roots, skips links and hidden inputs, deduplicates overlaps and reports individual failures. Cancel after the current file. The dialog excludes existing WebP by default. Legacy APIs keep WebP eligible unless opted out.

`processing.ImageFile.compress()` uses commonUtils for encoding and chroma. WebP normally preserves alpha, ICC and EXIF with orientation and resized dimensions normalized. The dialog preserves animated and multipage inputs by default. Explicit preservation conflicts with always-keep. With the preservation argument omitted, API always-keep may encode the first frame.

Keep verified exclusive dot-stage output only below 75% of source size or on override. Same-path replacement is atomic. New-path publication uses an exclusive hard link or exclusive copy, cleaning partial copies on failure. Recheck source revision before deleting it. `ExifCommentsDialog` calls `actions.set_jpg_exif_comments_batch()` and keeps a `.before-comments` backup on the first changed edit.

## Compression regression coverage

Run `python3 dev.py test-owner images`. Under `Python/tests/images/`, use `test_image_folder_tool.py` for scan/cancel, `test_image_staging.py` for publication and `test_image_audit_fixes.py` and `test_image_alpha.py` for revisions, multiframe and transparency.

## Viewer and camera

- `ui/viewer.py` and `mobile/navigation.py` publish the replacement before retiring the current view. Private views release content on revocation. `validation.py` bounds PNG/JPEG/WebP to 8 MiB, 8192 per axis and 16 megapixels, with animated WebP rejected. `orientation.py` and platform decoders share display orientation. Check `test_viewer_orientation.py` and mobile `test_image_documents.py`.
- iOS Home calls `mobile/burst_camera.py` and `mobile/ios/BurstCamera.m`. Update native source and permission packaging via `mobile_build/build_support/camera_build.py`. Requests run at 1–30 per second subject to backpressure. Encoded originals stay in `Documents/Local/Camera Pending` until Photos confirms. Failed saves stop capture and leave local files. Run `python3 dev.py test mobile --exact-file mobile_build/tests/native/test_burst_camera.py`. Capture, switching and achieved rate require an iPhone.
