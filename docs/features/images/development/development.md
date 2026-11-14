# Develop Image Tools

Image Tools opens read-only image documents on desktop, Android and iOS.
Desktop also offers folder compression and JPEG comment editing. The iOS Home
screen has a burst camera. See the [desktop user guide](../user/user.md) and
[mobile user guide](../user_mobile/user_mobile.md) for controls.

## Try a compression default change

On desktop, enable **Image Tools** under **Settings → Features**. Put a
disposable 100 × 100 PNG in an ordinary test folder and right-click the folder
in **File Browser → Batch Compress Images to WEBP…**. The enabled long-edge
limit starts at 5120 pixels. The action is registered in
`Python/features/images/ui_contributions.py` and opens `ImageCompressDialog`
in `Python/features/images/ui/dialogs.py`.

For a small experiment, change the initial `self.max_long_edge` field to
`24` in `ImageCompressDialog.__init__()`, then relaunch and reopen the dialog.
Leave the height limit disabled, uncheck **Preserve animated and multipage
originals**, and check **Always keep compressed images** so the size-savings
rule cannot discard the fixture. Click **Batch Compress** and confirm the
operation on your disposable copy.
Expect a **Converted to WEBP** result and a 24 × 24 WebP in place of the PNG.

In `test_selected_options_reach_folder_workflow_and_results_remain_visible`,
assert the new initial long-edge value instead of setting it to 24. Set the
test height cap to 30 instead of 18 so the long-edge default determines the
output size. Update the expected worker arguments and dimensions. Run from the
repository root with the desktop environment installed.

```sh
python3 dev.py test desktop --exact-file Python/tests/images/test_image_folder_dialog.py
```

Expect the synthetic conversion to produce a 24 × 24 WebP, leave the nested
PNG untouched and keep the results visible. The same test file covers invalid
options and partial EXIF results.

## Standalone compression

`ImageCompressDialog._execute()` validates options and passes them to
`actions.compress_folders()` on a worker. The folder workflow checks all roots
before processing, skips hidden inputs and links, deduplicates overlapping roots
and continues after individual file failures. Cancellation lets the current
file finish. The dialog displays the results after a failure or partial batch.
The legacy `processing.batch_compress_image()` inspects files before converting
and stops on failure.

The dialog defaults to excluding existing WebP files, including uppercase
extensions and files in included subfolders. The legacy batch API keeps those
inputs eligible unless `exclude_webp=True` is supplied. Existing WebP filenames
retain their original spelling when recompressed. Animated and multipage originals
are preserved by default in the standalone and Comics dialogs. An API call
with the preservation argument omitted allows first-frame conversion when
always-keep is enabled. Passing `preserve_animated_and_multipage_originals=False`
also permits conversion. Explicit preservation and always-keep conflict.
Static GIFs follow the normal compression path.

## Encoding versus compression policy

`processing.ImageFile.compress()` delegates Pillow encoding and chroma
classification to the shared format owner. Logistics selects quality and
resizing policy, allocates the exclusive dot-prefixed stage after pixel
preparation, verifies output and source revisions, and controls publication.
WebP preserves RGB, grayscale and palette transparency by default. Comics
passes `preserve_alpha=False` for encoded pages, dropping alpha without
compositing. Retained comic pages keep their original bytes and member names.
JPEG output is opaque.

## Metadata and color profiles

The encoder carries ICC and EXIF into WebP and JPEG. Applied EXIF orientation
is removed to avoid rotating twice and existing EXIF dimensions are updated
after resizing. RGB profiles are retained. For WebP, CMYK and grayscale
profiles are converted with the pixels to sRGB and the matching profile is
embedded. Invalid and unsupported profiles fail safely. The size comparison
includes the encoded metadata.

## Publication and failure handling

The shared encoder stages `.page.webp` next to the requested `page.webp`.
It refuses an existing stage, cleans up a failed candidate and closes the
input before replacing the requested output. With `defer_replace=True`, it
leaves the verified stage in `compressed_image`. Standalone compression uses
this option to keep the candidate only when it is strictly under 75% of the
source size or always-keep is enabled. Comics uses the shared dot-and-rename
step in its compressed-image directory, then applies its own retention policy.

`processing.compress_image()` checks source identity, size, permissions and
timestamps around encoding and publication. For an in-place WebP conversion
it replaces the source with the completed stage. For a different filename,
shared persistence publishes through an exclusive hard link or falls back to
exclusive create and copy when hard links are unavailable. The fallback output
is visible during the copy. A failed copy removes partial output and preserves
the original. Existing unrelated destinations are refused. The feature
rechecks the source before deleting it and preserves an observed edit.

## Safety Notes

**Debug → JPG EXIF - Set Comments…** opens `ExifCommentsDialog` in
`ui/dialogs.py`. The worker uses `actions.set_jpg_exif_comments_batch()` and
reports changed, unchanged, failed and unprocessed JPEGs. Cancellation during
scan edits nothing. After editing starts, the current edit finishes and
completed edits remain. The first changed edit keeps an original
`<filename>.before-comments` backup. The synchronous
`set_jpg_exif_comments()` API remains available. Low-level reads and writes
belong to `commonUtils.integrations.wrappers.piexifWrapper`.

## Compression regression coverage

Run the [images owner selection](../../../development/testing.md#find-the-tests-for-your-change)
with `python3 dev.py test-owner images`. Choose the individual tests under
`Python/tests/images/` based on the change.

| Change | Check |
| --- | --- |
| Folder scanning, cancellation, per-file failure and backups | `test_image_folder_tool.py` uses portable temporary folders. `test_image_folder_dialog.py` verifies the Qt worker and result handling. |
| Staging, size comparison or publication | `test_image_staging.py` uses real and stubbed encodes to exercise exclusive staging, replacement and copy fallback. |
| Source changes, multiframe defaults or metadata | `test_image_audit_fixes.py` covers those contracts. `test_image_alpha.py` exercises transparency and Comics' opt-out. |

The exhaustive color-classification and fallback error dispatch tests belong to
commonUtils (`test_image_color_detection.py` and `test_exclusive_copy.py`).
Logistics tests cover representative real encodes and source preservation.

## Image document sessions

On desktop, start with **File Browser** image activation or **New / Open
Document → Image Viewer**. `ui_contributions.py` registers PNG, JPEG and WebP
activation and the document launcher. LocalCrypt and remote browsers use the
same `ui/viewer.py` owner. It reads through the selected resource provider on
a cancellable worker, publishes pixels after success, retains the provider until
close and clears pixels on credential revocation. `document.py` owns the
read-only document and natural same-folder selection.

On Android and iOS, follow the [mobile reader runtime](../../../development/mobile-runtime.md)
to provider opening and presentation. `mobile/navigation.py` installs previous
and next actions for the `image` session kind. It serializes navigation,
checks session tokens and selection after listing asynchronously, and opens a
replacement before retiring the previous session.

`Python/tests/readers/test_image_viewer.py` covers ordering, storage chrome,
failed replacement and provider release.
`mobile_build/tests/reading/test_image_documents.py` tests local, LocalCrypt
and remote reads, replacement failure and Home Server read-only/session-only
identity using host backends. Update `Python/features/images/mobile_sources.json`
when adding an imported mobile module. See
[mobile preparation](../../../development/mobile-preparation.md) for allowlist
and packaging checks.

## Portable image validation

`validation.py` checks PNG, JPEG and WebP headers before decoding and reports
display-oriented dimensions. Readers share limits of 8 MiB, 8192 pixels per
axis and 16 million pixels per image, and reject animated WebP. These limits
cover image documents and provider reading. Desktop batch encoding uses its own
format and resize policy.

## Display orientation

`orientation.py` reads bounded EXIF orientation from JPEG APP1, WebP EXIF
and PNG eXIf metadata. Missing or malformed optional orientation metadata uses the
encoded orientation. `ui/decoding.py` handles explicit desktop transforms,
including WebP orientation ignored by Qt. Other formats can use Qt's native
transforms and Comics retains a Pillow fallback. Browser previews use the
same desktop owner before caching PNG pixels.

`mobile/decoding.py` uses ImageIO thumbnail transforms on iOS and a bitmap
matrix on Android. Comics uses oriented dimensions for spread selection and
portrait splitting. Native rclone thumbnails map oriented output coordinates
back to the source without a second full-size image. The orientation fixture
in `Python/tests/images/test_viewer_orientation.py` checks display geometry
and asymmetric corner colors across all eight orientations. Host checks do
not establish native appearance or large-photo latency and memory use.

## iPhone burst camera

On iOS, the **Burst camera** action at the end of Home calls
`features.images.mobile.burst_camera.present()` through `Python/mobile/home.py`.
The Python presenter uses Rubicon to load `LGBurstCameraController` in
`mobile/ios/BurstCamera.m`. Edit that source and its build hook in
`mobile_build/build_support/camera_build.py`. The hook refreshes the generated
launcher's native source and camera/Photos permission strings. The cloud build
links AVFoundation and Photos.

The controller requests the first frame immediately. A timer requests further
frames at the preferred 1–30 photos per second, subject to capture readiness,
three captures in flight and eight pending saves. The rate sets a request
interval. Processed HEIF/JPEG uses balanced capture, flash off, and Zero
Shutter Lag and responsive capture where supported. Accepted captures can
finish after Done. Foreground loss stops capture and the session.

PhotoKit uses add-only permission. The controller keeps each encoded original
in `Documents/Local/Camera Pending` until Photos confirms the save. A failed
save stops the burst and leaves files for manual recovery. Photos receives
individual assets. The public SDK exposes a read-only
[burst identifier](https://developer.apple.com/documentation/photos/phasset/burstidentifier?language=objc).

**Settings → Camera** and the viewer use `save_camera_preferences()` for
`burst_camera` and `burst_photos_per_second` in the host Preferences INI.
The settings form uses `commonUtils.ui.native.forms.FittedLabel` directly.
The presenter applies settings before view loading. An unavailable saved lens
remains visible in Settings and the controller falls back to rear main. An
invalid rate falls back to 8. Viewer menus stay disabled through accepted
capture completion. Between bursts the viewer can change the timer rate or
reconfigure the session's lens, retaining its photo output and restoring prior
inputs if the new input fails to attach. Settings controls refresh with events
suppressed to avoid recursive saves.

Run the host entry, preferences and build-hook tests from the repository root.

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/native/test_burst_camera.py
```

`test_hub_documents.py` and `test_packaged_startup.py` cover broader Home and
payload startup behavior. Native changes still need an iOS compile and launch.
The synthetic Photos-save path can exercise save and failure recovery. Physical
lens capture, lens switching, achieved rate, shutter latency and image quality
require a real iPhone.
