# Logistics

Logistics brings file browsing, document readers and editors, media tools and
remote-folder management into one app. Start with files already on your computer,
then add libraries, servers or encrypted offline copies as you need them.

The desktop app runs on Windows, macOS and Linux. An Android/iOS development app
supports a smaller set of document and storage workflows. Some tools need
another application or service configured separately.

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

## Find your way around

After opening Logistics, start with **File Browser** and a local text or Markdown
file. **Documents** brings you back to open readers and editors. **Workspaces**
collects local libraries, cloud locations and SMB servers. Use **Home Server →
Add server…** to browse and download files from a Mac, PC or NAS. **Settings**
controls feature availability and configuration.

The [desktop guide](docs/user/user.md) walks through the first local document and
explains those parts of the app. Continue with
[files and documents](docs/user/files-and-documents.md) for browsing and tabs, or
[configuration](docs/user/configuration.md) when you are ready to set up a tool.

## Explore the tools

| What you want to do | Where to start |
| --- | --- |
| Read and edit documents | [Text Editor](docs/features/text_editor/text_editor.md), [Notes Library](docs/features/notes_library/notes_library.md), [Books](docs/features/books/books.md), [Comics](docs/features/comics/comics.md), [PDF](docs/features/pdf/pdf.md) and experimental [Notebooks](docs/features/notebooks/notebooks.md) |
| View and process media | [Images](docs/features/images/images.md), [Video Player](docs/features/video/video.md) and [audio chapter tools](docs/features/media/media.md) |
| Organize files | [File Browser](docs/user/files-and-documents.md), [Bulk Rename](docs/features/bulk_rename/bulk_rename.md) and [Archives](docs/features/archives/archives.md) |
| Connect storage, keep offline copies and resume interrupted downloads | [rclone connections and LocalCrypt](docs/features/rclone/rclone.md), [FUSE mounts](docs/features/fuse/fuse.md) and [Dropbox tools](docs/features/dropbox/dropbox.md) |
| Work with code and language models | [Git](docs/features/git/git.md), [IDE](docs/features/ide/ide.md) and [LM Chat](docs/features/lm/lm.md) |
| Use configured applications and utilities | [Feature catalog](docs/features/features.md), including Calibre, Blender, Plex, Obsidian and platform tools |

The [feature catalog](docs/features/features.md) explains each tool's purpose and
links to its desktop, mobile and developer guides. Check a feature's prerequisites
and recovery guidance before applying batch or remote changes.

Additional emulator tools are available on request through ispaure’s **ally-tools**.

## Use Logistics on mobile

Start with the [mobile guide](docs/user_mobile/user_mobile.md) for Android and iOS.
It covers local files, text and Markdown editing, supported readers, LM Chat,
remote transfers, encrypted copies and [on-device archives](docs/features/archives/user_mobile/user_mobile.md). It also explains differences in navigation,
storage and platform support. Help is bundled in the app for offline use.

For local builds, device installation or Firebase/TestFlight distribution, use
[Build and release](docs/development/build-release/build-release.md). The standalone
Build Deployment Manager runs the reviewed workflows through the Logistics adapter.

## Contribute

Start with the [developer guide](docs/development/development.md). It leads from
running a checkout to understanding the app, choosing a change and checking it.
The [first-run walkthrough](docs/development/setup/getting-started.md) uses the
pinned Python environment and local files.

`python3 dev.py doctor` checks the local environment; `python3 dev.py --help`
lists the contributor commands. Use `py` on Windows. The project uses Python
3.12.2 and pinned dependencies, with separate desktop and mobile host environments.

For a particular task, use [architecture](docs/development/architecture/architecture.md),
[testing](docs/development/testing/testing.md) or
[documentation maintenance](docs/development/documentation/documentation.md).
Shared commonUtils API documentation belongs in that library's own repository.

## Documentation and updates

The [documentation wiki](docs/docs.md) is the home for user guides, feature
manuals and contributor documentation. In-app Help opens the same guides.

Use **Update Logistics** in the hub to update from published main, beta or alpha
releases. Update checks are on by default; choose a channel or turn them off in
**Settings → Configuration → Updates**. See
[update settings](docs/user/configuration.md#logistics-updates) for user controls
and [release packaging](docs/development/build-release/releasing.md) for publishing.

## License

Logistics is available under the [MIT License](LICENSE.md).
