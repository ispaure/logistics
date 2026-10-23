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

1. Select the configured local folder on **Workspaces**.
2. Open **YouTube Downloader…**.
3. Start the intended download operation and review process output and failures.

Files are stored in sibling channel folders under `Season <number>`. Completion
lists are kept in `CompleteLists/` beneath the settings directory. Numbering
continues from the highest existing parsed episode number.

Downloads and season transfers run in the background. **Cancel** stops the running
process tree and leaves yt-dlp’s resumable partial downloads in place. Closing the
dialog requests cancellation and waits for the worker to stop. A successful process exit may still omit individual
playlist items because yt-dlp uses ignore-errors behavior.

Optional remote synchronization requires [rclone](../../rclone/user/user.md)
and the appropriate selected remote/config. Review transfer direction before use.

## More help

See [Using Logistics](../../../user/user.md) for navigation and settings.

For example, a channel file can contain:

```ini
[Youtube-DL]
channel_name = Example Channel
download_url = https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID
season_number = 1
additional_params =
```

Replace the example URL with your playlist. The settings directory must stay
inside the selected local folder; paths that escape it are rejected. Download
history lists prevent repeated completed downloads. They are state files, not
copies of the media. Remote season/config transfers use sync and can remove
extra destination files; review the selected credential and destination first.

GUI Push and Pull actions show a detailed rclone review before transferring,
including additions, replacements and deletions. You can explicitly proceed
without the full review while a comparison is still running. Confirmation does
not bypass required credential or encrypted-file checks. Season-folder Pushes
review each destination separately.
