# Using Logistics

Logistics gathers folder, library, remote-storage and maintenance tools in one
desktop application. Tools appear according to enabled features and the selected
folder's contents or configuration.

## Find a tool

| Page | Use it for |
| --- | --- |
| Folders | Choose a source/folder and use detected library, server or remote actions |
| rclone | Load credential packages and manage remote configs |
| Debug | Standalone file/media/maintenance tools and Open File Browser |
| Features | Enable/disable integrations and open each feature's User guide |
| Links / Smart Home | Controls provided by those enabled features |

Disabling a feature removes its new actions; existing windows/jobs can finish.
Enabling also enables required dependencies. Changes last for the current session.
A user guide remains accessible when its feature is disabled or lacks a dependency.

## Read documentation

Choose **User guide** beside a feature on Features. This reader supports headings,
lists, tables and code examples. Click a Markdown link to navigate to another guide
or a heading, and use Back/Forward to retrace your steps. Website links open in
your default browser. Unsupported or missing documents show an explanation while
keeping the current page available.

Double-click `.md` or `.markdown` files in the file browser to use the same reader.
Reading does not modify a document. Developer READMEs remain separate from these
user guides.

## Resources and settings

Default private resources live in `Software/` and `RemoteCredentials/` at the
checkout root; Dropbox is optional. Credentials must be supplied separately.
Missing rclone software and macOS/Windows mount-driver installers can offer verified
downloads on first use. Other integrations keep their own installed-app or private
software requirements. See [configuration and resource setup](CONFIGURATION.md)
for path overrides and the configuration layers.

Managed folders use `~/Server/Local/` and mounts use `~/Server/NetworkMount/` by
default. The rclone config directory is `~/.config/rclone/`. Per-feature guides show
where their settings belong and what actions change files or external services.

## Feature guides

- [Create encrypted ZIPs](Python/features/archives/user_docs/index.md)
- [Read and manage comics](Python/features/comics/user_docs/index.md)
- [Connect and transfer remote folders](Python/features/rclone/user_docs/index.md)
- [Open a mounted remote folder](Python/features/fuse/user_docs/index.md)
- [Compress images and edit JPG comments](Python/features/images/user_docs/index.md)
- [Open and export Calibre libraries](Python/features/calibre/user_docs/index.md)
- [Back up and restore Plex server data](Python/features/plex/user_docs/index.md)
- [Rename MKA chapters from a CSV](Python/features/media/user_docs/index.md)
- [Download configured channels and playlists](Python/features/youtube_downloader/user_docs/index.md)
- [Manage Minecraft servers](Python/features/minecraft/user_docs/index.md)
- [Launch a local Perforce server](Python/features/perforce/user_docs/index.md)
- [Open Obsidian vaults](Python/features/obsidian/user_docs/index.md)
- [Browse Dropbox folders and clean conflicts](Python/features/dropbox/user_docs/index.md)
- [Open configured service shortcuts](Python/features/links/user_docs/index.md)
- [Control Philips Hue lights](Python/features/smart_home/user_docs/index.md)
- [Apply X-Plane 12 presets](Python/features/flight_sim/user_docs/index.md)
- [Inspect paths and remove Python bytecode](Python/features/file_tools/user_docs/index.md)
- [Run system maintenance actions](Python/features/system_tools/user_docs/index.md)
