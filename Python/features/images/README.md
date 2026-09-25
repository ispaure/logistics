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
