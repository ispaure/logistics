"""Inventory compatibility import paths without importing toolkits or features."""
import json
from pathlib import Path
from .architecture import references

ROOT = Path(__file__).resolve().parents[1]


def inventory(root=ROOT):
    entries = json.loads((root / 'Scripts/compatibility.json').read_text())['modules']
    paths = []
    for area in ('features', 'services', 'ui_new', 'logisticsmobile'):
        for path in (root / 'Python' / area).rglob('*.py'):
            if 'emulation' not in path.parts and '__pycache__' not in path.parts and not path.is_symlink():
                paths.append(path)
    imports = {path: references(path, root / 'Python') for path in paths}
    for name, canonical in entries.items():
        source = root / 'Python' / (name.replace('.', '/') + '.py')
        if not source.is_file():
            raise ValueError('Missing compatibility module: ' + name)
        for target in canonical:
            module = root / 'Python' / target.replace('.', '/')
            if not module.with_suffix('.py').is_file() and not (module / '__init__.py').is_file():
                raise ValueError('Missing canonical target: ' + target)
        consumers = [path.relative_to(root).as_posix() for path, refs in imports.items()
                     if path != source and any(ref == name or ref.startswith(name + '.') for ref in refs)]
        yield name, canonical, consumers
