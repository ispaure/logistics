# Developing FUSE mounts

FUSE integration opens a saved rclone remote as a mounted desktop folder.
Logistics offers the action for eligible Cloud entries, then checks the
remote, mount location and readiness when the user invokes it.

## Trace mount admission

Selecting a saved remote in **Workspaces → Cloud** asks
`Python/features/fuse/ui_contributions.py:_get_actions` for **Open Mount Folder**.
The focused fixtures check that discovery does not mount anything and that
invocation captures the intended remote and configuration:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_fuse.py
```

Mount only on invocation. macOS needs macFUSE, Windows WinFsp and Linux `/dev/fuse` plus fusermount. Pinned installers require consent; retry after OS installation. [Software manifest](../../../../Python/software_manifest.json)

Use bounded readiness probes, contained mount names and empty ordinary directories. `MountBindings` ties reuse to config identity and live access. Explicitly unmount inherited or mismatched mounts before reuse. Unix recovery unmounts a matching stale mount before retry and stops on unmount failure. Windows lacks automatic stale-mount recovery. The desktop GUI excludes `.session` credentials. [Setup and recovery](../user/user.md)
