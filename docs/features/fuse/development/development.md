# Developing FUSE mounts

FUSE lets rclone expose a remote as a local folder on macOS, Windows and Linux.
See the [user guide](../user/user.md) for setup and how to retry a failed mount.

## Try a change to mount action discovery

On desktop, enable rclone and FUSE, then select an rclone remote with saved
credentials in **Workspaces → Cloud**. Its FUSE section offers **Open Mount
Folder**. The callback in `Python/features/fuse/ui_contributions.py:_get_actions`
passes the selected remote name and config path to
`actions.mount_and_open_remote`.

For example, shorten the action's description in `_get_actions` while keeping
the selected config bound to the callback. The fixture
`test_folder_action_discovery_is_lazy` constructs a remote entry and mocks
the mount action. Run from the repository root with the desktop environment set up:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_fuse.py
```

Expect the fixture to find the action and see exactly one call with the
selected remote and config after invoking the callback. Before the callback,
discovery performs no mount attempt. Check the wording in `_get_actions`;
the test checks the handoff and timing. It uses simulated mount states and a
temporary local directory for the readiness probe. Driver and remote behavior
require platform checks.

## Dependency and execution boundary

`__init__.py:register` declares the rclone dependency and contributes the
desktop folder action through `ui_contributions.py`. Browsing/switching folders must
not probe mounts, contact remotes or provision software; dependency checks,
readiness probes and mounting run only after that action. Mount-path calculation
resolves configuration without creating unrelated Software or credential folders.

## Platform support

| Platform | Local dependency check | Provisioning |
| --- | --- | --- |
| macOS | `/Library/Filesystems/macfuse.fs` | Offer the pinned macFUSE installer. |
| Windows | WinFsp in standard Program Files locations | Offer the pinned WinFsp installer. |
| Linux | `/dev/fuse` and `fusermount`/`fusermount3` | System package manager; no universal driver download. |

Update versions, hashes and installer paths in the
[software manifest](../../../../Python/software_manifest.json).
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

## Platform exposure

`ui_contributions._get_config_path` restricts the desktop action to rclone entries
with a credential context and excludes `.session` contexts. Internal binding tests
for session generations do not imply that session-only mounting is offered by the
GUI. There is no mobile FUSE adapter; see [mobile scope](../user_mobile/user_mobile.md).
