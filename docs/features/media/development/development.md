# Media Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../development/features.md) for shared contribution conventions.

Provides media-specific file operations for Logistics.

## Responsibilities

- Own CSV-based audio chapter renaming.
- Provide reusable validation and execution logic for media maintenance tools.

## Structure

- `mka.py` contains Matroska Audio (`.mka`) operations.
- Playback belongs to the separate [Video Player feature](../../video/development/development.md).

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
- Destination filenames are portable, stay in their original folder, and are unique
  including case and Unicode equivalents.
- No destination filename already exists.

Only after the complete rename plan passes validation are files renamed. The shared
`plan_named_renames` / `apply_renames` engine revalidates source stamps and destinations
before execution, stages the batch, and rolls it back if publication fails. Any
unresolved recovery paths are reported rather than overwritten.

The [earlier video brief](video-player.md) redirects to the Video Player owner.
