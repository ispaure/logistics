# Minecraft feature

Minecraft adds server discovery and launch controls to desktop Workspaces.

## Try a Linux launch check

1. Enable **Minecraft Server** in desktop **Settings → Features**. In the
   managed local workspace root (default `~/Server/Local`), create
   `MinecraftProbe/ProbeServer` with an empty `server.properties` and an empty
   `bedrock_server` file. In **Workspaces → Local → Rclone Copies**, use
   **Refresh folders**, select **MinecraftProbe** and open **Actions**.
   The **Minecraft** section should open on **Bedrock**. On Linux, a file
   with mode `0644` leaves **Launch Server**
   disabled. Change it to `0755`, refresh and reselect the workspace. Expect
   the button to become enabled. Leave the button unpressed and remove the
   disposable folder after trying it.
2. In `Python/features/minecraft/ui/folder_widget.py`,
   `MinecraftFolderWidget._show_server()` sets button enablement from
   `MinecraftServer.is_launchable()`. Follow that to
   `MinecraftServer.__get_disk_app()` in `Python/features/minecraft/server.py`.
   As a temporary change, replace the Linux permission check's `os.X_OK`
   with `os.R_OK`. This would offer to launch the readable but nonexecutable
   file. Run the check, then restore `os.X_OK` and run it again.

Run from the repository root with the desktop environment set up, on Linux
or macOS:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_minecraft_platforms.py
```

Expect `test_linux_binary_is_bedrock_and_requires_execute_permission` to fail
with the temporary change and both tests to pass after restoring it. The suite
mocks Linux and the launch adapter. The execute-permission case requires a
POSIX host and skips on Windows.

## Owners and registration

`Python/features/minecraft/__init__.py` exposes `register()` and the compatibility
entry point `get_contributions()`. `ui_contributions.py` declares the
`FolderFeatureContribution`. Its availability check requires a local entry and
at least one detected server. Workspaces calls the widget factory after
detection. The factory imports `ui.folder_widget.MinecraftFolderWidget` on
demand. Import the widget from that module for desktop UI changes.

`detection.get_servers()` calls `Directory.list_directories` with
`MAX_SERVER_DEPTH - 1` to inspect ordinary directories one to three levels
beneath the selected root. A candidate must contain a regular
`server.properties` file. Choose the containing workspace if a server is
missing. `server.get_minecraft_server_lst()` is an older helper for immediate
children, skipping names ending in `Backups` and accepting candidates without
the marker. Workspaces uses `detection.get_servers()` and applies no
name-based `Backups` exclusion.

## Launch and action boundaries

The widget starts on Java when Java servers exist, otherwise Bedrock. Either
Bedrock executable name classifies the directory as Bedrock on any desktop OS.
The launch adapter requires `bedrock_server.exe` on Windows or an executable
`bedrock_server` on Linux. macOS has no Bedrock launch adapter. An ordinary
discovered directory with no Bedrock executable name uses the Java path.

For Java, `server.py` looks up `[LaunchScript] win`, `mac` or `linux` in
`logistics_cfg.ini`. A configured value creates a `DiskApp` with the server
directory as its working directory. `is_launchable()` checks for that adapter.
Check the script and runtime if startup fails. Logistics delegates launch and
leaves process management to the server's own controls.

`[Documentation] wiki` enables **Open Wiki** when configured. **Open Folder**
and **server.properties** depend on the directory or file existing. Logistics
hands off to the system browser, file manager or editor for those actions.
Reload properties through the server after editing if needed. See the
[user guide](../user/user.md#configure-launching) for the INI example.

## Platform scope and validation

Workspaces excludes private LocalCrypt copies from ordinary local detection.
The private-folder case in `Python/tests/files/test_folder_sources_ui.py`
registers Minecraft among the folder tools and checks that the private
workspace keeps backend-aware controls while bypassing local-only detection.
The platform tests check launch adapter selection using synthetic files.
Actual Java and Bedrock process startup remains a separate desktop check.

Minecraft is absent from the mobile catalog in `Python/services/mobile_features.py`.
See [mobile availability](../user_mobile/user_mobile.md) and
[feature conventions](../../../development/architecture/features.md).
