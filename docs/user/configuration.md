# Configuration and resources

Open **Logistics Settings** from the rail or floating Settings button.
Use **Features** to choose available tools and the [feature guides](features.md)
for setup. Use **Open-source licenses** in Settings to read installed notices
offline.

## Configuration layers

| File | What it controls |
| --- | --- |
| [launch_config.ini](../../launch_config.ini) | Launcher and startup paths |
| [Python/configFile.ini](../../Python/configFile.ini) | Managed folders, resource paths and exclusions |
| `Python/features/<feature>/config.ini` | Defaults for that feature |
| remoteConfig.ini in a managed folder | Settings for that integration or folder |
| [Python/software_manifest.json](../../Python/software_manifest.json) | Pinned public software downloads |

Each feature defines how its folder settings apply. See
[Archives](../features/archives/user/user.md) and
[Comics](../features/comics/user/user.md) for archive passwords.

## Feature INI settings

Save explicitly. Invalid values or concurrent file changes block the save.
Key suffixes determine the setting's type. A mode can use a companion list
for its dropdown. Unsuffixed keys remain as text.

| Key suffix | Value |
| --- | --- |
| _str, _mode | Text or one named choice |
| _int, _float, _bool | Whole number, decimal or true/false |
| _list-str, _list-int, _list-float, _list-bool | JSON list of that type |

```ini
[Display]
preview_bool = true
scale_float = 1.25
view_mode = tiles
view_choices_list-str = ["tiles", "list", "columns"]
```

See [configuration and data](../development/architecture/configuration-and-data.md)
for schema details.

## Managed data paths

**DirectoryStructure** in **Python/configFile.ini** selects the platform
server root and the Local and NetworkMount subfolders. Defaults put local
copies under **~/Server/Local** and mounts under **~/Server/NetworkMount**,
grouped by credential configuration and remote. Update the launcher's
**ensure_user_dir** too if you change which directory it creates.

**Folders** exclusions are comma-separated and case-insensitive. Exact remote
names hide remote entries. Folder suffixes apply to both local and remote
entries. The filters keep files on disk.

## Private resource directories

Software and rclone credentials normally use **Software/** and
**Credentials/rclone/**. Under **Resources**, set **software_path** or
**credentials_path** independently to use another location. Relative paths
start at the checkout root. **blender_addons_path** can point to an optional
read-only library of provided ZIPs.

A saved rclone config uses the ZIP's base name. Use distinct names for
distinct configurations. Keep credentials and passwords in private locations,
outside tracked example INIs.

## Tools and integrations

See [rclone credentials](../features/rclone/user/user.md#set-up-credentials),
[rclone download versions](../features/rclone/user/download-versions.md),
[FUSE mount setup](../features/fuse/user/user.md) and
[Text Editor preferences](../features/text_editor/user/preferences.md).

## Destructive folder tools

**Python/maintenance.ini → FolderSafety** controls protection for WEBP and
PYC maintenance. System and application folders are protected by default,
including when a recursive selection contains one. Add paths through
**additional_protected_paths**. A missing policy file blocks these tools.

## Editing in the application

**Settings → Configuration** edits the launcher, application and maintenance
INIs. Save explicitly. Shared configuration changes may need a restart.
Manage generated rclone configurations from **Settings → rclone**.

## Software defaults and personal settings

**Personal Settings** writes only overrides. **↶** removes an override so the
software value applies again. **Default Software Configuration**, where
available, edits the tracked defaults shown above the fields. Save explicitly.

**Reset All Personal Settings…** removes overrides and unsaved personal
configuration edits across all categories. It keeps documents, accounts,
workspaces, reading progress and Blender presets. Launcher changes take effect
on the next launch.

## Appearance and workspace layout

**Appearance & shared controls → Styling** changes theme, accent and
interface, browser, reading and code fonts. Blank families use platform
defaults. Preview changes and choose **Save Settings** to update open views.

Under **Appearance & shared controls → Menus**, **Launch with sidebar**
controls the next launch. Choose **Open full hub with sidebar** to restore
the rail from a focused workspace.

## Logistics updates

In **Configuration → configFile.ini → Updates**, turn update checks on or off
and choose **main**, **beta**, or **alpha**. The default checks published main
releases. **Update Logistics** appears on the landing page when a release is
available. It runs the normal close and save flow before restarting. Local
changes or file collisions can stop the update. Git checkouts need clean
tracked files and initialized submodules. Older extracted releases may need
a fresh extraction.
