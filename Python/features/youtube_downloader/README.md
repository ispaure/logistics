# YouTube Downloader Feature

Provides configured YouTube channel/playlist downloads for Logistics.

## Using this feature

Select a local folder with downloader configuration in **Folders**, then open
**YouTube Downloader…**. Its dialog manages downloads and optional remote sync.

See [shared setup and resource paths](../../../CONFIGURATION.md) and the
[Logistics feature index](../../../README.md#features) for application-wide setup.

## Responsibilities

- Detect local folders containing YouTube Downloader configuration.
- Update and run yt-dlp for configured channels/playlists.
- Contribute the YouTube Downloader workflow to matching Folder entries.
- Optionally synchronize downloaded Season folders and downloader configuration through rclone.

## Dependencies

The feature has no hard feature dependencies.

It declares:

`FEATURE_OPTIONAL_DEPENDENCIES = ('rclone',)`

Without rclone, downloading still works. The remote sync controls are disabled.

With rclone available, the workflow additionally supports:

- Push Local Season Folders
- Push Local Config
- Pull Remote Config

## Configuration and Runtime

The local folder's `remoteConfig.ini` needs:

```ini
[Youtube-Download]
config_sub_path = DownloaderConfig
```

That subdirectory contains download `.ini` files with a `[Youtube-DL]` section and `channel_name`, `download_url`, `season_number`, and `additional_params` values. Downloads go into sibling channel directories organized as `Season <number>`. Completion lists live in the config directory's `CompleteLists/` folder.

## Structure

- `detection.py` resolves normalized, relative config paths within a local folder.
- `settings.py` reads and validates INI settings and builds yt-dlp argument lists.
- `downloader.py` runs updates/downloads and reports their process status.
- `sync.py` holds optional rclone operations; the existing downloader imports remain available.
- `ui/dialog.py` presents downloads and optional remote synchronization.

## Platform support and execution

Windows, macOS and Linux first look for FFmpeg on PATH. Windows/macOS fall back
to `Software/ffmpeg_win/ffmpeg.exe` or `Software/ffmpeg_macos/ffmpeg`; Linux needs
FFmpeg on PATH. Missing FFmpeg is reported before launching a download.

Commands use argument lists, without a shell or platform-specific separators.
The URL remains one argument, including query parameters. INI interpolation is
disabled so percent-encoded URLs and output templates work. `additional_params`
uses shell-style quoting on all platforms, but is never executed as shell code.
For Windows paths in these options, use quoted forward-slash paths, such as
`--cookies "C:/My Files/cookies.txt"`. These are trusted yt-dlp options and can
change yt-dlp behavior, including its own supported execution options.

Channel names must be a single portable folder name; seasons are nonnegative
integers. URLs must use HTTP or HTTPS. Config sub-paths cannot escape the local
folder, and redirected channel paths cannot escape the download root. Archive
and download directories are created before launch. Numbering continues after the highest parsed episode number in the current
season, so deleted files do not cause number reuse. Legacy unnumbered MP4 files
use a count fallback; metadata sidecars and directories are excluded. Seasons
use at least two digits (`s01`, `s10`). Season sync includes only `Season <digits>` folders.

Batch processing validates the directory before any update, handles `.ini`
extensions case-insensitively, continues after individual failures and returns
whether all commands succeeded. An empty config directory does not trigger an
update. Each command's nonzero exit is reported. `--ignore-errors` remains a
default yt-dlp option, so successful exit does not guarantee every playlist item
was downloaded.

The updater attempts `python -m pip install --upgrade yt-dlp` in the running
environment, with a three-minute timeout. Update failures are logged and downloads
still proceed. Neither pip nor yt-dlp is declared in the project dependencies;
provision them separately. Downloads retain console output and run synchronously;
long-running UI actions still need a future background-worker/cancellation pass.

## Validation

`Python/tests/test_youtube_downloader.py` covers settings, argument boundaries,
paths, Linux/system FFmpeg and bundled Windows fallback, failed commands and batch
behavior. Processes are mocked: tests do not download videos, update packages or
transfer remote files.
