# Develop YouTube Downloader

## Try an output filename change

On desktop, use the [configuration example](../user/user.md) in a disposable local workspace and open **YouTube Downloader…**. With a synthetic URL, leave downloads idle. In `Python/features/youtube_downloader/settings.py:download_arguments`, change `%(title).50s` to `%(title).40s`. Assert the shorter template in `test_arguments_preserve_quotes_ampersands_and_template_percent` and run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_youtube_downloader.py
```

Expect the new template, one intact URL after `--` and one quoted filter argument.

## Configuration, execution and sync

`detection.py` rejects absolute, traversal and link-escaping config paths. Channel names are single portable folder names. Settings accept UTF-8 BOM and keep interpolation off. Trusted `additional_params` use shell-style quoting. Execution uses argument lists. Numbering continues from the highest parsed episode, with the legacy MP4-count fallback. `CompleteLists/` stores yt-dlp archives.

FFmpeg uses PATH, then bundled Windows/macOS paths. A locked launcher sync restores the pinned yt-dlp after manual updates. A batch continues after individual failures. Cancel terminates the process tree and close waits for the worker. Partial downloads remain resumable.

`downloader.py` re-exports `push_seasons`, `push_config` and `pull_config`. Push selects `Season <digits>` folders. Waiting sync requires `SUCCEEDED`. Reviewed sync also accepts `STARTED`. A rejection stops later seasons. Both config operands use the captured directory. See [rclone transfer ownership](../../rclone/development/transfers.md) and [mobile availability](../user_mobile/user_mobile.md).
