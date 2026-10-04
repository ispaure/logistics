# rclone Feature

Provides base rclone integration for Logistics.

## Responsibilities

- Load each credential ZIP into its own same-named rclone `.conf`.
- Expose one Folders source per loaded credential config.
- Push and pull folder data using an explicit selected rclone config.
- Manage loaded credential configs without modifying credential ZIP packages.
- Provide the rclone executable/configuration/sync primitives used by dependent features.

## Credential configs

Credential packages live in the Logistics `RemoteCredentials` folder.

Loading:

```text
RemoteCredentials/Personal.zip
```

creates:

```text
~/.config/rclone/Personal.conf
```

The ZIP remains unchanged. Removing the loaded credential deletes only
`Personal.conf`, allowing the ZIP to be loaded again later.

The rclone page also provides a **Clear All .conf Files** action. It deletes
every `.conf` directly inside the rclone config directory, including a legacy
`rclone.conf` if one exists. It never deletes credential ZIP packages.

## Folders UI

The generic Folders page always provides:

```text
Local
```

When credential configs are loaded, rclone contributes additional sources:

```text
rclone [Personal]
rclone [Work]
```

Local-only folders are shown under `Local`.

An rclone source shows remotes available through that config and associates an
exact case-sensitive local folder when one has the same name.

The config name is execution context only. It is not part of folder identity.
If two configs both define `Media`, Logistics still treats the remote as
`Media`.

## Filesystem paths

This change does not alter Logistics folder locations.

Local folders remain directly under:

```text
Local/<folder>
```

FUSE mounts remain directly under:

```text
NetworkMount/<remote>
```

No credential/config name is inserted into either path.

## UI Contributions

The feature contributes:

- one remote-folder source per loaded credential config;
- `Push...` and `Pull` actions for matching remote Folder entries;
- the standalone rclone credentials/configuration page.

Filesystem mounting is intentionally not part of this feature. The optional
`fuse` feature depends on rclone and uses the selected config when it needs to
start a mount.

## Initialization

The feature is loaded dynamically by the Logistics feature registry.

Initialization only ensures the rclone configuration directory exists.
Credentials are not merged into a global `rclone.conf`.

## Dependencies

rclone has no feature dependencies.

Other features may explicitly depend on it when they use rclone behavior:

- `fuse` requires rclone;
- `plex` requires rclone for PMS backup/restore synchronization;
- `youtube_downloader` optionally uses rclone for remote sync actions.

## Notes

The executable resolver uses the private `Software/` directory, rather than searching PATH:

| Platform | Relative executable path |
| --- | --- |
| Windows | `Windows/rclone-2026/rclone.exe` |
| macOS | `macOS/rclone/rclone` |
| Linux x86_64 | `Linux/rclone-v1.73.0-linux-amd64/rclone` |
| Linux ARM64 | `Linux/rclone-v1.73.1-linux-arm64/rclone` |

Credential ZIPs contain `.txt` files whose first line is a rclone section header (such as `[Media]`), followed by that remote's configuration lines. Loading combines the entries into the package's dedicated `.conf`.

Logistics core does not depend on rclone. Local folders continue to work when
the rclone feature is not distributed with the application.
