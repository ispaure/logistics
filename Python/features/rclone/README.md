# rclone Feature

For usage instructions, see the [user guide](user_docs/index.md). This README
covers development, implementation details and validation.


Provides base rclone integration for Logistics.

## Using this feature

Open the **rclone** page to load credential ZIPs, then select the matching
credential and remote on **Folders** for push/pull actions. FUSE mounting is a
separate optional feature.

See [shared setup and resource paths](../../../CONFIGURATION.md) and the
[Logistics feature index](../../../README.md#features) for application-wide setup.

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

The **Local** source shows managed local folders that are not represented by an
active remote or a dedicated local source. It is hidden when there are no such
folders. Excluding a remote name does not exclude its local folder.

Loaded rclone configs appear together under the **rclone** source tab. The
**Credential** dropdown selects **All** configs or a specific config such as
Personal or Work. Switching back to Folders refreshes the available configs and
folder lists; changing the credential uses the current refresh's snapshot.

An rclone source associates an exact case-sensitive local folder when a remote
has the same name. If two configs both define `Media`, the All view shows separate
entries labelled with the config names and preserves the selected credential
through a refresh. Actions use the context belonging to the selected entry.
The remote's name remains `Media`; the credential label does not change its
filesystem paths.

## Filesystem paths

Local folders live directly under:

```text
Local/<folder>
```

FUSE mounts live directly under:

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

The executable resolver uses the checkout's ignored `Software/` directory.
`Python/software_manifest.json` pins rclone 1.73.1, official HTTPS URLs, archive
SHA-256 hashes, extracted executable hashes, and installation paths. Builds cover
Windows, macOS, and Linux on both x86_64 and ARM64:

| Platform | Path beneath `Software/` |
|----------|---------------------------|
| Windows x86_64 / ARM64 | `Windows/rclone-v1.73.1-windows-{amd64,arm64}/rclone.exe` |
| macOS Intel / Apple Silicon | `macOS/rclone-v1.73.1-osx-{amd64,arm64}/rclone` |
| Linux x86_64 / ARM64 | `Linux/rclone-v1.73.1-linux-{amd64,arm64}/rclone` |

Startup and source discovery never download software. Immediately before sync or
mount, a missing or mismatched executable offers a download. Declining, cancelling,
or failing verification stops the command. Downloads run in a background worker,
verify both hashes, set Unix execute permission, and replace files atomically.
Existing legacy rclone paths are left alone; the manifest's architecture-specific
path is now authoritative. Versions are pinned rather than automatically upgraded.

Archive hashes were checked against the official
[rclone 1.73.1 SHA256SUMS](https://downloads.rclone.org/v1.73.1/SHA256SUMS).
Executable hashes were computed from those verified archives. The macFUSE digest
matches its published release digest; the WinFsp digest was computed from the
pinned official release MSI.

All `.conf` files in `~/.config/rclone` are available as sources, including the
legacy default config and configs whose original credential ZIP is no longer
present. The ignored root `RemoteCredentials/` directory can start empty.

Credential ZIPs contain `.txt` files whose first line is a rclone section header (such as `[Media]`), followed by that remote's configuration lines. Loading combines the entries into the package's dedicated `.conf`.

Logistics core does not depend on rclone. Local folders continue to work when
the rclone feature is not distributed with the application.

Credential ZIP loading uses the shared `commonUtils.zip_access` extraction through
`zipUtils.unzip_file`, with the explicitly supplied credential password. Plain,
ZipCrypto and AES ZIPs retain the same extraction layout. Each load has its own
private temporary directory, removed after success or failure; failed extraction
never writes/replaces the generated `.conf`. This flow does not inherit Comics'
`remoteConfig.ini` password or prompt/cache policy.


## Software policy and shared APIs

Use `services.software.get_software('rclone')` for the pinned spec and resolved
installation path, and `ensure_software('rclone')` immediately before a command.
The manifest remains the single source for versions, URLs, hashes and architecture
paths. Do not add a second automatic-download path in feature code.
[Resource setup](../../../CONFIGURATION.md#public-software-provisioning) explains
manifest updates; [commonUtils download recipes](../../commonUtils/RECIPES.md#provision-a-pinned-executable-or-installer)
cover the shared implementation. Cancel/failure returns no executable and must
stop the command; downloads do not make transfers themselves asynchronous.
