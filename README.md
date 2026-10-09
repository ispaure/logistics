# Logistics

Logistics brings file browsing, media tools and remote-folder management into one
desktop app. Browse your files, see what's taking up space, read comics, rename
batches of files, or work with your servers and libraries.

It runs on Windows, macOS and Linux. Some tools are specific to one platform or
need another application installed.

## Get started

1. Download **release.zip** from [GitHub Releases](https://github.com/ispaure/logistics/releases)
   when a packaged release is available. Choose that file rather than GitHub's
   automatic “Source code” ZIP: it includes the shared commonUtils files too.
2. Extract the ZIP and open the `Logistics` folder.
3. Start the app using the launcher for your computer:

   | Computer | What to open |
   | --- | --- |
   | Windows | Double-click **LaunchLogistics_WIN.bat** |
   | macOS | Double-click **LaunchLogistics_MAC.command** |
   | Linux | Open a terminal in the folder and run `bash LaunchLogistics_LINUX_UV.sh` |

The launcher sets up Python and the required Python packages for you. You'll need
an internet connection for the first run. Setup may take a little while; later
launches reuse the installed environment.

Using Git instead? Clone with the shared utilities included, then open the same launcher:

```sh
git clone --recurse-submodules https://github.com/ispaure/logistics.git
```

If you've already cloned it, run `git submodule update --init --recursive` in the
project folder to fetch any missing shared files.

## Find your way around

The app opens in **File Browser**, starting in your home folder. Use **Open
folder…** to browse another location. You can search, preview files, switch views,
and explore folder sizes with the storage charts.

**Known Folders** brings your configured local folders and remote sources together.
**Settings** lets you enable features and edit their configuration. Each feature
has a **User guide** button under **Settings → Features**.

Start with the tools you need. Credentials for remote services are supplied
separately, and some integrations need their own software or setup. The
[configuration guide](CONFIGURATION.md) explains those steps when you're ready.

## What can it do?

| Tool | Use it to… |
| --- | --- |
| File Browser | Browse, search, preview files and explore storage usage |
| Bulk Rename | Preview and apply changes to many filenames at once |
| [Text Editor](Python/features/text_editor/user_docs/index.md) | Edit text and code in tabs, search/replace, and preserve file encodings |
| [Books & Comics](Python/features/books/user_docs/index.md) | Read EPUBs and comics, edit metadata, and manage or compress comic archives |
| [Archives](Python/features/archives/user_docs/index.md) | Create encrypted ZIPs from files and folders |
| [Images](Python/features/images/user_docs/index.md) | Compress images and work with photo metadata |
| [rclone](Python/features/rclone/user_docs/index.md) | Transfer files between local folders and remote storage |
| [FUSE](Python/features/fuse/user_docs/index.md) | Open supported remote storage as a mounted folder |
| [Calibre](Python/features/calibre/user_docs/index.md) | Open book libraries and export books |
| [Plex](Python/features/plex/user_docs/index.md) | Back up and restore media-server data |
| [YouTube Downloader](Python/features/youtube_downloader/user_docs/index.md) | Download channels and playlists |
| [Minecraft](Python/features/minecraft/user_docs/index.md) | Find and manage local servers |
| [Perforce](Python/features/perforce/user_docs/index.md) | Launch configured servers on Linux |
| [Obsidian](Python/features/obsidian/user_docs/index.md) | Find and open vaults |
| [Dropbox](Python/features/dropbox/user_docs/index.md) | Browse Dropbox folders and clean up conflicting copies |
| [Links](Python/features/links/user_docs/index.md) | Keep useful website shortcuts together |
| [Smart Home](Python/features/smart_home/user_docs/index.md) | Control Philips Hue and access Tautulli tools |
| [Aviation Tools](Python/features/aviation_tools/user_docs/index.md) | Flight calculators and aircraft/airport reference data |
| [Flight Simulator](Python/features/flight_sim/user_docs/index.md) | Manage X-Plane settings and window presets |
| [Media](Python/features/media/user_docs/index.md) | Rename audio chapters from a CSV |
| [File Tools](Python/features/file_tools/user_docs/index.md) | Check filenames and remove Python bytecode files |
| [System Tools](Python/features/system_tools/user_docs/index.md) | Run platform-specific maintenance tools |

## Learn more

- [User guide](USER_GUIDE.md): using the app and its tools.
- [Configuration](CONFIGURATION.md): paths, settings and optional integrations.
- [Development](DEVELOPMENT.md): project structure, extension guides and testing.
- [Publishing releases](RELEASING.md): package checks and release troubleshooting.

Maintainers publish a release by tagging a committed, pushed version:

```sh
git tag v1.0.0
git push origin v1.0.0
```

GitHub builds **release.zip**, including submodules, and adds it to a release with
automatic notes. See the release guide for the steps before publishing your first one.
