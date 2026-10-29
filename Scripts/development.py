"""Standard-library-only check planning, execution and contributor setup."""
import json
from fnmatch import fnmatchcase
import os
from pathlib import Path
import shutil
import subprocess


def shared_test_groups(root, pattern):
    """Keep Qt in the desktop environment and replay native contracts with Toga."""
    directory = root / 'Python/commonUtils/tests'
    groups = [('shared Qt/portable', False, directory, pattern,
               ['--require-module', 'PySide6'])]
    native = directory / 'native'
    if any(path.is_file() and fnmatchcase(path.name, pattern)
           for path in native.rglob('test_native*.py')):
        groups.append(('shared native', True, native, 'test_native*.py',
                       ['--include-pattern', pattern, '--require-module', 'toga',
                        '--require-module', 'toga_dummy']))
    return groups


def run_checks(root, checks, *, dry_run=False, stop_on_failure=False):
    """Validate all interpreters before running; retain failures across matrix legs."""
    import shlex
    if not dry_run:
        for label, interpreter, command, environment in checks:
            if not interpreter.is_file():
                raise ValueError(f'Environment Python is missing: {interpreter}. '
                                 'See docs/development/testing.md for setup, or pass --python / --native-python PATH.')
        if not (root / 'Python/commonUtils/__init__.py').is_file():
            raise ValueError('commonUtils is missing. Run git submodule update --init --recursive '
                             'in a fresh checkout; preserve any existing submodule edits first.')
    result = 0
    for label, interpreter, command, environment in checks:
        print(f'Check: {label}', flush=True)
        print(f'Working directory: {root}', flush=True)
        for name in ('PYTHONPATH', 'QT_QPA_PLATFORM', 'TOGA_BACKEND'):
            if name in environment:
                print(f'{name}={environment[name]}', flush=True)
        print(subprocess.list2cmdline(command) if os.name == 'nt' else shlex.join(command), flush=True)
        if not dry_run:
            code = subprocess.run(command, cwd=root, env=environment).returncode
            if code and not result:
                result = code
            if code and stop_on_failure:
                print('Remaining check groups not run after failure.', flush=True)
                break
    return result


def find_uv():
    return shutil.which('uv') or next((str(path) for path in (
        Path.home() / '.local/bin/uv', Path.home() / '.cargo/bin/uv',
    ) if path.is_file()), None)


def doctor(root, interpreter):
    """Read environment metadata, never credentials or private configuration."""
    checks = [('commonUtils', (root / 'Python/commonUtils/__init__.py').is_file()),
              ('uv', bool(find_uv()))]
    for mobile, packages in ((False, ['PySide6', 'ruff']),
                             (True, ['toga', 'markdown_it', 'pygments', 'pypdf'])):
        name = 'mobile' if mobile else 'desktop'
        python = interpreter(mobile)
        if not python.is_file():
            print(f'MISSING {name}: run python3 dev.py setup {name}')
            checks.append((name, False))
            continue
        code = ('import importlib.util,json,sys; print(json.dumps(dict('
                'python=sys.version.split()[0], missing=[p for p in '
                + repr(packages) + ' if importlib.util.find_spec(p) is None])))')
        try:
            result = subprocess.run([str(python), '-c', code], cwd=root,
                                    capture_output=True, text=True, timeout=30,
                                    env={k: v for k, v in os.environ.items() if k != 'PYTHONPATH'})
            info = json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired, ValueError):
            info = None
        ready = info is not None and not info['missing']
        print(f'{"OK" if ready else "MISSING"} {name}: {info if info else "interpreter check failed"}')
        checks.append((name, ready))
    for name, ready in checks[:2]:
        print(f'{"OK" if ready else "MISSING"} {name}')
    for tool in ('git', 'go', 'java', 'adb', 'xcodebuild'):
        print(f'{"AVAILABLE" if shutil.which(tool) else "OPTIONAL / absent"} native tool: {tool}')
    print('Setup: python3 dev.py setup desktop | python3 dev.py setup mobile')
    print('Missing commonUtils: git submodule update --init --recursive (preserve local edits first).')
    print('Generated environments, mobile_build/build, payload, logs and deployment workspaces stay local.')
    return int(not all(ready for _, ready in checks))


def setup(root, suite, interpreter, *, dry_run=False):
    """Install a declared host environment; never build or deploy an application."""
    import shlex
    uv = find_uv()
    if not uv:
        print('uv is missing. Install it with a desktop launcher, then rerun setup.')
        return 1
    environment = dict(os.environ, UV_PROJECT_ENVIRONMENT=str(root / '.venv'))
    if suite == 'desktop':
        commands = [[uv, 'sync', '--project', str(root / 'Python'), '--locked', '--python', '3.12.2']]
    else:
        python = interpreter(True)
        commands = [] if python.is_file() else [[uv, 'venv', '--python', '3.12.2', str(root / 'mobile_build/.venv')]]
        # Additive installation preserves native build tools in an existing environment.
        commands.append([uv, 'pip', 'install', '--python', str(python), '--require-hashes',
                         '-r', str(root / 'mobile_build/requirements-host.txt')])
    for command in commands:
        print(subprocess.list2cmdline(command) if os.name == 'nt' else shlex.join(command), flush=True)
        if not dry_run:
            result = subprocess.run(command, cwd=root, env=environment)
            if result.returncode:
                return result.returncode
    return 0
