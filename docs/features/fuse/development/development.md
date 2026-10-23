# FUSE Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../development/features.md) for shared contribution conventions.

Provides optional mounted-folder access for rclone remotes.

## Dependency and execution boundary

FUSE requires the rclone feature. It contributes Open Mount Folder for configured
remotes, using the selected credential context. Browsing/switching folders must
not probe mounts, contact remotes or provision software; dependency checks,
readiness probes and mounting run only after that action. Mount-path calculation
resolves configuration without creating unrelated Software or credential folders.

## Platform support

| Platform | Local dependency check | Provisioning |
| --- | --- | --- |
| macOS | `/Library/Filesystems/macfuse.fs` | Offer the pinned macFUSE installer. |
| Windows | WinFsp in standard Program Files locations | Offer the pinned WinFsp installer. |
| Linux | `/dev/fuse` and `fusermount`/`fusermount3` | System package manager; no universal driver download. |

Versions, hashes and installer paths belong to the
[software manifest](../../../../Python/software_manifest.json), not duplicated feature constants.
See [resource setup](../../../user/configuration.md#public-software-provisioning) for
pin updates and overrides. Logistics verifies and opens the installer after consent;
the OS owns installation, privileges and restarts. Retry mounting after installation.
Download cancellation does not provide mount/unmount cancellation.

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

An unresponsive Unix mount with a matching process-owned credential binding is
unmounted before retrying. A failed unmount stops
recovery; failed startup reports failure and removes only an ordinary empty mount
directory. Automatic recovery of an unresponsive Windows mount remains unsupported.
Linux dependency/installer checks do not require private Software resources.

`Python/tests/integrations/test_fuse.py` simulates mount states and process outcomes, including
deadline handling, recovery failures and link preservation. It also runs the
directory probe against a temporary local folder. These tests do not mount real
remotes or validate macFUSE/WinFsp/Linux drivers.

Mount locations include a stable identity derived from the configuration path,
so same-named remotes in different credential files stay separate. Mount readiness
runs in a retained progress dialog after dependency prompts on the GUI thread.

## Credential binding

`MountBindings` retains the remote, canonical configuration path and credential
identity that launched each mount. Reuse and readiness require that binding to
still match. File credentials include file identity and content digest; session
credentials also retain the session generation's revocation predicate. Replacing
credentials with identical values cannot reactivate a revoked session mount.

Bindings stay in memory. A mount inherited after application restart, or a mount
whose credentials changed during startup, requires explicit unmounting before it
can be opened again. Unknown mounts are not automatically unmounted or browsed.
Tests simulate these policies; native driver validation remains outstanding.
