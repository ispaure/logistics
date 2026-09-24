# Plex Feature

Provides Plex integration for Logistics.

## Responsibilities

- Expose Plex-related operations through Logistics.
- Read and work with Plex library and database information.
- Support Plex-specific workflows without making Plex a requirement for Logistics itself.

## Initialization

This feature currently does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until Plex functionality is actually used.

## Current Implementation

The feature currently relies on existing Plex logic elsewhere in the project.

That implementation may be moved into this feature package later as part of a dedicated Plex refactor.

## Notes

Plex is an optional Logistics feature.

Any current Plex detection, configuration, or folder-specific behavior continues to use the existing Logistics mechanisms. That behavior is intentionally not being changed as part of the feature-system refactor.