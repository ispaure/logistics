"""Preference precedence, migrations and persistence independently of activation."""
from configparser import Error
from pathlib import Path
import json
from commonUtils.runtime.diagnostics import Severity, log


class PreferenceState:
    def __init__(self, settings_store):
        self.feature_settings_store = settings_store
        self.disabled = set()
        self.path = None
        self.layered = False

    def default_disabled_features(self):
        raw = self.feature_settings_store().safe_values('application').get(('FeatureDefaults', 'disabled_list-str'), '[]')
        try:
            values = json.loads(raw)
            if isinstance(values, list) and all(isinstance(name, str) for name in values):
                return set(values)
        except ValueError:
            pass
        return set()


    def load_feature_preferences(self, path=None):
        """Load defaults before feature initialization; no package folders are renamed."""
        from ..preferences import preferences_path, load_disabled, read_legacy_disabled
        self.layered = path is None
        path = Path(path) if path is not None else preferences_path()
        if self.layered:
            store = self.feature_settings_store()
            legacy_disabled = None
            try:
                from ..settings import migration_ledger
                overrides = store.overrides()
                def migrate():
                    nonlocal legacy_disabled
                    legacy_disabled = read_legacy_disabled(path)
                    if legacy_disabled is not None:
                        store.save({('FeatureDefaults', 'disabled_list-str'): json.dumps(sorted(legacy_disabled))})
                migration_ledger(store).run('feature-enable-v1', migrate,
                                           already_applied=('Migration', 'features_bool') in overrides)
                # Later migrations consume the import. Do not complete them
                # until its data and completion marker have both been saved.
                legacy_disabled = None
                self._migrate_feature_overrides(store)
                self._migrate_notes_library(store)
            except (OSError, UnicodeError, Error, ValueError) as error:
                log(Severity.ERROR, 'Feature settings', f'Could not migrate preferences; original files preserved: {error}')
            disabled = self._effective_disabled_features(store, fallback=legacy_disabled)
        else:
            disabled = load_disabled(path)
            if path.exists():
                from ..preferences import migrate_notes_library
                disabled = migrate_notes_library(path, disabled)
        self.disabled.clear()
        self.disabled.update(disabled)
        self.path = path


    def feature_overrides(self):
        """Return explicit per-engine personal choices, including matching defaults."""
        result = {}
        for (section, key), value in self.feature_settings_store().overrides().items():
            if section == 'FeatureOverrides' and key.endswith('_bool'):
                if value.lower() in ('true', 'false'):
                    result[key.removesuffix('_bool')] = value.lower() == 'true'
        return result


    def _effective_disabled_features(self, store, *, fallback=None):
        disabled = self.default_disabled_features() if fallback is None else set(fallback)
        # Preserve the old selection if migration cannot publish; retry next launch.
        try:
            legacy = store.overrides().get(('FeatureDefaults', 'disabled_list-str'))
        except (OSError, UnicodeError, Error):
            return disabled
        if legacy is not None:
            try:
                values = json.loads(legacy)
                if isinstance(values, list) and all(isinstance(name, str) for name in values):
                    disabled = set(values)
            except ValueError:
                pass
        for name, enabled in self.feature_overrides().items():
            if enabled:
                disabled.discard(name)
            else:
                disabled.add(name)
        return disabled


    def _migrate_feature_overrides(self, store):
        from ..settings import migration_ledger
        def migrate():
            overrides = store.overrides()
            identity = 'FeatureDefaults', 'disabled_list-str'
            if identity not in overrides:
                return
            values = json.loads(overrides[identity])
            if not isinstance(values, list) or not all(isinstance(name, str) for name in values):
                raise ValueError('Invalid legacy feature selection; personal file preserved')
            disabled = set(values)
            # Legacy snapshots cannot tell deliberate matching values from untouched
            # features. Preserve differences and let matching choices inherit again.
            changes = {identity: None}
            for name in disabled ^ self.default_disabled_features():
                key = 'FeatureOverrides', name + '_bool'
                if key not in overrides:
                    changes[key] = 'false' if name in disabled else 'true'
            store.save(changes)
        migration_ledger(store).run('feature-overrides-v2', migrate)


    def _migrate_notes_library(self, store):
        from ..settings import migration_ledger
        def migrate():
            key = 'FeatureOverrides', 'notes_library_bool'
            if key not in store.overrides():
                disabled = self._effective_disabled_features(store)
                if ('text_editor' in disabled) != ('notes_library' in disabled):
                    store.save({key: str('text_editor' not in disabled).lower()})
        migration_ledger(store).run('notes-library-feature-v1', migrate)

    def _save_feature_preferences(self, changes=None):
        if self.layered:
            store = self.feature_settings_store()
            fields = ({('FeatureOverrides', name + '_bool'): None if enabled is None else str(enabled).lower()
                       for name, enabled in changes.items()} if changes is not None else
                      {key: None for key in store.overrides() if key[0] == 'FeatureOverrides'})
            if changes is None:
                fields['FeatureDefaults', 'disabled_list-str'] = None
            store.save(fields)
            return
        if self.path is not None:
            from ..preferences import save_disabled
            save_disabled(self.path, self.disabled)
