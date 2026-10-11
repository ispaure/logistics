# Configuration, state and compatibility

[Developer index](README.md) · [User configuration guide](../../CONFIGURATION.md)

## Choose the correct owner

Launcher paths belong in `launch_config.ini`; resource/managed folder roots and
application exclusions belong in `Python/configFile.ini`. Feature-wide defaults
belong in `Python/features/<feature>/config.ini`. Folder-owned `remoteConfig.ini`
keys remain with the folder and its integration. Do not infer that all integrations
inherit settings from ancestors: archive password lookup has its own rules.

Use shared INI/schema editors for typed fields and retain fallback reads when
migrating public keys. `_str`, `_int`, `_float`, `_bool`, typed lists and `_mode`
are Logistics' chosen schema; an ordinary INI reader still returns strings.
Feature settings contributions declare their scope explicitly; personal controls
can coexist with application-level configuration files. Saving a config need not
reconfigure an already running worker or reader.

## Persistence map

| Data | Location/owner | Compatibility consequence |
| --- | --- | --- |
| Disabled feature names | Logistics `preferences.ini` | Stable feature IDs; load before initialization |
| Git options, bookmarks and subtree mappings | `git.json` beside Logistics preferences | Preserve malformed files; credentials belong in secure helpers |
| Editor appearance, recent paths and checkpoints | shared Cache/TextEditor | Recovery files may contain unsaved private text; do not treat as disposable thumbnails |
| EPUB reading state/bookmarks | shared Cache/Books, hashed resolved book path | Moving a book changes identity; state does not contain the book |
| Comic resume positions | shared Cache/Comics, hashed resolved comic path | Last successfully displayed page; restore by image entry name, then bounded index; shares Books' remember-position setting |
| Browser index/search metadata | shared index/storage service | Partial saved snapshots are not proof of a complete filesystem scan |
| Remote credential packages | configured private resource directory | Never commit secrets; package basename identifies generated config |
| rclone configs | config directory chosen by the rclone integration | Same-named configs/packages can collide; deletion controls act on real configs |
| FUSE mounts | managed mount root/config-path hash/remote | Moving a credential config changes mount identity |
| Managed local sync folders | managed local root/remote name | Credential identity does not isolate local destinations |
| Backups and staging | workflow-specific, often beside affected files | Keep documented recovery paths; there is no global application Undo |

Logistics preferences live at `~/Library/Application Support/Logistics` on macOS,
`%APPDATA%/Logistics` (with a home-directory fallback) on Windows, and
`$XDG_CONFIG_HOME/logistics` or `~/.config/logistics` on Linux. commonUtils cache,
temp and settings paths are separate; use its storage helpers, not hard-coded
Logistics preference paths. Feature enablement is saved atomically; malformed
preferences are retained under a `.broken-...` name where possible.

## Compatibility requirements

`features.code_font` owns Logistics' shared code point size (9 by default),
persisted as `Editor.font_size_int` in Cache/TextEditor/preferences.ini. IDE,
Text Editor and Git code views register with the QApplication-owned controller;
zoom propagates within the same preference-path group, including split and review
views. Git's serialized diff font supplies the family, not a separate size.
Unrelated preferences and text recovery data are retained when saving the size.

Stable feature IDs, workflow IDs, configuration keys and public compatibility
imports are contracts to examine before changing them. Preserve file formats and
saved-state precedence; test old configuration fixtures when introducing new keys.
Comic compression has an explicit [output contract](../../Python/features/comics/COMPRESSION.md),
including rebuilding page records after page changes. Do not generalize one
workflow's preservation or cancellation policy to all operations.

External-tool credentials, private presets, software resources and cache content
are not public distribution assets. Publication logic must check names, links,
source changes and existing destinations according to the owning workflow.
Use the documented platform checks for changes involving file identity, case,
Unicode normalization, permissions, process termination or native UI behavior.
