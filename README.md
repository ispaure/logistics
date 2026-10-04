# Logistics

Logistics is a personal Python/PySide6 desktop toolbox for managing local and remote folders, media libraries, servers, and maintenance tasks. Launchers support macOS, Windows, and Linux; individual integrations may support fewer platforms.

## Getting started

1. Clone with shared utilities: `git clone --recurse-submodules <repository-url>`. For an existing checkout, run `git submodule update --init --recursive`.
2. Supply the private `Software/` and `RemoteCredentials/` directories separately; they are ignored by Git. Resource discovery prefers the configured Marc Dropbox location (`Software/GIT/logistics`) when both directories exist there, then falls back to the repository root. See [resource resolution](Python/config.py).
3. Review [application paths](Python/configFile.ini) and [launcher settings](launch_config.ini). Feature-specific configuration is described in the docs below.
4. Run the launcher for your platform:

   | Platform | Launcher |
   | --- | --- |
   | macOS | `LaunchLogistics_MAC.command` |
   | Windows | `LaunchLogistics_WIN.bat` |
   | Linux | `bash LaunchLogistics_LINUX_UV.sh` |

The shared launchers install `uv` when needed, resolve the requested Python version, and synchronize [dependencies](Python/pyproject.toml) from [uv.lock](Python/uv.lock) into the root `.venv`. Initial setup requires internet access. The application entry point is `Python/launch.py`.

Use **Folders** to select a source and access relevant folder actions. Load credential ZIPs on the **rclone** page to add remote sources. **Debug** offers additional maintenance workflows. macFUSE, WinFsp, or Linux FUSE support is required for mounting remotes, rather than ordinary rclone transfers.

## Features

Each feature README describes its behavior, configuration, and limitations.

| Feature | Purpose |
| --- | --- |
| [rclone](Python/features/rclone/README.md) | Credential configs and remote push/pull |
| [FUSE](Python/features/fuse/README.md) | Mount and open remotes on demand |
| [Comics](Python/features/comics/README.md) | CBZ compression, ComicInfo editing, CBR conversion, and external reader integration |
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

Run the comics/image regression suite from the repository root:

```sh
# macOS / Linux
PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/tests -v
```

On Windows PowerShell, set `$env:PYTHONPATH = "Python"` and run `.venv/Scripts/python.exe -m unittest discover -s Python/tests -v`.

Tests use disposable fixtures. Desktop dialogs and external integrations require separate platform validation.
