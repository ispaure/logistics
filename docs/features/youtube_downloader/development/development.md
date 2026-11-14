# Develop YouTube Downloader

YouTube Downloader reads local channel or playlist settings and uses yt-dlp to
download episodes into season folders. The optional rclone integration syncs
seasons and configuration. See the [user guide](../user/user.md) for setup.

## Try an output filename change

On desktop, enable **YouTube Downloader** in **Settings → Features**. Create a
disposable folder with these two files, then select the local folder in
**Workspaces → YouTube Downloader…**. The dialog should show the configuration
directory. Leave **Download All Channels** idle when using the synthetic URL.

`remoteConfig.ini`

```ini
[Youtube-Download]
config_sub_path = DownloaderConfig
```

`DownloaderConfig/channel.ini`

```ini
[Youtube-DL]
channel_name = Example Channel
download_url = https://example.test/watch?v=one&list=two
season_number = 1
additional_params = --match-filter "duration > 20"
```

**Download All Channels** calls `YouTubeDownloaderDialog._download_all()` in
`Python/features/youtube_downloader/ui/dialog.py`. Follow `downloader.download_all()`
and `download()` to `download_arguments()` in
`Python/features/youtube_downloader/settings.py`. For a small experiment, change
the title limit in the `-o` template from `%(title).50s` to `%(title).40s`. Add an
assertion for the shorter template in
`test_arguments_preserve_quotes_ampersands_and_template_percent` and run from
the repository root with the desktop environment installed.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_youtube_downloader.py
```

Expect the shorter title template, the complete URL as one argument after `--`
and `duration > 20` as a single filter value. The tests mock process execution
and transfers, so this check needs neither FFmpeg nor network access.

## Find or change folder detection

`ui_contributions.py` offers the desktop action when a Workspaces entry has a
local folder and `detection.has_config()` resolves a configured relative path.
`detection.py` normalizes separators, rejects absolute paths and parent
traversal, and verifies that links stay inside the local root. Detection checks
the configuration path, while `downloader.download_all()` checks that the
directory exists before launching work. If the action is missing, start with
the local entry, feature setting and `[Youtube-Download]` section. If a batch
fails immediately, check the directory and its per-channel INIs.

## Configuration and Runtime

`settings.DownloadSettings.read()` accepts UTF-8 with an optional BOM. It
requires a portable single folder name, a nonnegative integer season and an
HTTP or HTTPS URL. `additional_params` is optional and uses shell-style
quoting on every platform. For Windows paths in options, use quoted forward
slashes such as `--cookies "C:/My Files/cookies.txt"`. These are trusted yt-dlp
options and can invoke behavior yt-dlp itself supports. Logistics runs argument
lists without a shell. INI interpolation is disabled so percent-encoded URLs
and output templates work.

Output goes under a sibling channel directory in `Season <number>`. Resolved
channel destinations must stay inside the download root. Numbering continues
after the highest parsed episode for that season. When there are no parsed
episodes, the legacy fallback counts MP4 files with ` - s` in their basename.
Directories and metadata sidecars do not count. Season prefixes have at least
two digits. Completion lists under `CompleteLists/` are yt-dlp download
archives. The download and archive directories are created before launch.

## Platform support and execution

`settings.find_ffmpeg()` checks PATH first. Windows and macOS also look in
`Software/ffmpeg_win/ffmpeg.exe` and `Software/ffmpeg_macos/ffmpeg`,
respectively, without provisioning resource directories. Linux requires FFmpeg
on PATH. A missing executable fails before launch.

`downloader.download_all()` scans case-insensitive `.ini` extensions, continues
after individual failures and reports whether all commands succeeded.
`--ignore-errors` allows yt-dlp to return success despite missing individual
playlist items. Cancel or close requests termination of the process tree.
Closing waits for worker completion and yt-dlp's resumable partial downloads
remain available. Keep UI updates on the Qt side of `OperationProgress`.
`test_youtube_worker_ui.py` checks the background dialog behavior.

The locked launcher installs pinned yt-dlp. **Update yt-dlp** is a separate
action using uv or pip with a three-minute timeout. A later locked launcher sync
restores the pin.

## Sync compatibility exports

The dialog's optional sync controls require an available rclone integration and
remote context. `downloader.py` re-exports `push_seasons`, `push_config` and
`pull_config` from `sync.py`; the dialog calls these public names.
[The rclone transfer owner](../../rclone/development/transfers.md) owns review
and transfer execution.

`sync.push_seasons()` selects only `Season <digits>` directories. Waiting
transfers require `SyncState.SUCCEEDED`. Reviewed transfers also accept
`STARTED`, which confirms launch. A rejected outcome stops later seasons while
earlier transfers keep their results. Config push and pull derive both operands
from the same captured configuration directory. The focused tests above mock
these outcomes and verify operand consistency.

## Desktop and mobile ownership

The Workspaces action lazily opens a Qt dialog. See the
[mobile support boundary](../user_mobile/user_mobile.md) for platform availability.
