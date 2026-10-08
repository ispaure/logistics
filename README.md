# Logistics

Logistics is a personal Python/PySide6 desktop toolbox for managing local and remote folders, media libraries, servers, and maintenance tasks. Launchers support macOS, Windows, and Linux; individual integrations may support fewer platforms.

## Getting started

1. Clone with shared utilities: `git clone --recurse-submodules <repository-url>`. For an existing checkout, run `git submodule update --init --recursive`.
2. `Software/` and `RemoteCredentials/` are created at the repository root when needed and are ignored by Git, as are `.conf` files. Supply credential ZIPs separately. rclone and macOS/Windows FUSE installers offer verified downloads on first use; no Dropbox installation is required. See [resource resolution](Python/config.py) and the [pinned software manifest](Python/software_manifest.json).
3. Review [application paths](Python/configFile.ini) and [launcher settings](launch_config.ini). Feature-specific configuration is described in the docs below.
4. Run the launcher for your platform:

   | Platform | Launcher |
   | --- | --- |
   | macOS | `LaunchLogistics_MAC.command` |
   | Windows | `LaunchLogistics_WIN.bat` |
   | Linux | `bash LaunchLogistics_LINUX_UV.sh` |

The shared launchers install `uv` when needed, resolve the requested Python version, and synchronize [dependencies](Python/pyproject.toml) from [uv.lock](Python/uv.lock) into the root `.venv`. Initial setup requires internet access. The application entry point is `Python/launch.py`.

Use **Folders** to select a source and access relevant folder actions. Load credential ZIPs on the **rclone** page to add remote sources. **Debug → Open File Browser…** opens a general browser with the enabled features’ actions and panels. **Features** enables/disables integrations for the session; browser contributions and owned file types follow those toggles. macFUSE, WinFsp, or Linux FUSE support is required for mounting remotes, rather than ordinary rclone transfers.

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

## Comics and encrypted archives

The Comics library has an **All** tab and a tab for each configured library. Closing
a reader opened from a browser returns to that browser. Comics metadata panels,
reader activation and selection actions are available in general browsers while
Comics is enabled. Catalog creation/indexing remains attached to the dedicated
Comics library view; unlocked passwords are cached in memory for the session.

Set an archive password in `remoteConfig.ini` in the relevant folder or an ancestor:

```ini
[LogisticsZIP]
archive_password = your-password-here
```

The nearest `[LogisticsZIP]` section wins; an empty/missing key in that section stops
inheritance. Logistics owns lookup and prompts; commonUtils receives explicit
passwords. Keep real configuration passwords out of Git.

- **Archives → Create encrypted ZIP…** creates a separate archive and keeps sources.
  `Comic.cbz` suggests `Comic.zip` containing the CBZ; selected folders retain their
  root inside the ZIP. Missing configuration triggers password entry and confirmation.
  One ZIP needs one password; conflicting selected passwords require separate ZIPs.
- **Comics → Encrypt unencrypted comics…** recursively encrypts plain CBZs in place
  without converting images or changing entry names/content. Encrypted comics are
  skipped. Each comic uses its configured password; **one confirmed fallback covers
  all comics missing a configured password in the operation**. A progress bar counts
  processed comics. **Cancel after current comic** finishes and verifies the current
  archive, then leaves remaining comics untouched.
- Readers and single-comic metadata editing try the configured password, then prompt
  if needed. Background previews do not prompt. Recompression of encrypted comics
  retains their password and requires valid INI configuration, reporting errors
  instead of repeated batch prompts.

Password-protected writes use AES-256. Entry names remain visible without the
password. Staged replacements are verified before publication; failures preserve
the affected original. See the feature guides for exact rules and limitations.

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
