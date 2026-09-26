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
