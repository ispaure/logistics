# Plex Feature

Provides Plex integration for Logistics.

## Responsibilities

- Detect folders with a matching `-PMSDATA` rclone remote.
- Back up and restore Plex Media Server application data.
- Preserve platform-specific Windows and macOS PMS packaging behavior.
- Expose the Plex database comparison/test workflow through Debug.
- Keep Plex-specific behavior outside Logistics core and generic UI code.

## Structure

- `detection.py` detects Plex PMS support and platform data locations.
- `folders.py` resolves local and mounted `-PMSDATA` helper folders.
- `actions.py` contains PMS backup, restore, package, and sync operations.
- `database.py` contains the existing Plex database inspection/comparison tools.
- `ui_contributions.py` contributes Manage PMS to matching folders and the database test to Debug.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Manage PMS

A local Logistics folder receives the Manage PMS workflow when a matching
`<folder>-PMSDATA` rclone remote exists.

The workflow supports:

- Opening local and mounted `-PMSDATA` locations.
- Clearing the local package.
- Pulling the remote package locally.
- Unpacking the local package into the platform Plex Media Server data location.
- Packaging current Plex Media Server data locally.
- Pushing the local package to the paired remote.

Plex intentionally depends on rclone for these backup and restore sync operations.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry and performs no work until
Plex functionality is used.
