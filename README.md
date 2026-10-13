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

The Qt 6.12 interface requires macOS 14 or newer, Windows 10/11, or Linux
with glibc 2.34 or newer on x86-64 (2.39 or newer on ARM64).

Using Git instead? Clone with the shared utilities included, then open the same launcher:

```sh
git clone --recurse-submodules https://github.com/ispaure/logistics.git
```

If you've already cloned it, run `git submodule update --init --recursive` in the
project folder to fetch any missing shared files.

You can open several Logistics instances. They share indexing work and progress;
another open instance can resume unfinished indexing if its owner closes. If all
instances close, queued indexing resumes on the next launch.

Appearance and systemic tool settings share one Logistics Settings window, with
repository defaults, personal AppData overrides and per-field reset. Fonts cover
the interface, browser, reading and code; accent colors also tint dark surfaces.

## Find your way around

The launch page offers **Open full hub with sidebar**, or **File Browser**, **Git**
and **IDE** without the sidebar. **Read & edit** cards launch enabled editors and
readers, including comics, EPUBs and archives. Single-tool views keep a small
settings icon at the bottom-left; clicking it opens settings and navigation choices.

Use **File Browser** for any folder, or **Folder Hub** for configured libraries
and remote storage. **Documents** collects open readers and editors; their tabs can
be split or detached. **Settings** saves feature choices and configuration and
provides links to each feature's help.

Start with [files and documents](Python/ui_new/user_docs/README.md), then choose a
guide below. The [configuration guide](CONFIGURATION.md) explains resource paths,
credentials and settings. External services need their own accounts/software.

## What can it do?

An independent [Android/iOS document prototype](Mobile/README.md) is available for
development builds, with a native hub, private preferences, text/Markdown editing
and EPUB/comic reading plus LM text chat. See its guide for format limits and validation status.

| Tool | Use it to… |
| --- | --- |
| [File Browser & Markdown](Python/ui_new/user_docs/README.md) | Browse, search, preview files and explore storage usage |
| [Git](Python/features/git/user_docs/README.md) | Clone repositories, browse history, stage and commit changes, manage branches and remotes |
| [Bulk Rename](Python/ui_new/bulk_rename/user_docs/README.md) | Preview and apply changes to many filenames at once |
| [Text Editor](Python/features/text_editor/user_docs/README.md) | Edit text and code in tabs, search/replace, see Git change markers, and preserve file encodings |
| [IDE](Python/features/ide/user_docs/README.md) | Keep dockable projects, arrange shared file views in up to three internal groups, navigate Python definitions, search project files, and autosave with Git change markers |
| [LM Chat](Python/features/lm/user_docs/README.md) | Chat with an existing LM server, paste screenshots, discuss IDE projects with read-only file tools, and save conversations locally |
| [Books](Python/features/books/user_docs/README.md) and [Comics](Python/features/comics/user_docs/README.md) | Read EPUBs and CBZs, edit metadata, and manage comic collections |
| [Archives](Python/features/archives/user_docs/README.md) | Browse, create, encrypt, test and extract ZIP/TAR archives |
| [Images](Python/features/images/user_docs/README.md) | Compress images and work with photo metadata |
| [rclone](Python/features/rclone/user_docs/README.md) | Transfer files between local folders and remote storage |
| [FUSE](Python/features/fuse/user_docs/README.md) | Open supported remote storage as a mounted folder |
| [Calibre](Python/features/calibre/user_docs/README.md) | Open book libraries and export books |
| [Plex](Python/features/plex/user_docs/README.md) | Back up and restore media-server data |
| [YouTube Downloader](Python/features/youtube_downloader/user_docs/README.md) | Download channels and playlists |
| [Minecraft](Python/features/minecraft/user_docs/README.md) | Find and manage local servers |
| [Blender](Python/features/blender/user_docs/README.md) | Launch Blender configuration cards; manage presets, compatible addon libraries and Blue Hole branches/Deluxe in Settings |
| [Perforce](Python/features/perforce/user_docs/README.md) | Launch configured servers on Linux |
| [Obsidian](Python/features/obsidian/user_docs/README.md) | Find and open vaults |
| [Dropbox](Python/features/dropbox/user_docs/README.md) | Browse Dropbox folders and clean up conflicting copies |
| [Links](Python/features/links/user_docs/README.md) | Keep useful website shortcuts together |
| [Smart Home](Python/features/smart_home/user_docs/README.md) | Control Philips Hue and access Tautulli tools |
| [Aviation Tools](Python/features/aviation_tools/user_docs/README.md) | Flight calculators and aircraft/airport reference data |
| [Flight Simulator](Python/features/flight_sim/user_docs/README.md) | Manage X-Plane settings and window presets |
| [Media](Python/features/media/user_docs/README.md) | Rename audio chapters from a CSV |
| [File Tools](Python/features/file_tools/user_docs/README.md) | Check filenames and remove Python bytecode files |
| [System Tools](Python/features/system_tools/user_docs/README.md) | Run platform-specific maintenance tools |

Additional emulator tools are available on request through ispaure’s **ally-tools**.

## Learn more

- [User guide](USER_GUIDE.md): using the app and its tools.
- [Configuration](CONFIGURATION.md): paths, settings and optional integrations.
- [Development](docs/developer/README.md): project structure, extension guides and testing.
- [Publishing releases](RELEASING.md): package checks and release troubleshooting.

For contributions, use the [development and validation guide](docs/developer/testing.md).
Feature changes should include updates to their user guides. The application uses
Python 3.12.2 and pinned dependencies; normal launchers manage that environment.
Git and optional external tools are installed/configured separately.

## License

Logistics is available under the [MIT License](LICENSE.md).

Logistics can update itself from published main, beta or alpha releases through
**Update Logistics** in the hub. Checks are on by default; choose a channel or
turn them off in **Settings → Configuration → Updates**. Updates preserve private
software, credentials and ignored files. See [release packaging](RELEASING.md)
for supported installation manifests and channel tags.
