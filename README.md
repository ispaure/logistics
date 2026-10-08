# Logistics

Logistics is a personal Python/PySide6 desktop toolbox for managing local and remote folders, media libraries, servers, and maintenance tasks. Launchers support macOS, Windows, and Linux; individual integrations may support fewer platforms.

Read [Using Logistics](USER_GUIDE.md) for user instructions, or choose **User guide**
beside a feature on the Features tab.

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
requires internet access. The entry point is `Python/launch.py`; [launch_config.ini](launch_config.ini) controls launcher paths.

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
pages provide other controls, such as Links and Smart Home. Minecraft server
controls appear within the selected folder’s section.

**Features** enables or disables integrations for the current session and opens
per-feature user guides in the built-in Markdown reader. Hard
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

For both repositories' suites and the historical comic compression comparison,
use the same project interpreter:

```sh
.venv/bin/python Python/tests/run_platform_checks.py
```

On Windows, use `.venv/Scripts/python.exe Python/tests/run_platform_checks.py`.
The runner configures the import path and headless Qt automatically. See
[cross-platform testing](Python/tests/PLATFORM_CHECKS.md) for CI and platform details,
[UI architecture](Python/features/UI_ARCHITECTURE.md) for extension conventions,
and [maintenance notes](Python/MAINTENANCE.md) for remaining validation gaps.

Tests cover application startup, contributions, local fixtures and simulated
failures. Desktop interaction, real remote transfers/mounts, external applications
and installed drivers require separate validation.
