# Images Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../../../docs/development/features.md) for shared contribution conventions.

Provides image-processing and image-metadata workflows for Logistics.

## Responsibilities

- Represent image files and inspect image dimensions/color characteristics.
- Batch compress supported image formats to WEBP.
- Apply JPG EXIF metadata through the reusable commonUtils piexif wrapper.
- Provide shared image-processing behavior to other Logistics features such as Comics.

## Structure

- `processing.py` contains `ImageFile` and image-compression behavior.
- `actions.py` exposes user-facing image and EXIF operations.

## Shared Usage

The Comics feature uses `features.images.processing` for image-file handling and compression support.

`ImageFile.compress(..., preserve_alpha=True)` preserves transparency in WebP by default, including RGBA, grayscale alpha, and palette/color-key transparency. Standalone image compression uses this default. Comics explicitly passes `preserve_alpha=False` for encoded pages, dropping alpha without compositing onto a background. Retained original comic pages remain unchanged. JPEG cannot store alpha and stays opaque regardless of this option.

Dot-file staging is implemented by shared `ImageFile.compress()`: it writes `.page.webp` beside the requested `page.webp`, verifies the encoded file, closes the input, then replaces the requested output. Existing dot files are refused and failed candidates are cleaned up. With `defer_replace=True`, it instead leaves the dot file in `compressed_image` so the caller can choose whether to publish it.

## Standalone compression

Standalone batch compression uses deferred replacement. The dialog checks “Exclude existing WebP images” by default, skipping `.webp` inputs (case-insensitively) before inspection, including those in subfolders when recursion is enabled. Uncheck it to recompress existing WebP files. The batch API keeps its existing behavior unless `exclude_webp=True` is supplied; this option does not affect Comics compression. It compares the dot file using the existing strict under-75% rule (or always-keep override), and only then publishes the output. Losing/failed candidates are removed and the original stays intact. Existing output files belonging to another source are refused. Dot-prefixed inputs are skipped. No temporary directory is used for image staging. Comics uses the same shared dot-and-rename step inside its existing compressed-images directory, then performs its normal page-retention selection; final comic member names are unchanged.

Animated/multipage originals are preserved by default in both workflow dialogs. Explicit preservation and always-keep compression cannot be enabled together. For API calls with the preservation argument omitted, normal compression preserves multiframe originals, while an explicit always-keep request permits first-frame conversion. Passing `preserve_animated_and_multipage_originals=False` also permits it. Static GIFs are processed normally.

## Metadata and color profiles

The shared encoder carries ICC profiles and EXIF into WebP/JPEG output. Applied EXIF orientation is removed to avoid a second rotation; existing EXIF dimensions are updated after resizing. RGB profiles are retained unchanged. CMYK/gray profiles are transformed to sRGB when writing WebP, which stores RGB pixels, and the matching sRGB profile is embedded. Invalid or unsupported profiles fail safely. This intentionally adds metadata bytes to the size comparison and may cause more originals to be retained.

## Publication and failure handling

Shared encoding and standalone publication/deletion check the source's identity, size, permissions, and modification/change timestamps, refusing observed changes during processing. Existing WebP filenames retain their original spelling, using normalized `File.ext` to recognize the format. The image dialog reports exceptions and failed/partial batches and stays open; it validates the target and numeric fields before running.

Standalone publication prefers an exclusive hard link from the completed candidate. When the filesystem does not support hard links, it exclusively creates the destination and copies, flushes, and closes the candidate before deleting the original. Failed copies remove partial outputs; existing destinations are never overwritten. The fallback destination is visible during copying, so publication is not atomic on those filesystems.

Low-level EXIF read/write behavior remains in:

`commonUtils.integrations.wrappers.piexifWrapper`

because that wrapper is reusable code and is not specific to Logistics UI behavior.

## Safety Notes

Image compression may replace original image files with WEBP versions when the compressed output meets the configured rules.

EXIF operations modify JPG metadata in place.

Use disposable copies when testing behavioral changes to these operations.

## Portable image validation

`validation.py` validates bounded PNG/JPEG/WebP dimensions before native decoding. Books, Comics and provider readers share it without loading Qt, Toga or image-processing tools. The existing 8 MiB, 8192-pixel-axis and 16-megapixel limits are unchanged.

## Mobile source manifest

`../../mobile_sources.json` declares this feature's selected portable/mobile sources. Update it when adding an imported module. The build tool aggregates and checks the allowlists without starting desktop registration.

## iPhone burst camera

`mobile/burst_camera.py` presents `LGBurstCameraController` from
`mobile/ios/BurstCamera.m` through Rubicon. The iOS-only entry is appended to
Home, after documents and status. `Mobile/camera_build.py` refreshes the native
source included by the generated launcher's existing compilation unit and adds
the two purpose strings. `Mobile/cloud_build.py` invokes it and links AVFoundation
and Photos. Do not edit generated launcher copies.

The native controller owns a serial capture queue. Touch-down requests capture
immediately; a timer based on the saved 1–30 pictures-per-second preference requests subsequent
frames when capture readiness,
the three-capture bound and eight-pending-save bound permit. These are request
limits, not a guaranteed frame rate. Balanced processed HEIF/JPEG capture uses
supported Zero Shutter Lag/responsive capture, with flash off. Fast capture
prioritization is not enabled. PhotoKit uses add-only permission and creates
individual assets. Encoded originals are atomically retained in Documents/Local/
Camera Pending until PhotoKit confirms success; failed saves stop the burst and
leave the files for manual recovery. Foreground loss stops capture and the
session; Done dismisses after requesting teardown while accepted captures finish.

Host validation: `test_burst_camera`, `test_hub_documents` and
`test_packaged_startup` in `Mobile/tests`. Native source must also compile and
run on iOS; a simulator cannot establish physical capture latency or quality.
See the [mobile user guide](../user_mobile/user_mobile.md).

### October 21, 2026 verification

Four focused Home/build/packaged-startup checks passed. Both device and arm64
simulator builds succeeded. The isolated `burst_camera_probe.py` verified native
Home presentation, camera-unavailable UI, shutter guards, dismissal, a synthetic
image saved through PhotoKit, successful-save original cleanup, and retention plus
burst stop after a forced Photos save failure. Local results/screenshots are in
`Mobile/logs/burst-camera-result.json`, `burst-home.png`, and `burst-camera.png`.
The signed app installed and launched in place over Wi-Fi on the paired iPhone
15 Pro Max. Sensor capture, physical shutter latency and comparison with Apple's
Camera image quality still require the on-device trial; simulator evidence does
not establish those results.

Camera and requested rate preferences (`burst_camera`, `burst_photos_per_second`)
are validated by the images owner and persisted through the host Preferences INI.
Settings → Camera discovers available physical lenses using the native controller;
a saved unavailable lens remains visible and falls back to rear main at launch.
The Python presenter applies settings before native view loading. Native interval
validation also defaults invalid/out-of-range rates to 8. The first capture remains
immediate, with the selected interval used only for subsequent requests.

The camera preferences follow-up passed 15 focused camera/settings/UI/packaged
startup checks. A native simulator run additionally verified that saved front
camera and 3-pictures-per-second choices reached the controller, including its
1/3-second repeat interval. Settings presentation was visually checked, and the
updated signed build was installed and launched on the paired iPhone 15 Pro Max.
Actual rate and quality on each physical lens remain part of on-device testing.

Camera settings use `commonUtils.ui.native.forms.FittedLabel`, the same label
class used by the mobile Settings host. The feature imports it directly and has
no dependency on the mobile application package. The architecture check and
`test_burst_camera.py` cover the boundary and preference controls.

Viewer lens/rate menus share `save_camera_preferences()` with Settings. A retained
Rubicon BOOL block writes the same validated INI keys before native changes apply;
retained Settings controls refresh with event suppression to avoid recursive saves.
The viewer updates its timer rate between bursts and reconfigures the existing
session for lens changes, retaining the photo output and restoring prior inputs
if a new input cannot attach. Menus are disabled through accepted capture completion.

Apple's Camera groups burst photos in Photos. The public Photos SDK exposes
`PHAsset.burstIdentifier` as read-only, and `PHAssetCreationRequest` /
`PHAssetChangeRequest` have no burst-creation setter. Logistics therefore saves
individual assets rather than using private APIs or undocumented maker-note tags.
See [Apple's burst identifier contract](https://developer.apple.com/documentation/photos/phasset/burstidentifier?language=objc).

The viewer-control follow-up passed 14 focused camera/settings/packaged-startup
checks plus native device and simulator builds. The native probe changed the
viewer rate from 3 to 5 and lens from front to rear main, verified both saved
preferences and retained Settings controls, and rechecked PhotoKit saves and
failure retention. The viewer screenshot was inspected and the signed update
installed and launched on the paired iPhone 15 Pro Max. Physical lens switching
and achieved capture rates remain on-device checks.
