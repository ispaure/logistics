# YouTube Downloader Feature

Provides configured YouTube channel/playlist downloads for Logistics.

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

Downloading currently supports Windows and macOS, using FFmpeg under `Software/ffmpeg_win/ffmpeg.exe` or `Software/ffmpeg_macos/ffmpeg`. The updater attempts `python -m pip install --upgrade yt-dlp` in the running environment. Neither pip nor yt-dlp is declared in the project dependencies, so the uv-created environment is not guaranteed to provide them; provision them separately for this workflow. Update failures are logged and downloading still proceeds.
