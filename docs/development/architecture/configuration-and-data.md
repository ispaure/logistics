# Configuration, state and compatibility

| Data | Owner |
| --- | --- |
| Application and feature defaults | `configFile.ini` and feature `config.ini`, registered by `features.settings` |
| Personal overrides | Logistics AppData `configuration/<Python-relative INI path>`, including `commonUtils/settings.ini` and `launch_config.ini` |
| Feature enablement | `[FeatureDefaults] disabled_list-str`, sparse personal `[FeatureOverrides] <feature_id>_bool` |
| Git identities/actions/bookmarks | `git.json`; scalar options use INI |
| Editor drafts and reader state | Owner cache/recovery directories. [Reader state](reader-state.md) |
| Blender installations and presets | Per-user `software/blender/<version>` and `preferences/blender/<version>/<preset>` |
| LocalCrypt, copy associations and FUSE | `LocalCrypt/.connections`, `Connections/Local` and config-path/remote mount identity |

Preserve public keys, feature/workflow IDs, precedence and legacy reads.
Use shared typed editors and atomic writes. Preserve BOM/newlines, invalid input
and intervening external edits. Renaming an owner key or changing an INI layer
requires a migration and legacy fixtures.

## Mobile preference ownership

`mobile/preference_schema.py` owns defaults and validation. `mobile/preferences.py`
owns private `preferences.ini`, `[Mobile]`, bounded reads, migrations and atomic
publication. Keep `mobile.preferences.DEFAULTS` and `Preferences.validate()`
compatible. Invalid or oversized input blocks saving until repaired. Widgets
use the API. Run `python3 dev.py test mobile test_mobile_preferences.py`.

## Android collection location recovery

`services.documents.locations.recover_location` validates a retained root and
marker, requires one managed folder, and creates the missing companion. It
checks root paths. `switch_location` copies and verifies document bytes before
switching.

## Central software/personal configuration

A toggle writes an explicit override even when equal to default. The reset
arrow removes that key. `PreferenceState` runs legacy migrations in order.
Preserve saved choices and leave failed imports pending for retry, including
failures of the completion marker. Test `test_feature_preferences.py`.

Whole-personal reset replaces only `configuration/`, using identity-checked
rollback and retaining the backup until feature defaults activate.
The migration ledger in `state/settings-migrations.ini` prevents old values
from returning. Failed restoration reports retained paths. Keep dirty scope
checks and application edits. `test_personal_settings_reset.py` covers failure.
Effective folder exclusions and software overlays use registered sparse values.
Shared styling and host views subscribe to preference changes.

Keep Blender's per-version catalog and preset add-on data with its owner.
Installations and private presets sit outside configuration reset.
[Blender contracts](../../features/blender/development/development.md)

`features.settings` maps each registered INI to its own personal path. Sparse
`[Folders]` lists replace the matching default list. The software resolver
overlays present `*_str` values and still applies path and download validation.
`test_folder_policy.py` and `test_software.py` exercise those consumers.

On reset failure, report configuration and ledger restoration separately.
If another writer replaced the new configuration directory, preserve it and
report the backup path. Layered editors keep their pending application changes
when reloading personal state. Shared Styling updates font roles without changing
document text or modified flags.

Migrate only legacy values that still belong to each owner. Editor options move
from cache into persistent INIs. Git scalar values move from JSON into feature
INI; identity and actions stay in JSON. Blender copies legacy combined-release
fields into version-specific INIs without replacing newer choices.

## rclone credential lifetime

Discover ZIPs in ignored `Credentials/rclone` and its read-only Dropbox
counterpart. Saved `.conf` remains independently available. Session ZIPs stay in
RAM, with virtual `.session` identities and per-child environments. Detached
FUSE requires a saved config. [Credential policies](../../features/rclone/development/credentials.md) ·
[LocalCrypt](../../features/rclone/development/localcrypt.md)

[Shared configuration APIs](https://github.com/ispaure/commonUtils/blob/main/configuration/README.md)
