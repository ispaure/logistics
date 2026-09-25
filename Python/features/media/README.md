# Media Feature

Provides media-specific file operations for Logistics.

## Responsibilities

- Handle audio/video media workflows that do not belong to a more specific feature.
- Keep media file processing out of the UI layer.
- Provide reusable validation and execution logic for media maintenance tools.

## Structure

- `mka.py` contains Matroska Audio (`.mka`) operations.
- `__init__.py` exposes the feature to the Logistics feature registry.

## MKA Chapter Rename

The current MKA workflow renames top-level files named like:

`Chapter_01.mka`

using chapter names from the single CSV file in the same directory.

The CSV is expected to contain:

- Column A: chapter number
- Column B: chapter name

Before any files are renamed, Logistics validates the entire batch:

- The target directory exists.
- Exactly one CSV file is present.
- Every MKA filename contains a valid chapter number.
- Every chapter has a matching CSV row.
- CSV chapter numbering matches the MKA chapter number.
- Every CSV row contains a chapter name.
- No destination filename already exists.

Only after the complete rename plan passes validation are files renamed.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry but performs no work until a Media action is used.
