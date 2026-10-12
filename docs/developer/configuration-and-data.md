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
| Blender installations and presets | per-user Logistics root: `software/blender/<version>` and `preferences/blender/<version>/<preset>` | Separate from global software resources; removal preserves presets; copies retain embedded absolute paths |
| Feature choices | configFile.ini defaults and sparse personal FeatureOverrides | Stable feature IDs; explicit matching choices persist until reset |
| Git options | feature config.ini and personal override | Scalars are exposed in central Settings |
| Git accounts, actions, bookmarks and subtree mappings | `git.json` beside Logistics preferences | Preserve malformed files; credentials belong in secure helpers |
| Editor settings | feature config.ini and persistent personal override; shared Styling fonts | Legacy cache settings migrate once |
| Editor recent paths and checkpoints | shared Cache/TextEditor | Recovery files may contain unsaved private text; do not treat as disposable thumbnails |
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

commonUtils owns shared code family and point size (11 by default) in
`ui/settings.ini [Styling]`, layered with persistent personal overrides.
Production Text Editor, IDE, Git and Markdown code use the QApplication-owned
styling controller. `features.code_font` retains a compatibility entry point for
explicit preferences-path consumers. Appearance changes preserve document text,
modified flags and recovery data.

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

## Central software/personal configuration

`features.settings` owns the application path mapping and registers repository
INIs with commonUtils at startup. Settings pages and launch bootstrap import
that owner directly. Persistent overrides are under the platform Logistics AppData
root, `configuration/<Python-relative INI path>`; shared controls map to
`configuration/commonUtils/settings.ini`. The root launcher maps to
`configuration/launch_config.ini`. Bootstrap wrappers pass that personal path to
the shared launcher, including before Python dependencies are available.

SettingsPage propagates one application/personal scope to all category panels.
It starts in personal scope and offers application scope in its selector only
when `Path.home().name == 'marca'`.
Its global personal-reset action calls `services.preferences.reset_personal_preferences()`.
That service coordinates `features.settings.reset_personal_configuration()`, feature
activation, shared notifications and host-supplied view reload callbacks. The Settings
widget owns confirmation, its dirty-editor policy and result text. Only
`configuration/` is replaced. Completion is recorded through
commonUtils' MigrationLedger in `state/settings-migrations.ini`, outside resettable
overrides. Existing legacy completion markers are adopted once; pending imports
retry idempotently after partial failures. Reset deliberately completes the legacy
migration IDs, so old preferences cannot return even when their personal INIs are
absent. Migration metadata rolls back along with failed resets. The prior tree is kept
outside temporary staging until feature-default activation succeeds; failures
restore it or retain a named recovery directory. Personal layered editors discard
pending edits and reload, while application-editor pending values remain intact.
The registry notifies navigation observers and styling reloads immediately. Styling,
Text Editor, Books and Git subscribe to shared change detection instead of owning
separate preference polling timers. Layered saves notify after publication; one
application monitor detects external changes every 500 ms and queues GUI callbacks.
Subscriptions retire with their QObject owners. Launcher values apply at launch.
Each panel retains editors for both scopes and checks all dirty editors on close.
Feature schemas declare exposed systemic settings; runtime book positions,
recovery, folder credentials and Git account/action records retain their own
persistence. The feature-enable baseline is `[FeatureDefaults] disabled_list-str`
in configFile.ini; old personal feature defaults migrate once with a marker.

Editor cache font/options migrate to persistent INIs. Git scalar JSON options
migrate to the feature INI while identity/account/action records remain JSON.
Books use central appearance with position/bookmarks retained per book. Production
Text Editor binds commonUtils' shared code controller; explicit preferences paths
retain compatibility for isolated hosts/tests. Typography changes do not write
source documents. Shared mechanics and font-role API contracts live in the
[commonUtils configuration guide](https://github.com/ispaure/commonUtils/blob/main/configuration/README.md)
and [styling guide](https://github.com/ispaure/commonUtils/blob/main/ui/styling.md).

Feature defaults remain `[FeatureDefaults] disabled_list-str`; personal feature
choices use `[FeatureOverrides] <feature_id>_bool`. Only an explicit toggle (or a
dependency that must be enabled) writes a key. Equal-to-default values remain
explicit; the reset arrow removes the key. Untouched features resolve against
current defaults at startup. The retryable `feature-overrides-v2` migration removes
the old personal selection snapshot while preserving differing choices and
unrelated settings. Whole-preference reset also marks this migration complete.

Blender release catalogs use `features/blender/config-<exact-version>.ini`, one
file per version with platform sections. Initialization registers each file with
its matching sparse personal layer; the feature's custom Settings panel retains
one shared field editor per version/scope. The retryable
`blender-release-files-v1` migration copies matching fields from the old personal
combined catalog without deleting it or overwriting new-format choices. Whole
personal reset marks that migration complete alongside feature/editor/Git migrations;
Blender presets and installations remain outside the configuration reset boundary.

## Blender addon library and credentials

Blender's feature-owned library is stored under the per-user Logistics root at
`addons/blender/<kind-module>/<numeric-version>/addon.zip`; it is independent of
checkout credential packages. Each preset's `.logistics-addons.json` records chosen
identities and the published module/path/digest inventory. Imports read metadata
without executing code. Applying or launching a managed selection resolves latest
compatible releases, copies files, enables modules through background Blender and
saves preferences; failed updates restore preset resource folders. See the
[Blender contracts](../../Python/features/blender/README.md).

The default credential ZIP root is now `Credentials/rclone` in the checkout, with
read-only discovery of the matching Dropbox location. `RemoteCredentials` is no
longer searched. Existing `~/.config/rclone/*.conf` files remain independently
available. The whole checkout `Credentials/` tree is ignored, reserving
`Credentials/blender_addons` for future private manifests. No Blender credential
manifest format or download implementation is defined yet.

Blender now merges that personal library with an optional read-only provided ZIP
folder (`[Resources] blender_addons_path`, default checkout `Addons/blender`).
Personal wins on equal identity/version, with latest compatible selection over both
sources. The ignored provided folder is never created or modified automatically.
Managed activation uses alphabetical display-name order and sorted CLI `--addons`
plus a startup script; ordinary Blender initialization precedes this controlled
reactivation. Saved addon preferences survive reactivation. See the feature's
layering/activation contract for details.

Blender personal settings show Presets first, then Versions Definitions for admin
maintenance of the installable release catalog. Default software scope shows only
Versions Definitions. The launch page
links to Settings; creating presets/saving selections does no provisioning. Blue Hole
has dedicated enabled/branch/Deluxe state in the preset selection JSON, plus its
resolved commit and Deluxe payload digest. It uses a separate commit-keyed private
cache and GitHub branch comparison on each enabled launch. Deluxe stamping is
preset-contained and part of the existing rollback transaction; unchanged payloads
preserve subsequent preference customization. See the feature guide for these contracts.
