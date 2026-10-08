# FUSE Feature

Provides optional mounted-folder access for rclone remotes.

## Using this feature

Load a credential config on the **rclone** page, select its remote in
**Folders**, then choose **Open Mount Folder** in the FUSE section. A missing
driver or rclone executable is handled on that action, not during browsing.

See [shared setup and resource paths](../../../CONFIGURATION.md) and the
[Logistics feature index](../../../README.md#features) for application-wide setup.

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
- Offer a verified macFUSE or WinFsp installer download when required.
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

When filesystem support is missing, the mount action offers to download and
open the pinned installer. Its SHA-256 hash and path are centralized in
`Python/software_manifest.json`. After completing installation, retry the mount:


`Logistics/Software/macOS/macfuse-5.0.5.dmg`

### Windows

The feature detects WinFsp in its standard Program Files locations.

When filesystem support is missing, the mount action offers to download and
open the pinned installer. Its SHA-256 hash and path are centralized in
`Python/software_manifest.json`. After completing installation, retry the mount:


`Logistics/Software/Windows/winfsp-1.11.22176.msi`

### Linux

The feature expects the system FUSE device and helper to already be available.
Install FUSE through the distribution package manager; Logistics does not download
a universal Linux driver installer.

## Initialization

Initialization only performs local stale-mount housekeeping where required.
It never mounts all remotes at application startup.

Windows cleanup removes only empty ordinary directories. Symbolic links,
junctions, mount points and nonempty folders are preserved.

## Commands and recovery

Mount, unmount and installer commands use argument lists. Remote names cannot
escape their mount directory or be interpreted as command options. New mounts
refuse linked or nonempty mount locations. Unix daemon startup checks the command
exit status; Windows starts the long-running mount process and readiness is
checked separately.

Directory-read probes run in a child Python process with a timeout, preventing
normal stale-filesystem probe failures from blocking the polling loop indefinitely.
Readiness probes use the remaining wait budget. The explicit bulk-mount helper
returns success/failure and has a shared bounded readiness wait rather than an
unlimited loop. Command timeouts are separate from that readiness budget.

An unresponsive Unix mount is unmounted before retrying. A failed unmount stops
recovery; failed startup reports failure and removes only an ordinary empty mount
directory. Automatic recovery of an unresponsive Windows mount remains unsupported.
Linux dependency/installer checks do not require private Software resources.

`Python/tests/test_fuse.py` simulates mount states and process outcomes, including
deadline handling, recovery failures and link preservation. It also runs the
directory probe against a temporary local folder. These tests do not mount real
remotes or validate macFUSE/WinFsp/Linux drivers.


## Shared provisioning boundary

Driver installer metadata and paths are centralized with rclone in the Logistics
software manifest. [Resource setup](../../../CONFIGURATION.md#public-software-provisioning)
explains overrides and updating pins. The shared download UI verifies a local
installer; Logistics opens it after consent, while the operating system owns driver
installation and any privilege/restart requirements. Download cancellation is not
an unmount or mount cancellation API.
