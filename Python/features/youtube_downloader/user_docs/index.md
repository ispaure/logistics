# Download configured channels and playlists

The YouTube Downloader folder action appears when its `remoteConfig.ini` identifies
a directory of download settings.

## Prepare settings

At the local folder root:

```ini
[Youtube-Download]
config_sub_path = YoutubeDownloaderConfig
```

Inside that subdirectory, each channel/playlist INI uses a `[Youtube-DL]` section
with `channel_name`, `download_url`, `season_number` and `additional_params`.
Channel names must be a single folder name; seasons must be nonnegative integers.
The download URL must use HTTP or HTTPS. Extra options use shell-style quoting.

FFmpeg must be on PATH; Windows/macOS also check their supplied software locations.
The launcher installs the pinned yt-dlp dependency. Normal downloads use that
installed version. **Update yt-dlp** is a separate action; it uses uv when
available, otherwise pip. A normal launcher dependency sync restores the version
pinned by Logistics.

## Download

1. Select the configured local folder on **Folder Hub**.
2. Open **YouTube Downloader…**.
3. Start the intended download operation and review process output and failures.

Files are stored in sibling channel folders under `Season <number>`. Completion
lists are kept in `CompleteLists/` beneath the settings directory. Numbering
continues from the highest existing parsed episode number.

Downloads and season transfers run in the background. **Cancel** stops the running
process tree and leaves yt-dlp’s resumable partial downloads in place. Closing the
dialog requests cancellation and waits for the worker to stop. A successful process exit may still omit individual
playlist items because yt-dlp uses ignore-errors behavior.

Optional remote synchronization requires [rclone](../../rclone/user_docs/index.md)
and the appropriate selected remote/config. Review transfer direction before use.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
