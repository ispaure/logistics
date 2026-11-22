"""Versioned project registrations outside source repositories."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import dataclass, field, asdict
from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
from uuid import uuid4
from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.streams import read_up_to
from features.preferences import preferences_path

MAX_WORKSPACE_BYTES = 4 * 1024 * 1024


def matches_exclusion_pattern(relative, patterns):
    """Match a glob against any file or ancestor directory name."""
    return any(fnmatchcase(part, pattern) for part in relative.parts for pattern in patterns)


def is_excluded(relative, rules, patterns=()):
    """Match a name anywhere or a slash-separated path from the project root."""
    return (any(part in rules for part in relative.parts) or any(
        path.as_posix() in rules for path in (relative, *relative.parents) if path.parts)
        or matches_exclusion_pattern(relative, patterns))


class ProjectFolderRoles:
    """Resolve source roots once and apply project rules to each folder path."""

    def __init__(self, root, sources, exclusions, patterns):
        self.root = root
        self.sources = {path for value in sources
                        if (path := self.source_folder(value)) is not None}
        self.exclusions = frozenset(exclusions)
        self.patterns = tuple(patterns)

    def source_folder(self, value):
        try:
            return (self.root / Path(value).expanduser()).resolve() if self.root else None
        except (OSError, RuntimeError, ValueError):
            return None

    def status(self, path):
        if self.root is None or not path.is_relative_to(self.root):
            return ''
        if is_excluded(path.relative_to(self.root), self.exclusions, self.patterns):
            return 'Excluded'
        for folder in (path, *path.parents):
            if folder in self.sources:
                return 'Source'
            if folder == self.root:
                break
        return ''


@dataclass
class Project:
    name: str
    root_path: str
    id: str = field(default_factory=lambda: str(uuid4()))
    source_paths: list[str] = field(default_factory=lambda: ['.'])
    excluded_paths: list[str] = field(default_factory=lambda: ['.git', '.venv', '__pycache__', 'node_modules', 'build', 'dist'])
    python_interpreter: str | None = None
    layout: dict = field(default_factory=dict)
    autosave: str = 'after_delay'
    column_guide: int = 120
    excluded_patterns: list[str] = field(default_factory=list)

    @property
    def root(self):
        return Path(self.root_path).expanduser().resolve()

    def sources(self):
        return list(dict.fromkeys(str((self.root / Path(p).expanduser()).resolve()) for p in self.source_paths))

    def environment(self):
        if not self.python_interpreter:
            return None
        # A virtualenv's Python often links to the base interpreter. Keep the
        # executable's location so Python can find the environment beside it.
        return os.path.abspath(self.root / Path(self.python_interpreter).expanduser())

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Invalid IDE project')
        for key in ('name', 'root_path', 'id'):
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f'Invalid project {key}')
        for key in ('source_paths', 'excluded_paths', 'excluded_patterns'):
            if key in data and (not isinstance(data[key], list) or not all(isinstance(p, str) for p in data[key])):
                raise ValueError(f'Invalid project {key}')
        if data.get('autosave', 'after_delay') not in ('off', 'after_delay', 'focus_change'):
            raise ValueError('Invalid autosave mode')
        if type(data.get('column_guide', 120)) is not int or not 0 <= data.get('column_guide', 120) <= 1000:
            raise ValueError('Column guide must be an integer between 0 and 1000')
        if not isinstance(data.get('layout', {}), dict):
            raise ValueError('Invalid project layout')
        if data.get('python_interpreter') is not None and not isinstance(data['python_interpreter'], str):
            raise ValueError('Invalid interpreter')
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ProjectStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else preferences_path().parent / 'IDE' / 'workspace.json'
        self.projects = {}
        self.open_ids = []
        self.active_id = None
        self.error = None
        self.original = None
        try:
            if self.path.exists():
                with self.path.open('rb') as stream:
                    self.original = read_up_to(stream, MAX_WORKSPACE_BYTES + 1)
                if len(self.original) > MAX_WORKSPACE_BYTES:
                    raise ValueError('IDE workspace exceeds 4 MiB')
            if self.original is not None:
                data = json.loads(self.original)
                if not isinstance(data, dict) or data.get('version') != 1:
                    raise ValueError('Unsupported IDE workspace version')
                if not isinstance(data['projects'], list):
                    raise ValueError('Invalid IDE project list')
                projects = [Project.from_dict(p) for p in data['projects']]
                by_id = {p.id: p for p in projects}
                if len(by_id) != len(projects):
                    raise ValueError('Duplicate IDE project identifiers')
                open_ids = data['open_ids']
                if not isinstance(open_ids, list) or not all(isinstance(p, str) for p in open_ids):
                    raise ValueError('Invalid open project identifiers')
                active_id = data.get('active_id')
                if active_id is not None and not isinstance(active_id, str):
                    raise ValueError('Invalid active project identifier')
                # Publish only after the complete checkpoint has been validated.
                self.projects = by_id
                self.open_ids = list(dict.fromkeys(p for p in open_ids if p in by_id))
                self.active_id = active_id
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            self.error = str(error)

    def save(self):
        if self.error:
            raise ValueError(f'Workspace preserved at {self.path}: {self.error}')
        def validate():
            current = None
            if self.path.exists():
                with self.path.open('rb') as stream:
                    current = read_up_to(stream, MAX_WORKSPACE_BYTES + 1)
            if current != self.original:
                raise OSError('IDE workspace changed in another instance. Restart to load it.')
        content = json.dumps(dict(version=1, projects=[asdict(p) for p in self.projects.values()],
                                  open_ids=self.open_ids, active_id=self.active_id), indent=2).encode()
        if len(content) > MAX_WORKSPACE_BYTES:
            raise ValueError('IDE workspace exceeds 4 MiB')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self.path, content, validate=validate)
        self.original = content
