# Configuration and resources

Logistics separates launcher settings, shared application paths, feature settings
and folder-specific configuration. Start with defaults, then configure only the
integrations you intend to use. See the [feature index](README.md#features) for
individual workflows and platform limitations.

## Configuration layers

| Location | Owns | Path base |
| --- | --- | --- |
| [launch_config.ini](launch_config.ini) | Shared launcher, source directory, entry point and optional home directory creation | Launcher directory |
| [Python/configFile.ini](Python/configFile.ini) | Server/data roots, resource overrides and folder exclusions | Depends on setting, described below |
| `Python/features/<feature>/config.ini` | Feature-wide settings, currently Links and Smart Home | Feature-defined |
| `remoteConfig.ini` in a managed folder | Folder-specific integration settings | Feature-defined; usually the selected folder |
| `logistics_cfg.ini` in a Minecraft server | Server launch scripts and documentation URL | Server directory |
| [Python/software_manifest.json](Python/software_manifest.json) | Pinned public download versions, URLs, hashes and installation paths | Software resource root |

These INI files are not interchangeable. Each feature interprets its own sections;
there is no universal ancestor inheritance rule. In particular, archive password
inheritance belongs to [Archives](Python/features/archives/README.md) and
[Comics](Python/features/comics/README.md#password-protected-cbzs), not rclone credentials.

## Managed data paths

The `[DirectoryStructure]` section selects `server_path_win32`, `server_path_macos`
or `server_path_linux` for the current platform. The shipped values use `Server`
under the current user's home directory. The two sub-paths select local folders
and remote mount locations:

```ini
[DirectoryStructure]
server_path_win32 = Server
server_path_macos = Server
server_path_linux = Server
remote_local_sub_path = Local
remote_network_mount_sub_path = NetworkMount
```

With these defaults, a local folder is `~/Server/Local/<folder>` and a mount is
`~/Server/NetworkMount/<remote>`. Credential names do not add another path level.
The launcher also has `ensure_user_dir = Server`; keep it aligned if you change
the managed root. Changing launcher creation alone does not change application paths.

`[Folders] excluded_remote_names` removes listed remote names from the Folders
view. `excluded_folder_name_suffixes` hides matching local and remote folder suffixes. Exclusions
are comma-separated; excluding a remote does not delete it or exclude its local
folder. Dedicated local sources, such as Dropbox, remain separately selectable.

## Private resource directories

Defaults are independent directories at the checkout root:

```text
logistics/
├── Software/
│   ├── Windows/
│   ├── macOS/
│   ├── Linux/
│   └── General/
└── RemoteCredentials/
```

The resource roots are created when configuration is loaded; platform subfolders
are created as needed. Neither root must come from Dropbox. To reuse another
location, add independent overrides to `Python/configFile.ini`:

```ini
[Resources]
software_path = Software
credentials_path = RemoteCredentials
```

Relative overrides resolve from the checkout root; absolute paths and `~` paths
are supported. Either directory can point to an external/private location without
moving the other. Configuration loading requires write access to missing resource
roots so it can create them.

`Software/`, `RemoteCredentials/` and all `.conf` files are ignored by Git.
Git ignore rules do not protect secrets placed in other tracked files or remove
already tracked content. Keep credential packages and real configuration passwords
in private locations; repository INIs should contain only safe example settings.

## Public software provisioning

[services/software.py](Python/services/software.py) selects platform/architecture,
reads the manifest and resolves the destination beneath the software root.
commonUtils supplies download verification and the confirmation/progress UI.

- **rclone:** pinned Windows, macOS and Linux builds for x86_64 and ARM64.
  A missing or mismatched executable prompts immediately before an rclone command.
- **macFUSE / WinFsp:** the mount action offers the pinned installer when driver
  support is missing. Complete the operating-system installation and retry.
- **Linux FUSE:** install device/helper support through the distribution package
  manager. Logistics has no universal Linux driver download.

Downloads verify both release and installed-file SHA-256 hashes, stage beside the
output and replace only after verification. Declining, cancellation or failure
stops the requested operation. Cancellation is cooperative between reads; an active
network read can take until its timeout to return. Ready matching files are reused.
Versions are pinned, with no automatic upgrade to the latest release.

When updating a manifest entry, change the version, HTTPS URL, download hash,
installed-file hash, archive member (if applicable) and relative destination
as one unit. The installed hash is the extracted executable's digest; for a raw
installer it matches the download digest. Validate each supported platform entry.

Other tools keep their existing prerequisites: examples include installed
Obsidian, private Calibre/7-Zip resources, FFmpeg for downloads and X-Plane presets.
An empty `Software/` directory does not provision every optional integration.

## Configure a feature

| Integration | Configuration / prerequisites |
| --- | --- |
| [rclone](Python/features/rclone/README.md) | Private credential ZIPs; generated configs in `~/.config/rclone` |
| [FUSE](Python/features/fuse/README.md) | rclone plus platform mount driver/helper |
| [Comics](Python/features/comics/README.md) | `[LogisticsComics]` library names; optional `[LogisticsZIP]` password |
| [Archives](Python/features/archives/README.md) | Optional inherited `[LogisticsZIP]` password; otherwise interactive creation prompt |
| [Calibre](Python/features/calibre/README.md) | Immediate child library with `metadata.db`; executable/device prerequisites |
| [Plex](Python/features/plex/README.md) | Matching `-PMSDATA` remote and platform server-data location |
| [YouTube Downloader](Python/features/youtube_downloader/README.md) | `[Youtube-Download]` folder config, `[Youtube-DL]` per-channel INIs and FFmpeg |
| [Minecraft](Python/features/minecraft/README.md) | `server.properties` plus `logistics_cfg.ini` for Java launch scripts |
| [Perforce](Python/features/perforce/README.md) | `[Perforce]` folder config and supplied Linux executables/data |
| [Links](Python/features/links/README.md) | Feature `config.ini` URL and hostname substitutions |
| [Smart Home](Python/features/smart_home/README.md) | Feature `config.ini` Hue bridge address and configured groups |

Images, file diagnostics and media rename workflows take their input through
individual dialogs. Dropbox discovers account roots from its installed account
configuration. See each feature guide before using its file-changing actions.
