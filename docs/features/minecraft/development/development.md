# Minecraft feature

The desktop feature contributes a local-folder server selector to Workspaces,
not a standalone destination. See the [user guide](../user/user.md) and
[mobile availability](../user_mobile/user_mobile.md). Shared contribution contracts
are described in [feature conventions](../../../development/features.md).

## Owners and registration

- `Python/features/minecraft/__init__.py` exposes `register()` and the compatibility
  `get_contributions()` entry point, lazily importing `ui_contributions.py`.
- `ui_contributions.py` returns a `Feature` with one `FolderFeatureContribution`
  named Minecraft, order 20. It requires a local entry and detected servers.
  Its flat action list is empty; `create_widget` imports the Qt widget lazily.
- `detection.py` is the active discovery path. It asks `Directory.list_directories`
  for immediate children plus two additional levels (`MAX_SERVER_DEPTH = 3`),
  then admits only directories with a regular `server.properties` file. The
  selected root itself is excluded. There is no fixed Dropbox root or name-based
  Backups exclusion in this discovery path.
- `server.py` owns edition classification, configured application/working-directory
  resolution, wiki lookup and external folder/editor/browser actions.
- `ui/folder_widget.py` owns `MinecraftFolderWidget`, Java/Bedrock filtering,
  initial edition selection and action enablement. Import that owner directly;
  there is no root `folder_widget.py` compatibility module.

`server.py` also retains `get_minecraft_server_lst`, an older immediate-child
helper that excludes names ending in `Backups` and does not require the properties
marker. The current contribution/widget use `detection.get_servers`, not that
legacy helper. Keep their behavior distinct when maintaining callers.

## Launch and action boundaries

Either Bedrock executable name classifies the directory as Bedrock regardless of
host OS. The launch adapter then requires the matching platform file: Windows
`bedrock_server.exe`, or Linux `bedrock_server` with execute permission. macOS has
no Bedrock application adapter. Other nonempty directories are classified Java;
active discovery already requires the properties marker.

Java launch lookup reads `[LaunchScript] win`, `mac` or `linux` from the server's
`logistics_cfg.ini`. A non-None value constructs `DiskApp` with the server folder
as working directory. `is_launchable()` checks that an adapter exists; it does
not validate Java availability or script contents. `launch_server()` delegates to
that adapter and reports an error when it is absent. No server lifecycle monitor,
embedded console or stop action is registered.

The wiki uses `[Documentation] wiki`; availability checks for a non-None value,
not successful URL access. Folder availability checks the directory, and property
editing checks the file before using the external default editor. Editing does
not reload a running server. See the user guide for the complete INI example.

## Platform scope and validation

`Python/services/mobile_features.py` does not register Minecraft. No mobile
feature adapter is provided. Desktop folder presentation also keeps local-only
detectors away from private LocalCrypt entries; remote browsing is not a Minecraft
server execution environment.

`Python/tests/integrations/test_minecraft_platforms.py` covers Linux execute
permission gating and rejection of a Windows-only Bedrock binary on Linux, using
mocked platform/application adapters without starting a server. The permission
case is skipped on Windows. The private-folder case in
`Python/tests/files/test_folder_sources_ui.py` checks that local-only feature
detectors are not invoked for a private encrypted copy, including Minecraft's
contribution. These tests do not establish real Java/Bedrock startup or desktop
console behavior on Windows, macOS or Linux.

This documentation audit reviewed source and test contracts and ran static
Markdown/link checks only. No Qt session, server, build or device was launched;
real server startup acceptance remains outside this audit.
