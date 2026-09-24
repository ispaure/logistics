# Minecraft Feature

Provides Minecraft-related integration for Logistics.

## Responsibilities

- Expose Minecraft-related operations through Logistics.
- Manage Minecraft server workflows.
- Keep Minecraft-specific behavior isolated from Logistics core.
- Allow Minecraft support to remain optional.

## Initialization

This feature currently does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until Minecraft functionality is actually used.

## Current Implementation

The feature currently relies on existing Minecraft logic elsewhere in the project.

That implementation may be moved into this feature package later as part of a dedicated Minecraft refactor.

## Notes

Minecraft is an optional Logistics feature.

Any current Minecraft configuration, server detection, or folder-specific behavior continues to use the existing Logistics mechanisms. That behavior is intentionally not being changed as part of the feature-system refactor.