# Using Logistics

Start in **File Browser** to work with any folder, or **Folder Hub** for configured
libraries, servers and remote storage. **Documents** lists open readers/editors;
**Settings → Features** saves which tools are enabled. Required features are enabled
together, and disabling a dependency with active dependents is refused.

- [Files, search, storage, panes and Markdown](Python/ui_new/user_docs/README.md)
- [Bulk Rename: preview, apply and recover](Python/ui_new/bulk_rename/user_docs/README.md)
- [Configuration: paths, credentials and saved settings](CONFIGURATION.md)

Feature help opens read-only in the app. Its compatibility entry links to the same
canonical guide used below. Save settings explicitly; some changes apply to new
windows or after a restart. A cancelled batch may already have changed some files;
check the feature's recovery guidance before retrying.

## Feature guides

| Tool | What it does |
| --- | --- |
| [Git](Python/features/git/user_docs/README.md) | Open/clone repositories, review changes, commit, manage branches and remotes |
| [Text Editor](Python/features/text_editor/user_docs/README.md) | Edit text/code, search, change encoding and recover unsaved work |
| [Books](Python/features/books/user_docs/README.md) | Read EPUBs and edit book metadata |
| [Comics](Python/features/comics/user_docs/README.md) | Read, organize, compress, convert and edit comic metadata |
| [Archives](Python/features/archives/user_docs/README.md) | Browse, create, test and extract ZIP/TAR archives |
| [Images](Python/features/images/user_docs/README.md) | Compress images and edit JPG comments |
| [rclone](Python/features/rclone/user_docs/README.md) | Configure and transfer remote folders |
| [FUSE](Python/features/fuse/user_docs/README.md) | Open remote storage as a mounted folder |
| [Calibre](Python/features/calibre/user_docs/README.md) | Open libraries and review book exports |
| [Plex](Python/features/plex/user_docs/README.md) | Back up, compare and restore server data |
| [YouTube Downloader](Python/features/youtube_downloader/user_docs/README.md) | Download configured channels and playlists |
| [Minecraft](Python/features/minecraft/user_docs/README.md) | Find and launch configured servers |
| [Perforce](Python/features/perforce/user_docs/README.md) | Launch a local Linux server and console |
| [Obsidian](Python/features/obsidian/user_docs/README.md) | Find and open vaults |
| [Dropbox](Python/features/dropbox/user_docs/README.md) | Browse account folders and review identical conflict copies |
| [Links](Python/features/links/user_docs/README.md) | Open configured website shortcuts |
| [Smart Home](Python/features/smart_home/user_docs/README.md) | Discover and control Hue rooms |
| [Aviation Tools](Python/features/aviation_tools/user_docs/README.md) | Use the supplied calculators and aircraft/airport tables |
| [Flight Simulator](Python/features/flight_sim/user_docs/README.md) | Apply X-Plane display/settings presets |
| [Media](Python/features/media/user_docs/README.md) | Rename MKA chapters from a CSV |
| [File Tools](Python/features/file_tools/user_docs/README.md) | Inspect filenames and review bytecode cleanup |
| [System Tools](Python/features/system_tools/user_docs/README.md) | Launch platform-specific maintenance commands |

## If a tool does not work

Check feature enablement, the selected source/credential, required software and
folder detection rules in its guide. Refresh Folder Hub after changing its folders
or loaded configs. Missing credentials do not prevent ordinary local browsing.

If a launcher says Logistics is already open, use the existing window: only one
process runs per user. Initial dependency setup needs internet. A missing shared
launcher usually means the commonUtils submodule was not included; see
[installation](README.md#get-started).
