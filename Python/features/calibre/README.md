# Calibre Feature

Provides Calibre integration for Logistics.

## Responsibilities

- Detect Calibre libraries contained directly within Logistics Local folders.
- Represent and operate on Calibre libraries.
- Launch libraries in Calibre.
- Export supported book formats to external reading devices.
- Keep Calibre-specific behavior isolated from Logistics core.

## Structure

- `detection.py` detects Calibre libraries by looking for `metadata.db` in immediate child folders.
- `library.py` contains the `CalibreLibrary` model and Calibre-specific library operations.
- `metadata.py` reads OPF titles/series and normalizes export filenames.
- `export.py` builds a read-only export plan and stages verified copies before replacing files and pruning obsolete exports.
- `launching.py` resolves native/bundled/Flatpak executables and launches them with argument lists.
- `actions.py` exposes Calibre operations to the Logistics UI.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Library Detection

A Logistics Local folder is considered Calibre-supported when at least one of its immediate child folders contains:

`metadata.db`

Only immediate child folders are checked. Calibre support no longer depends on a `Calibre` section in `remoteConfig.ini`.

## Initialization

This feature does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until Calibre functionality is used.

## Notes

Calibre is an optional Logistics feature.

Book exports use a dedicated destination as a complete one-way mirror. Obsolete
files, including files with other extensions, are removed only after all changed
books have been copied successfully. Do not mix unrelated files into that folder.

Planning validates the library marker, source/destination separation, filenames,
and existing destination entries before writing. Linked library/export roots and
linked entries are rejected. Collisions, including case or Unicode-equivalent
filenames, abort the export rather than silently choosing a book. Malformed or
missing OPF metadata falls back to the sanitized book folder name.

Checksums detect changed books even when sizes match. All changed copies are
staged and verified before replacements begin; staging requires temporary space
for those copies. Each replacement is atomic, but the complete mirror is not one
filesystem transaction. A replacement or deletion failure can leave a partial
update; failed copy staging preserves existing exports and skips pruning. Changes
to planned source/destination files are checked before writes and deletions.
The destination's directory/device identity is also checked during execution;
removing or replacing it stops the export. Staging files on a disconnected device
may remain until a later export can clean them.

BOOX export requires `/Volumes/BOOX-SD` to be mounted and reports failures in the
folder UI. Linux launching prefers native Calibre, then checks the Flatpak using
`flatpak info`, covering user and system installations. Windows uses the bundled
executable; macOS retains the existing bundled-archive installation fallback.

`Python/tests/test_calibre.py` uses disposable libraries/device folders and mocked
launchers. It covers naming, collisions, links, copy failures, changed files,
disconnected storage and Linux launcher selection. Actual device exports and
desktop launching still require platform validation.
