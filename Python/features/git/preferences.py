"""Feature-owned user settings; no repository-specific config in Logistics core."""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from weakref import WeakSet
from .options import validate_options


class Preferences:
    instances = WeakSet()

    def __init__(self, path=None):
        self.instances.add(self)
        self.custom = path is not None
        if path is None:
            from features.preferences import preferences_path
            path = preferences_path().with_name('git.json')
        self.path = Path(path)
        self.executable = 'git'
        self.repositories = []
        self.last_repository = ''
        self.subtrees = {}
        self.warning = ''
        self.options = validate_options({})
        data = {}
        self.views = WeakSet()
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict): raise ValueError('Expected an object')
            self.executable = str(data.get('executable') or 'git')
            self.last_repository = str(data.get('last_repository', ''))
            self.options = validate_options(data.get('options', {}))
            repositories = data.get('repositories', [])
            if not isinstance(repositories, list): raise ValueError('Invalid repository list')
            for entry in repositories:
                if isinstance(entry, dict) and isinstance(entry.get('path'), str):
                    self.repositories.append({'path': entry['path'], 'pinned': bool(entry.get('pinned'))})
            subtrees = data.get('subtrees', {})
            if isinstance(subtrees, dict):
                self.subtrees = {k: v for k, v in subtrees.items() if isinstance(v, list)}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as exc:
            self.warning = f'Could not read Git settings: {exc}. Original file has been preserved.'
        if not self.custom:
            from features.settings import settings_store
            from .configuration import config_path, FIELDS, field_key
            self.settings = settings_store(config_path())
            if data and not self.warning and not self.settings.personal.exists():
                legacy = data.get('options', {})
                changes = {('Git', field_key(key)): str(value).lower() if isinstance(value, bool) else str(value)
                           for key, value in legacy.items() if key in FIELDS}
                if 'executable' in data:
                    changes['Git', 'executable_str'] = self.executable
                for kind, colors in legacy.get('diff_colors', {}).items():
                    prefix = 'added' if kind == 'add' else 'removed'
                    for suffix, color in zip(('text', 'background'), colors):
                        changes['DiffColors', f'{prefix}_{suffix}_color_str'] = color
                try:
                    self.settings.save(changes)
                except (OSError, ValueError) as error:
                    self.warning = f'Could not migrate Git preferences: {error}. Original file has been preserved.'
            self.refresh_systemic()

    def refresh_systemic(self):
        if self.custom:
            return False
        from .configuration import defaults, FIELDS, config_path, color_settings
        from commonUtils.configuration.settings import get_setting
        values = defaults()
        scalar = {key: values[key] for key in FIELDS}
        executable = get_setting('Git', 'executable_str', 'git', path=config_path()).strip() or 'git'
        colors = color_settings()
        changed = (scalar != getattr(self, '_loaded_systemic', None) or executable != self.executable
                   or colors != getattr(self, 'color_settings', None))
        self.options.update(scalar)
        self.executable = executable
        self._loaded_systemic = scalar
        self._loaded_executable = executable
        self.color_settings = colors
        self.options['diff_colors'] = {}
        return changed

    def color_overrides(self, palette):
        if self.custom:
            return self.options['diff_colors']
        from commonUtils.ui.code_editor.diff_bands import diff_colors
        result = {}
        for kind, prefix in (('add', 'added'), ('remove', 'removed')):
            values = [self.color_settings[f'{prefix}_{suffix}_color_str'] for suffix in ('text', 'background')]
            if any(values):
                result[kind] = [value or fallback for value, fallback in zip(values, diff_colors(palette, kind))]
        return result

    def save(self):
        # Avoid overwriting malformed settings silently.
        if self.warning: raise OSError(self.warning)
        options = validate_options(self.options)
        if not self.custom:
            from .configuration import FIELDS, field_key
            changes = {('Git', field_key(key)): str(self.options[key]).lower() if isinstance(self.options[key], bool) else str(self.options[key])
                       for key in FIELDS if self.options[key] != self._loaded_systemic[key]}
            if self.executable != self._loaded_executable:
                changes['Git', 'executable_str'] = self.executable
            if changes:
                self.settings.save(changes)
            self._loaded_systemic = {key: self.options[key] for key in FIELDS}
            self._loaded_executable = self.executable
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                if not self.custom:
                    from .configuration import FIELDS
                    options = {key: value for key, value in options.items() if key not in FIELDS and key not in ('diff_font', 'diff_colors')}
                payload = {'repositories': self.repositories, 'last_repository': self.last_repository,
                           'subtrees': self.subtrees, 'options': options}
                if self.custom:
                    payload['executable'] = self.executable
                json.dump(payload, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)

    def remember(self, path):
        value = str(Path(path))
        entry = next((entry for entry in self.repositories if entry['path'] == value), {'path': value, 'pinned': False})
        self.repositories = [entry, *(other for other in self.repositories if other['path'] != value)]
        self.repositories = [other for i, other in enumerate(self.repositories) if other['pinned'] or i < 50]
        self.last_repository = value
