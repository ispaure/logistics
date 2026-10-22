# Logistics

Logistics brings file browsing, media tools and remote-folder management into one
desktop app. Browse your files, see what's taking up space, read comics, rename
batches of files, or work with your servers and libraries.

It runs on Windows, macOS and Linux. Some tools are specific to one platform or
need another application installed.

Mobile Settings includes bundled offline documentation with nested folder browsing
and file/title or page-text search.

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

Use **File Browser** for any folder, or **Workspaces** for configured libraries
and remote storage. Workspaces groups **Local**, **Cloud** and **Home Server**
locations beside a docked file browser and workspace actions. **Documents** collects open readers and editors; their tabs can
be split or detached. Text, Markdown, EPUB and comic Open dialogs share a Local/LocalCrypt
file picker; encrypted copies open in private readers or editors. Regular and private file browsers
share list, tile and column views. **Settings** saves feature choices and configuration and
provides links to each feature's help.

Start with [files and documents](docs/user/files-and-documents.md), then choose a
guide below. The [configuration guide](docs/user/configuration.md) explains resource paths,
credentials and settings. External services need their own accounts/software.

## What can it do?

An independent [Android/iOS document prototype](docs/development/mobile-launchers.md) is available for
development builds, with a native hub, private preferences, text editing and single-pane formatted/Source
Markdown editing (preview by default), EPUB/comic reading, LM text chat, managed rclone Local/LocalCrypt copies and encrypted
LocalCrypt offline reading, side-by-side saved and session-only credential packages,
text and comic/EPUB metadata editing, local file/folder
management with shared list/tile views, thumbnails and file information, and text
Save As across Local/LocalCrypt storage. Encrypted transfers and archive metadata
updates and ordinary comic imports stream large files without a fixed whole-file
size cap. Standalone AES/legacy password-protected CBZ/ZIP comics open with an
inline password prompt and can be locked after reading. Shared mobile browsing includes folder taps, Back history and search/sort. See its
guide for format limits and validation status. Native readers include EPUB passage resume/search,
comic spreads and imported-copy metadata editing, including explicit-field comic batches. Mobile Pull and reviewed Push show
progress while ordinary documents remain usable. Mobile can save multiple SMB/Mac server
connections and pull shared folders into device storage. Android can keep Local and
LocalCrypt together on a selected SD card under `Logistics/Local` and `Logistics/LocalCrypt`.
On iPhone/iPad, Local uses the Finder/iTunes and Files app sharing root, with automatic
migration and exclusion from device backups; LocalCrypt remains private.
Mobile includes a Focus home
screen, file/conversation drawers and equal-width browser/document
or two-text-document panes in wide windows. Chat and Settings use full-screen destinations.
Independent ordinary iPad windows
have separate workspaces and prevent duplicate writers. Crypt files offer both encrypted
offline copies and direct remote previews. A Mac can build, install and launch
the iPhone app over Wi-Fi using the [paired-device workflow](docs/development/mobile-launchers.md#build-and-deploy-to-a-paired-iphone-over-wi-fi).
A [double-click Android launcher](docs/development/mobile-launchers.md#double-click-android-deployment) stages local sources, builds and installs on a connected Android device.
A [simple deployment window](docs/development/mobile-launchers.md#simple-deployment-window) updates iOS and Android test devices concurrently and offers separate Firebase and TestFlight buttons using existing settings.
A [Firebase beta launcher](docs/development/mobile-launchers.md#double-click-android-firebase-distribution) builds and signs Android APKs for invited testers; a combined launcher runs device installs and both beta distributions.
An [opt-in TestFlight workflow](docs/development/mobile-testflight.md) prepares
archives and uploads with the same app identity after developer enrollment approval.
For first-time Xcode setup, local builds, TestFlight and Android instructions, start
with the [mobile build and release handbook](docs/development/mobile-handbook.md).

| Tool | Use it to… |
| --- | --- |
| [File Browser & Markdown](docs/user/files-and-documents.md) | Browse files, explore storage usage, and open Markdown Notes Libraries from location actions |
| [Git](Python/features/git/docs/user/user.md) | Clone repositories, browse history, stage and commit changes, manage branches and remotes |
| [Bulk Rename](Python/desktop/bulk_rename/docs/user/user.md) | Preview and apply changes to many filenames at once |
| [Text Editor](Python/features/text_editor/docs/user/user.md) | Edit text and code in tabs, search/replace, see Git change markers, and preserve file encodings |
| [IDE](Python/features/ide/docs/user/user.md) | Keep dockable projects, arrange shared file views in up to three internal groups, navigate Python definitions, search project files, and autosave with Git change markers |
| [LM Chat](Python/features/lm/docs/user/user.md) | Chat with an existing LM server, paste screenshots, discuss IDE projects with read-only file tools, and save conversations locally |
| [Books](Python/features/books/docs/user/user.md) and [Comics](Python/features/comics/docs/user/user.md) | Read EPUBs and CBZs, edit metadata, and manage comic collections |
| [PDF Reader](Python/features/pdf/docs/user/user.md) | Read and search local, remote and LocalCrypt PDFs on desktop and mobile, jump to page numbers, and swipe vertically |
| [Archives](Python/features/archives/docs/user/user.md) | Browse, create, encrypt, test and extract ZIP/TAR archives |
| [Images](Python/features/images/docs/user/user.md) | Compress images, work with photo metadata, and [capture bursts on iPhone](Python/features/images/docs/user_mobile/user_mobile.md) |
| [rclone](Python/features/rclone/docs/user/user.md) | Browse remotes in read-only tabs, open supported files in memory, and use managed Pull/Push for local or encrypted folders |
| [FUSE](Python/features/fuse/docs/user/user.md) | Open supported remote storage as a mounted folder |
| [Calibre](Python/features/calibre/docs/user/user.md) | Open book libraries and export books |
| [Plex](Python/features/plex/docs/user/user.md) | Back up and restore media-server data |
| [YouTube Downloader](Python/features/youtube_downloader/docs/user/user.md) | Download channels and playlists |
| [Minecraft](Python/features/minecraft/docs/user/user.md) | Find and manage local servers |
| [Blender](Python/features/blender/docs/user/user.md) | Launch Blender configuration cards; manage presets, compatible addon libraries and Blue Hole branches/Deluxe in Settings |
| [Perforce](Python/features/perforce/docs/user/user.md) | Launch configured servers on Linux |
| [Obsidian](Python/features/obsidian/docs/user/user.md) | Find and open vaults |
| [Dropbox](Python/features/dropbox/docs/user/user.md) | Browse Dropbox folders and clean up conflicting copies |
| [Links](Python/features/links/docs/user/user.md) | Keep useful website shortcuts together |
| [Smart Home](Python/features/smart_home/docs/user/user.md) | Control Philips Hue and access Tautulli tools |
| [Aviation Tools](Python/features/aviation_tools/docs/user/user.md) | Flight calculators and aircraft/airport reference data |
| [Flight Simulator](Python/features/flight_sim/docs/user/user.md) | Manage X-Plane settings and window presets |
| [Media](Python/features/media/docs/user/user.md) | Rename audio chapters from a CSV |
| [File Tools](Python/features/file_tools/docs/user/user.md) | Check filenames and remove Python bytecode files |
| [System Tools](Python/features/system_tools/docs/user/user.md) | Run platform-specific maintenance tools |

Additional emulator tools are available on request through ispaure’s **ally-tools**.

## Learn more

Application source lives under `Python/`: `desktop/` hosts the desktop app,
`mobile/` hosts the mobile app, and `features/` contains the tools they use.
Mobile packaging and deployment scripts live in `mobile_build/`. See the
[code map](docs/development/code-map.md) for ownership and native compatibility.

For contributors, start with [developer setup](docs/development/testing.md).
`python3 dev.py doctor` checks the local environment; `dev.py setup desktop` and
`dev.py setup mobile` prepare separate host environments. Use `py` on Windows.

Start at the [documentation wiki](docs/docs.md) for the user, mobile user and
development hierarchies. Feature manuals live in each owner’s `docs/` folder.

- [User guide](docs/user/user.md): using the app and its tools.
- [Configuration](docs/user/configuration.md): paths, settings and optional integrations.
- [Development](docs/development/development.md): project structure, extension guides and testing.
- [Publishing releases](docs/development/releasing.md): package checks and release troubleshooting.

For contributions, start with [Developing Logistics](docs/development/development.md)
for setup, code ownership and focused checks through `python3 dev.py --help` (`py dev.py --help` on Windows).
Feature changes should include updates to their user guides. The application uses
Python 3.12.2 and pinned dependencies; normal launchers manage that environment.
Git and optional external tools are installed/configured separately.

## License

Logistics is available under the [MIT License](LICENSE.md).

Logistics can update itself from published main, beta or alpha releases through
**Update Logistics** in the hub. Checks are on by default; choose a channel or
turn them off in **Settings → Configuration → Updates**. Updates preserve private
software, credentials and ignored files. See [release packaging](docs/development/releasing.md)
for supported installation manifests and channel tags.
