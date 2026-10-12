# Configuration and resources

Logistics separates launcher settings, shared application paths, feature settings
and folder-specific configuration. Start with defaults, then configure only the
integrations you intend to use. See the [feature index](README.md#what-can-it-do) for
individual workflows and platform limitations.

## Configuration layers

| Location | Owns | Path base |
| --- | --- | --- |
| [launch_config.ini](launch_config.ini) | Shared launcher, source directory, entry point and optional home directory creation | Launcher directory |
| [Python/configFile.ini](Python/configFile.ini) | Server/data roots, resource overrides and folder exclusions | Depends on setting, described below |
| `Python/features/<feature>/config.ini` | Feature-wide settings, including Books, Links, Smart Home and rclone | Feature-defined |
| `remoteConfig.ini` in a managed folder | Folder-specific integration settings | Feature-defined; usually the selected folder |
| `logistics_cfg.ini` in a Minecraft server | Server launch scripts and documentation URL | Server directory |
| [Python/software_manifest.json](Python/software_manifest.json) | Pinned public download versions, URLs, hashes and installation paths | Software resource root |

These INI files are not interchangeable. Each feature interprets its own sections;
there is no universal ancestor inheritance rule. In particular, archive password
inheritance belongs to [Archives](Python/features/archives/README.md) and
[Comics](Python/features/comics/README.md#password-protected-cbzs), not rclone credentials.

## Feature INI settings

Feature-wide defaults belong in `Python/features/<feature>/config.ini`, directly
beside that feature's code. Folder/library-specific configuration keeps its
existing location. Features with no configurable defaults need no empty INI.

Logistics Settings displays declared software settings as section tabs with one row
per key. Save is explicit;
invalid typed values and concurrent disk changes block saving. Comments, key case,
UTF-8 BOMs and line endings are retained when editing fields.

Logistics opts into the shared commonUtils typed-key schema; the generic
`INIFile` keeps values as strings:

| Suffix | Value / editor |
| --- | --- |
| `_str` | Text |
| `_int` | Whole number, without a 32-bit widget limit |
| `_float` | Finite decimal number |
| `_bool` | Boolean checkbox (`true` / `false`) |
| `_list-str` | String list, preferably JSON such as `["one", "two"]` |
| `_list-int`, `_list-float`, `_list-bool` | JSON list of the indicated type |
| `_mode` | Selected string, with a dropdown when companion choices exist |

For example:

```ini
[Display]
preview_bool = true
scale_float = 1.25
view_mode = tiles
view_choices_list-str = ["tiles", "list", "columns"]
```

`view_mode` stores the selected value; `view_choices_list-str` stores available
choices. Compact string lists such as `[tiles,list,columns]` also work; quote
strings containing commas using JSON. A `_mode` without companion choices uses a
text row. Numeric/list settings use editable text with validation; malformed
existing values remain visible so they can be corrected. Unsuffixed legacy keys
are displayed as text and are not automatically renamed. Links and Smart Home
prefer their new `_str` keys and still accept their old unsuffixed keys.

The [shared configuration guide](https://github.com/ispaure/commonUtils/blob/main/configuration/README.md)
covers schema APIs, editor embedding and gradual migration. Logistics keeps its
`ui_new.settings` imports as compatibility wrappers; its editor opts into typed
keys by default. Ordinary users can
edit these settings in Logistics without writing code.

## Managed data paths

The `[DirectoryStructure]` section selects `server_path_win32`, `server_path_macos`
or `server_path_linux` for the current platform. The shipped values use `Server`
under the current user's home directory. The two sub-paths select local folders
and remote mount locations:

```ini
[DirectoryStructure]
server_path_win32 = Server
server_path_macos = Server
server_path_linux = Server
remote_local_sub_path = Local
remote_network_mount_sub_path = NetworkMount
```

With these defaults, a local folder is `~/Server/Local/<folder>` and a credential-specific mount is
`~/Server/NetworkMount/<config-id>/<remote>`. The mount ID is derived from the
resolved credential config path. Local sync folders remain shared by remote name.
The launcher also has `ensure_user_dir = Server`; keep it aligned if you change
the managed root. Changing launcher creation alone does not change application paths.

`[Folders] excluded_remote_names` removes listed remote names from the Folders
view. `excluded_folder_name_suffixes` hides matching local and remote folder names
by suffix. Both lists are comma-separated and case-insensitive. Excluding a remote
by exact name does not exclude its local folder; suffix exclusions apply to both.
These filters affect discovery, not files on disk. Dedicated local sources, such
as Dropbox, remain separately selectable.

## Private resource directories

Defaults are independent directories at the checkout root:

```text
logistics/
├── Addons/
│   └── blender/  (optional provided addon ZIP library)
├── Software/
│   ├── Windows/
│   ├── macOS/
│   ├── Linux/
│   └── General/
└── Credentials/
    ├── rclone/
    └── blender_addons/  (reserved; downloads not implemented)
```

The optional provided Blender addon directory is read-only discovery and is never
created automatically. It may point to a shared studio folder. Artist imports stay
in their own per-user library and never alter provided ZIPs.

The software and rclone credential resource roots are created when configuration is loaded; platform subfolders
are created as needed. Neither root must come from Dropbox. To reuse another
location, add independent overrides to `Python/configFile.ini`:

```ini
[Resources]
software_path = Software
credentials_path = Credentials/rclone
blender_addons_path = Addons/blender
```

Relative overrides resolve from the checkout root; absolute paths and `~` paths
are supported. Either directory can point to an external/private location without
moving the other. Configuration loading requires write access to missing resource
roots so it can create them.

Credential discovery also includes Marc’s existing Dropbox folder at
`Software/GIT/logistics/Credentials/rclone` beneath his Dropbox root. Missing Dropbox
folders are skipped and never created. Packages are listed together with checkout
packages; their original locations stay unchanged. Generated configs use the ZIP’s
base name with a `.conf` extension, regardless of the package location. Same-named
ZIPs refer to the same config, including existing configs. Software provisioning continues
to use only the configured `software_path` and never searches Dropbox automatically.

`Software/`, `Addons/`, the entire `Credentials/` tree and all `.conf` files are ignored by Git.
Git ignore rules do not protect secrets placed in other tracked files or remove
already tracked content. Keep credential packages and real configuration passwords
in private locations; repository INIs should contain only safe example settings.

## Public software provisioning

[services/software.py](Python/services/software.py) selects platform/architecture,
reads the manifest and resolves the destination beneath the software root.
commonUtils supplies download verification and the confirmation/progress UI.

- **rclone:** pinned Windows, macOS and Linux builds for x86_64 and ARM64.
  A missing or mismatched executable prompts immediately before an rclone command.
- **macFUSE / WinFsp:** the mount action offers the pinned installer when driver
  support is missing. Complete the operating-system installation and retry.
- **Linux FUSE:** install device/helper support through the distribution package
  manager. Logistics has no universal Linux driver download.

Downloads verify both release and installed-file SHA-256 hashes, stage beside the
output and replace only after verification. Declining, cancellation or failure
stops the requested operation. Cancellation is cooperative between reads; an active
network read can take until its timeout to return. Ready matching files are reused.
Versions are pinned, with no automatic upgrade to the latest release.

When updating a manifest entry, change the version, HTTPS URL, download hash,
installed-file hash, archive member (if applicable) and relative destination
as one unit. The installed hash is the extracted executable's digest; for a raw
installer it matches the download digest. Validate each supported platform entry.

Other tools keep their existing prerequisites: examples include installed
Obsidian, private Calibre/7-Zip resources, FFmpeg for downloads and X-Plane presets.
An empty `Software/` directory does not provision every optional integration.

## Configure a feature

| Integration | Configuration / prerequisites |
| --- | --- |
| [rclone](Python/features/rclone/README.md) | Private credential ZIPs; generated configs in `~/.config/rclone` |
| [FUSE](Python/features/fuse/README.md) | rclone plus platform mount driver/helper |
| [Comics](Python/features/comics/README.md) | `[LogisticsComics]` library names; optional `[LogisticsZIP]` password |
| [Archives](Python/features/archives/README.md) | Workspace AES prompts; inherited `[LogisticsZIP]` for unlocking and the encrypted-selection action |
| [Calibre](Python/features/calibre/README.md) | Immediate child library with `metadata.db`; executable/device prerequisites |
| [Plex](Python/features/plex/README.md) | Matching `-PMSDATA` remote and platform server-data location |
| [YouTube Downloader](Python/features/youtube_downloader/README.md) | `[Youtube-Download]` folder config, `[Youtube-DL]` per-channel INIs and FFmpeg |
| [Minecraft](Python/features/minecraft/README.md) | `server.properties` plus `logistics_cfg.ini` for Java launch scripts |
| [Perforce](Python/features/perforce/README.md) | `[Perforce]` folder config and supplied Linux executables/data |
| [Links](Python/features/links/README.md) | Feature `config.ini` URL and hostname substitutions |
| [Smart Home](Python/features/smart_home/README.md) | Feature `config.ini` Hue bridge address and configured groups |

Images, file diagnostics and media rename workflows take their input through
individual dialogs. Dropbox discovers account roots from its installed account
configuration. See each feature guide before using its file-changing actions.

## Destructive folder tools

`Python/maintenance.ini` configures the WEBP and PYC folder protection policy:

```ini
[FolderSafety]
protect_system_folders = true
additional_protected_paths =
    ~/Important
```

System/application directories for the current OS and their descendants are
blocked, along with recursive selections that contain them. Aliases are resolved
before checking. Ordinary user folders and external drives are allowed. Extra
paths may be absolute, `~`-relative or relative to the checkout root. Changes apply
on the next operation. A missing policy file blocks these operations. Disabling
`protect_system_folders` is an explicit override; additional protected paths still
apply. Background folder tools skip directory links and preserve file links.

## Editing in the application

**Settings → Configuration** offers plain-text editing of `launch_config.ini`,
`Python/configFile.ini` and `Python/maintenance.ini`. Each feature can also provide
its own settings layout and INI editors. **Settings → rclone** manages credential
packages and generated configs. Save explicitly; shared configuration changes may
require restarting Logistics. Generated `.conf` credentials are managed by rclone’s
existing controls rather than the general INI editor.

## Rclone download versions

**Settings → rclone** exposes `Python/features/rclone/config.ini`, with one section
per supported operating system and architecture. These values override rclone's
entries in `Python/software_manifest.json`; missing override fields use the manifest.
Other software continues to use the manifest directly.

To select another release, update its version, HTTPS URL, ZIP member, destination
path and both hashes together. `sha256_str` checks the downloaded ZIP;
`installed_sha256_str` checks the executable inside it. Hash verification remains
mandatory. Destination paths must stay inside the configured Software folder.
Saving changes edits configuration only; provisioning still happens through the
existing confirmed download flow when the tool is needed. Invalid metadata is
rejected before it is used.

## Text Editor preferences

`Python/features/text_editor/config.ini` supplies typed editor defaults. Font,
indentation, wrap, gutter, whitespace, syntax and automatic editing choices made
in the window are persisted in `commonUtils/Cache/TextEditor/preferences.ini`,
using the same shared INI APIs. Private overrides take precedence over feature
defaults. **Reset Editor Preferences** removes the overrides. Recent paths use
`recent.json` in the same cache folder; window geometry is stored in the private
INI. Unsaved document content is not stored in preferences or recent history, but is
stored separately in private session checkpoints. See
[editor recovery](Python/features/text_editor/user_docs/README.md#appearance-and-preferences)
for recovery limits and shutdown behavior.

## Software defaults and personal settings

Settings defaults to **Personal Settings**. The **Default Software Configuration**
choice is available only when the current user's home folder is named `marca`.

**Reset All Personal Settings…**, at the upper-right in personal mode, resets
configuration overrides in every category after confirmation and discards unsaved
personal configuration edits. Migration completion lives separately in
`state/settings-migrations.ini` to prevent legacy settings from returning. Documents, accounts, workspaces,
reading state, managed software and Blender presets remain intact. Feature choices
and appearance refresh immediately; open tools reload their preferences, and
launcher settings apply on the next launch.

The selector at the top left of **Logistics Settings** chooses **Default Software
Configuration** or **Personal Settings** for all categories. Software mode writes
the tracked repository INI shown above the fields; commit that change to ship it
in a future release. Personal mode writes sparse overrides in the application's
persistent configuration directory. It never copies inherited fields into that
file. Each field shows **Inherited** or **Override**; **↶** removes its override,
so future software defaults apply again. In software mode, ↶ reverts an unsaved
field. Save explicitly; switching modes retains pending edits in each mode.

Personal INIs live under `configuration/` in:

- macOS: `~/Library/Application Support/Logistics/`
- Windows: `%APPDATA%/Logistics/`
- Linux: `${XDG_CONFIG_HOME:-~/.config}/logistics/` (relative XDG paths fall back to `~/.config`).

Shared controls use `configuration/commonUtils/settings.ini`; feature overrides
use `configuration/features/<feature>/config.ini`. Launcher overrides use
`configuration/launch_config.ini` and apply on the next launch. Folder-specific
integration files, reading positions, bookmarks, accounts and recovery records
retain their own storage and are not software defaults.

**Appearance & shared controls → Styling** contains 11 settings: theme, accent,
dark surface tint, and font family/point size for interface/dialogs, file browsers,
reading, and code. EPUB and Markdown share reading fonts. Text Editor, IDE, Git
hunks and Markdown code share code fonts. Blank font families select the platform
font (monospace for code). Saved styling updates open views; font changes preserve
document text and modified state. Dark tint mixes the accent into neutral dark
surfaces; zero gives neutral surfaces. The selection text follows accent contrast.

Editor, book and Git systemic options are in Feature settings. Per-tool appearance
buttons open this same Settings window. Existing editor font preferences and Git
systemic preferences migrate to personal INIs; original legacy files are retained.
Feature default enablement is stored in `[FeatureDefaults]` in `Python/configFile.ini`;
the Features category respects the same software/personal selector.

## Logistics updates

`Python/configFile.ini` supplies `[Updates] enabled_bool = true` and
`branch_mode = main`, with main/beta/alpha choices. The field is presented as
**Update channel** in **Configuration → Updates** and supports the normal personal
and software scopes. Disabled checks make no GitHub requests. Enabled checks run
at startup and approximately every fifteen minutes. Only published releases with
an uploaded, SHA-256-labelled `release.zip` qualify; no branch-HEAD fallback.
