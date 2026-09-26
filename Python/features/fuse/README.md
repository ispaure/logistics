# FUSE Feature

Provides optional mounted-folder access for rclone remotes.

## Dependency

This feature has a hard dependency on:

`rclone`

If the rclone feature is not present, the feature registry skips FUSE
initialization and contributions.

## Responsibilities

- Detect platform filesystem support required by `rclone mount`.
- Detect macFUSE on macOS.
- Detect WinFsp on Windows.
- Detect `/dev/fuse` and `fusermount`/`fusermount3` on Linux.
- Launch the bundled macFUSE or WinFsp installer when required.
- Mount one selected rclone remote on demand.
- Recover stale/unresponsive Unix FUSE mounts.
- Verify a mount can service directory reads before opening it.
- Open the mounted remote folder.

## UI

Configured rclone remotes receive a separate Folder section:

`fuse`

with one intentionally lazy action:

`Open Mount Folder`

Browsing or switching folders does not probe the mount, contact the remote,
or perform any network-related work.

All FUSE detection, mount-state checks, readiness checks, and mounting occur
only after the user clicks the action.

## Platform Dependencies

### macOS

The feature detects:

`/Library/Filesystems/macfuse.fs`

When missing, it can launch:

`Logistics/Software/macOS/macfuse-5.0.5.dmg`

### Windows

The feature detects WinFsp in its standard Program Files locations.

When missing, it can launch:

`Logistics/Software/Windows/winfsp-1.11.22176.msi`

### Linux

The feature expects the system FUSE device and helper to already be available.

## Initialization

Initialization only performs local stale-mount housekeeping where required.
It never mounts all remotes at application startup.
