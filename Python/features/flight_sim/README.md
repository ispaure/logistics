# Flight Simulator Feature

Provides flight-simulator-related integration for Logistics.

## Responsibilities

- Expose flight simulator operations through Logistics.
- Manage flight simulator configuration and preset workflows.
- Keep flight-simulator-specific behavior isolated from Logistics core.
- Allow flight simulator support to remain optional.

## Initialization

This feature currently does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until flight simulator functionality is actually used.

## Current Implementation

The feature currently relies on existing flight simulator logic elsewhere in the project.

That implementation may be moved into this feature package later as part of a dedicated flight simulator refactor.

## Notes

Flight Simulator is an optional Logistics feature.

Any current configuration, detection, or folder-specific behavior continues to use the existing Logistics mechanisms. That behavior is intentionally not being changed as part of the feature-system refactor.