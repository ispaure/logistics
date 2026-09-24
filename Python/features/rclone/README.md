# rclone Feature

Provides rclone integration for Logistics.

## Responsibilities

- Configure Logistics remotes in `rclone.conf`.
- Clear existing rclone mounts used by Logistics.
- Mount configured remotes.
- Build the current rclone remote objects used by Logistics.

## Initialization

The feature is loaded dynamically by the Logistics feature registry.

Its `initialize()` function preserves the existing rclone startup behavior.

## Current Implementation

The feature currently delegates to:

`wrappers/rcloneWrapper.py`

The implementation may be moved into this feature package later as part of a dedicated rclone refactor.

## Notes

rclone is an optional Logistics feature.

Logistics core should not depend on rclone being available in order to work with folders already present under `Server/Local`.