# Images Feature

Provides image-processing and image-metadata workflows for Logistics.

## Responsibilities

- Represent image files and inspect image dimensions/color characteristics.
- Batch compress supported image formats to WEBP.
- Apply JPG EXIF metadata through the reusable commonUtils piexif wrapper.
- Provide shared image-processing behavior to other Logistics features such as Comics.
- Keep image-specific behavior out of debug popup UI code.

## Structure

- `processing.py` contains `ImageFile` and image-compression behavior.
- `actions.py` exposes user-facing image and EXIF operations.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Shared Usage

The Comics feature uses `features.images.processing` for image-file handling and compression support.

`ImageFile.compress(..., preserve_alpha=True)` preserves transparency in WebP by default, including RGBA, grayscale alpha, and palette/color-key transparency. Standalone image compression uses this default. Comics explicitly passes `preserve_alpha=False` for encoded pages, dropping alpha without compositing onto a background. Retained original comic pages remain unchanged. JPEG cannot store alpha and stays opaque regardless of this option.

Dot-file staging is implemented by shared `ImageFile.compress()`: it writes `.page.webp` beside the requested `page.webp`, verifies the encoded file, closes the input, then replaces the requested output. Existing dot files are refused and failed candidates are cleaned up. With `defer_replace=True`, it instead leaves the dot file in `compressed_image` so the caller can choose whether to publish it.

Standalone batch compression includes existing WebP inputs and uses deferred replacement. It compares the dot file using the existing strict under-75% rule (or always-keep override), and only then publishes the output. Losing/failed candidates are removed and the original stays intact. Existing output files belonging to another source are refused. Dot-prefixed inputs are skipped. No temporary directory is used for image staging. Comics uses the same shared dot-and-rename step inside its existing compressed-images directory, then performs its normal page-retention selection; final comic member names are unchanged.

Low-level EXIF read/write behavior remains in:

`commonUtils.wrappers.piexifWrapper`

because that wrapper is reusable code and is not specific to Logistics UI behavior.

## Safety Notes

Image compression may replace original image files with WEBP versions when the compressed output meets the configured rules.

EXIF operations modify JPG metadata in place.

Use disposable copies when testing behavioral changes to these operations.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry but performs no work until an Images action is used.
