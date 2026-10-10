"""Feature-owned user settings; no repository-specific config in Logistics core."""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from weakref import WeakSet
from .options import validate_options


class Preferences:
    def __init__(self, path=None):
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

    def save(self):
        # Avoid overwriting malformed settings silently.
        if self.warning: raise OSError(self.warning)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'executable': self.executable, 'repositories': self.repositories,
                           'last_repository': self.last_repository, 'subtrees': self.subtrees,
                           'options': validate_options(self.options)}, stream, indent=2)
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
