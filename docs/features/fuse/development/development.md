# Developing FUSE mounts

## Try a change to mount action discovery

On desktop, select a saved rclone remote in **Workspaces → Cloud**. Shorten the **Open Mount Folder** description in `Python/features/fuse/ui_contributions.py:_get_actions`. Run from the checkout root. Expect no mount during discovery and one callback with the captured remote and config.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_fuse.py
```

Mount only on invocation. macOS needs macFUSE, Windows WinFsp and Linux `/dev/fuse` plus fusermount. Pinned installers require consent; retry after OS installation. [Software manifest](../../../../Python/software_manifest.json)

Use bounded readiness probes, contained mount names and empty ordinary directories. `MountBindings` ties reuse to config identity and live access. Explicitly unmount inherited or mismatched mounts before reuse. Unix recovery unmounts a matching stale mount before retry and stops on unmount failure. Windows lacks automatic stale-mount recovery. The desktop GUI excludes `.session` credentials. [Setup and recovery](../user/user.md)
