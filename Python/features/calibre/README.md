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

Book export operations can modify the destination by copying changed books and removing obsolete files. These operations should be tested carefully when making behavioral changes.
