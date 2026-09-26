# rclone Feature

Provides base rclone integration for Logistics.

## Responsibilities

- Configure Logistics remotes in `rclone.conf`.
- Discover configured remote names for the generic Folders view.
- Push and pull folder data with rclone sync.
- Manage rclone credentials and configuration.
- Provide the rclone executable/configuration/sync primitives used by dependent features.

## UI Contributions

The feature contributes:

- rclone remote names as a remote-folder source.
- `Push...` and `Pull` actions for matching Folder entries.
- the standalone rclone credentials/configuration page.

Filesystem mounting is intentionally not part of this feature. The optional
`fuse` feature depends on rclone and provides mounted remote-folder behavior.

## Initialization

The feature is loaded dynamically by the Logistics feature registry.

Initialization ensures the Logistics rclone credentials/configuration are
available. It does not perform filesystem mounting.

## Dependencies

rclone has no feature dependencies.

Other features may explicitly depend on it when they use rclone behavior:

- `fuse` requires rclone.
- `plex` currently requires rclone for PMS backup/restore synchronization.
- `youtube_downloader` optionally uses rclone for remote sync actions.

## Notes

Logistics core does not depend on rclone. Local folders continue to work when
the rclone feature is not distributed with the application.
