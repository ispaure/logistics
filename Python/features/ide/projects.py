"""Versioned project registrations outside source repositories."""
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
from uuid import uuid4
from commonUtils.persistence import atomic_write_bytes
from features.preferences import preferences_path


@dataclass
class Project:
    name: str
    root_path: str
    id: str = field(default_factory=lambda: str(uuid4()))
    source_paths: list[str] = field(default_factory=lambda: ['.'])
    excluded_paths: list[str] = field(default_factory=lambda: ['.git', '.venv', '__pycache__', 'node_modules', 'build', 'dist'])
    python_interpreter: str | None = None
    layout: dict = field(default_factory=dict)

    @property
    def root(self):
        return Path(self.root_path).expanduser().resolve()

    def sources(self):
        return list(dict.fromkeys(str((self.root / Path(p).expanduser()).resolve()) for p in self.source_paths))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Invalid IDE project')
        for key in ('name', 'root_path', 'id'):
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f'Invalid project {key}')
        for key in ('source_paths', 'excluded_paths'):
            if key in data and (not isinstance(data[key], list) or not all(isinstance(p, str) for p in data[key])):
                raise ValueError(f'Invalid project {key}')
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
                if self.path.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError('IDE workspace exceeds 4 MiB')
                self.original = self.path.read_bytes()
            if self.original is not None:
                data = json.loads(self.original)
                if data.get('version') != 1:
                    raise ValueError('Unsupported IDE workspace version')
                projects = [Project.from_dict(p) for p in data['projects']]
                self.projects = {p.id: p for p in projects}
                self.open_ids = list(dict.fromkeys(p for p in data['open_ids'] if p in self.projects))
                self.active_id = data.get('active_id')
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            self.error = str(error)

    def save(self):
        if self.error:
            raise ValueError(f'Workspace preserved at {self.path}: {self.error}')
        def validate():
            current = self.path.read_bytes() if self.path.exists() else None
            if current != self.original:
                raise OSError('IDE workspace changed in another instance. Restart to load it.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self.path, json.dumps(dict(version=1, projects=[asdict(p) for p in self.projects.values()],
                                        open_ids=self.open_ids, active_id=self.active_id), indent=2).encode(), validate=validate)
        self.original = self.path.read_bytes()
