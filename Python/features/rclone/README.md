# rclone Feature

Provides rclone integration for Logistics.

## Responsibilities

- Configure Logistics remotes in `rclone.conf`.
- Push and pull folder data with rclone sync.
- Manage rclone credentials and configuration.
- Mount individual remotes on demand through FUSE.
- Detect the platform filesystem dependency used by `rclone mount`.

## FUSE Mounting

Remote folders are no longer mounted automatically when Logistics starts.

The Folders UI exposes a separate `fuse` contribution for configured rclone remotes:

- Linux uses the system FUSE support.
- macOS detects macFUSE and can launch the bundled `Software/macOS/macfuse-5.0.5.dmg` installer when missing.
- Windows detects WinFsp and can launch the bundled `Software/Windows/winfsp-1.11.22176.msi` installer when missing.
- Once the dependency is available, `Mount and Open Remote Folder` mounts only the selected remote under
  `Server/NetworkMount/<remote>` and opens it.
- Already-mounted remotes expose `Open Remote Folder` instead of starting another mount process.

`mount_all_rclone_conf_remotes()` remains available as an explicit backend utility but is not called during feature startup.

## Initialization

The feature is loaded dynamically by the Logistics feature registry.

Initialization loads the Logistics rclone credentials and clears stale Windows mount directories. It does not mount remotes.

## Notes

rclone is an optional Logistics feature.

Logistics core should not depend on rclone being available in order to work with folders already present under `Server/Local`.


## macOS/Linux mount readiness

On-demand Unix mounts use rclone daemon mode and are not considered ready merely
because the mount point exists. Logistics verifies that the mounted root can
actually service a directory read before opening it.

If a FUSE mount point exists but is unresponsive, Logistics attempts to unmount
the stale mount and remount that remote before opening it.
