# Comics Feature

Provides comic-related integration for Logistics.

## Responsibilities

- Expose comic-related operations through Logistics.
- Work with comic archives and comic metadata.
- Support comic-specific workflows such as CBZ processing and compression.
- Keep comic functionality optional rather than making it a requirement for Logistics itself.

## Initialization

This feature currently does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until comic functionality is actually used.

## Current Implementation

The feature currently relies on existing comic-related logic elsewhere in the project.

That implementation may be moved into this feature package later as part of a dedicated comics refactor.

## Notes

Comics is an optional Logistics feature.

Any current folder detection, configuration, or comic-specific behavior continues to use the existing Logistics mechanisms. That behavior is intentionally not being changed as part of the feature-system refactor.