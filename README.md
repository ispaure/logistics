# Logistics

Logistics is a personal Python/PySide6 desktop toolbox for managing local and remote folders, media libraries, servers, and maintenance tasks. Launchers support macOS, Windows, and Linux; individual integrations may support fewer platforms.

## Getting started

1. Clone with shared utilities: `git clone --recurse-submodules <repository-url>`.
   For an existing checkout, run `git submodule update --init --recursive`.
2. Review [configuration and resource setup](CONFIGURATION.md). Defaults keep
   private resources in the checkout and managed data under your home directory;
   Dropbox is optional.
3. Run the launcher for your platform:

   | Platform | Launcher |
   | --- | --- |
   | macOS | `LaunchLogistics_MAC.command` |
   | Windows | `LaunchLogistics_WIN.bat` |
   | Linux | `bash LaunchLogistics_LINUX_UV.sh` |

The shared launchers install `uv` when needed, resolve the requested Python version,
and synchronize [dependencies](Python/pyproject.toml) from [uv.lock](Python/uv.lock)
into the root `.venv`. The current lock targets Python 3.12.2. Initial setup
requires internet access. The entry point is
`Python/launch.py`; [launch_config.ini](launch_config.ini) controls launcher paths.

## Finding your tools

**Folders** brings together managed local folders, optional Dropbox accounts and
loaded rclone remotes. Select a source, then a folder: enabled features contribute
relevant controls for detected libraries, servers and folder configuration. A
remote and its same-named local folder can share one entry; credential context is
retained when several configs define the same remote name.

**rclone** loads credential packages and manages the resulting remote configs.
Transfers use the selected config; **FUSE** adds an on-demand mount action where
supported. Ordinary transfers do not require a filesystem driver.

**Debug** hosts standalone maintenance workflows and **Open File Browser…**.
The browser navigates any selected root with list, tile and column views, file
information, previews and enabled features' selection actions. Dedicated feature
pages provide other controls, such as Links and Smart Home. **Servers** shows
contributed server controls when available.

**Features** enables or disables integrations for the current session. Hard
dependencies determine availability, and disabling a feature removes its browser
contributions and owned file-type rules. Existing operations and windows keep
their state; disabling does not undo changes already made to files.

## Configuration and resources

Application paths and folder exclusions live in
[Python/configFile.ini](Python/configFile.ini). Feature-owned settings live with
that feature; folder-specific integration settings use `remoteConfig.ini` where
required. The [configuration guide](CONFIGURATION.md) explains each layer and
links to the relevant feature instructions.

`Software/` and `RemoteCredentials/` are created at the repository root and ignored
by Git. Credential packages must be supplied separately; an empty credentials
folder is a valid starting point. `.conf` files are also ignored. On first use,
rclone and macOS/Windows mount drivers can offer a verified download from the
[pinned manifest](Python/software_manifest.json). Other integrations may require
an installed application or separately supplied software. Startup does not
provision every integration.

Platform launchers support Windows, macOS and Linux, while individual features
have their own platform limits. Actions may replace files, synchronize folders or
modify application settings; each feature guide describes its specific behavior.
Background progress and cancellation are available for archive creation and comic
compression/encryption. Other workflows have their own execution models.

## Features

Each feature README describes its behavior, configuration, and limitations.

| Feature | Purpose |
| --- | --- |
| [rclone](Python/features/rclone/README.md) | Credential configs and remote push/pull |
| [FUSE](Python/features/fuse/README.md) | Mount and open remotes on demand |
| [Comics](Python/features/comics/README.md) | Library tabs, native reader, metadata editing, CBZ compression and encryption, and CBR conversion |
| [Archives](Python/features/archives/README.md) | Create separate verified AES-256 ZIPs from file/folder selections |
| [Images](Python/features/images/README.md) | Image compression and JPG EXIF tools |
| [Calibre](Python/features/calibre/README.md) | Library launching and book export |
| [Plex](Python/features/plex/README.md) | Media Server data backup and restore |
| [Media](Python/features/media/README.md) | MKA chapter renaming from CSV |
| [YouTube Downloader](Python/features/youtube_downloader/README.md) | Channel/playlist downloads and optional remote sync |
| [Minecraft](Python/features/minecraft/README.md) | Discover and manage servers within local folders |
| [Perforce](Python/features/perforce/README.md) | Launch configured P4D servers on Linux |
| [Obsidian](Python/features/obsidian/README.md) | Discover, register, and open vaults |
| [Dropbox](Python/features/dropbox/README.md) | Folder sources and conflicting-copy cleanup |
| [Links](Python/features/links/README.md) | Configured website shortcuts |
| [Smart Home](Python/features/smart_home/README.md) | Philips Hue controls and Tautulli scripts |
| [Flight Simulator](Python/features/flight_sim/README.md) | X-Plane 12 settings and window presets |
| [File Tools](Python/features/file_tools/README.md) | Unicode path diagnostics and bytecode cleanup |
| [System Tools](Python/features/system_tools/README.md) | Platform-specific maintenance actions |

## Development

`Python/features/` owns feature logic and feature-specific UI; `Python/ui_new/` hosts the generic interface; `Python/models/` and `Python/services/` provide folder models and discovery support. `Python/commonUtils/` is a Git submodule. See [UI architecture](Python/features/UI_ARCHITECTURE.md) for contribution and configuration conventions. `Scripts/` contains standalone scripts.

Run the regression suite from the repository root:

```sh
# macOS / Linux
PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/tests -v
```

On Windows PowerShell, set `$env:PYTHONPATH = "Python"` and run `.venv/Scripts/python.exe -m unittest discover -s Python/tests -v`.

For the complete portable check runner (both repositories’ suites plus historical
comic compression comparisons), use the project interpreter:

```sh
python Python/tests/run_platform_checks.py
```

[Cross-platform CI and local testing](Python/tests/PLATFORM_CHECKS.md) cover Windows,
macOS, Ubuntu and Fedora 43 userspace in a container. Tests use disposable fixtures
and headless Qt. Desktop interaction, real remote mounts and external integrations
still require separate validation.

The suite covers feature startup ordering, folder-source refresh and selection,
generic action dispatch, main navigation, comics, images, Calibre exports, simulated
FUSE recovery, and Perforce command forwarding. Core UI tests supply mock feature contributions and use Qt's offscreen
platform; they do not mount remotes or launch external applications. See the
[maintenance notes](Python/MAINTENANCE.md) for the main remaining gaps.

Plex package/database maintenance and downloader command construction are covered
by temporary fixtures and mocked processes in `Python/tests/test_plex.py` and
`Python/tests/test_youtube_downloader.py`. These checks do not run a server,
download media, update packages or perform remote transfers.
