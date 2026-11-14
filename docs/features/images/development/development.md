# Develop Image Tools

See the [desktop guide](../user/user.md) and [mobile guide](../user_mobile/user_mobile.md) for controls.

## Try a compression default change

On desktop, enable **Image Tools**, place a disposable 100 × 100 PNG in a test folder and choose **Batch Compress Images to WEBP…** on the folder. Set the initial `self.max_long_edge` to 24 in `Python/features/images/ui/dialogs.py:ImageCompressDialog`. Relaunch, disable height and multiframe preservation, enable **Always keep compressed images**, then compress. Expect a 24 × 24 WebP.

In `test_selected_options_reach_folder_workflow_and_results_remain_visible`, assert the initial 24 instead of setting it, raise the test height cap to 30 and update worker arguments and output dimensions. Run from the checkout root:

```sh
python3 dev.py test desktop --exact-file Python/tests/images/test_image_folder_dialog.py
```

Expect the 24 × 24 conversion, untouched nested PNG and retained results.

## Compression and publication

`actions.compress_folders()` validates roots, skips links and hidden inputs, deduplicates overlaps and reports individual failures. Cancel after the current file. The dialog excludes existing WebP by default. Legacy APIs keep WebP eligible unless opted out.

`processing.ImageFile.compress()` uses commonUtils for encoding and chroma. WebP normally preserves alpha, ICC and EXIF with orientation and resized dimensions normalized. The dialog preserves animated and multipage inputs by default. Explicit preservation conflicts with always-keep. With the preservation argument omitted, API always-keep may encode the first frame.

Keep verified exclusive dot-stage output only below 75% of source size or on override. Same-path replacement is atomic. New-path publication uses an exclusive hard link or exclusive copy, cleaning partial copies on failure. Recheck source revision before deleting it. `ExifCommentsDialog` calls `actions.set_jpg_exif_comments_batch()` and keeps a `.before-comments` backup on the first changed edit.

## Compression regression coverage

Run `python3 dev.py test-owner images`. Under `Python/tests/images/`, use `test_image_folder_tool.py` for scan/cancel, `test_image_staging.py` for publication and `test_image_audit_fixes.py` and `test_image_alpha.py` for revisions, multiframe and transparency.

## Viewer and camera

- `ui/viewer.py` and `mobile/navigation.py` publish the replacement before retiring the current view. Private views release content on revocation. `validation.py` bounds PNG/JPEG/WebP to 8 MiB, 8192 per axis and 16 megapixels, with animated WebP rejected. `orientation.py` and platform decoders share display orientation. Check `test_viewer_orientation.py` and mobile `test_image_documents.py`.
- iOS Home calls `mobile/burst_camera.py` and `mobile/ios/BurstCamera.m`. Update native source and permission packaging via `mobile_build/build_support/camera_build.py`. Requests run at 1–30 per second subject to backpressure. Encoded originals stay in `Documents/Local/Camera Pending` until Photos confirms. Failed saves stop capture and leave local files. Run `python3 dev.py test mobile --exact-file mobile_build/tests/native/test_burst_camera.py`. Capture, switching and achieved rate require an iPhone.
