"""Check repeated dependency pins against the canonical application manifests."""
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def pins(text):
    return {name.lower().replace('_', '-'): version for name, version in
            re.findall(r'(?im)^\s*([a-z][a-z0-9_-]*)==([0-9][^\s;\\]*)', text)}


def check(root=ROOT):
    desktop = tomllib.loads((root / 'Python/pyproject.toml').read_text())
    mobile = tomllib.loads((root / 'Mobile/pyproject.toml').read_text())
    host = pins((root / 'Mobile/requirements-host.in').read_text())
    host.update(pins((root / 'Mobile/requirements-testflight.txt').read_text()))
    locked = pins((root / 'Mobile/requirements-host.txt').read_text())
    app = mobile['tool']['briefcase']['app']['logisticsmobile']
    errors = []
    for name, version in host.items():
        if locked.get(name) != version:
            errors.append(f'Mobile host lock differs for {name}; regenerate requirements-host.txt')
    for dependency in app['requires']:
        name, version = dependency.lower().split('==')
        if host.get(name) != version:
            errors.append(f'Mobile host input differs from the native manifest for {name}')
    for backend in ('android', 'iOS'):
        for dependency in app[backend]['requires']:
            if dependency.startswith('toga-') and dependency.split('==')[1] != host['toga-dummy']:
                errors.append(f'Toga backend {backend} differs from the host test version')
    canonical = pins('\n'.join(desktop['project']['dependencies']))
    for name in ('markdown-it-py', 'pygments', 'pypdf'):
        if host[name] != canonical[name]:
            errors.append(f'Desktop/mobile shared dependency differs: {name}')
    ruff = pins('\n'.join(desktop['dependency-groups']['dev']))['ruff']
    for workflow in (root / '.github/workflows').glob('*.yml'):
        for version in re.findall(r'ruff==([^\s]+)', workflow.read_text()):
            if version != ruff:
                errors.append(f'{workflow.name}: Ruff differs from Python/pyproject.toml')
    for error in errors:
        print(error)
    print(f'Toolchain consistency: {len(errors)} violations.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(check())
