# Calibre Feature

Provides Calibre integration for Logistics.

## Responsibilities

- Detect Calibre libraries associated with Logistics folders.
- Expose Calibre-related operations through Logistics.
- Manage Calibre-specific behavior without making Calibre a requirement for Logistics itself.

## Initialization

This feature currently does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until Calibre functionality is actually used.

## Current Implementation

The feature currently relies on existing Calibre logic elsewhere in the project.

That implementation may be moved into this feature package later as part of a dedicated Calibre refactor.

## Notes

Calibre is an optional Logistics feature.

Per-folder Calibre detection currently continues to use the existing Logistics mechanisms. That behavior is intentionally not being changed as part of the feature-system refactor.