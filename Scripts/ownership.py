"""Machine-readable source ownership and focused test selection."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def owners(root=ROOT):
    return json.loads((root / 'Scripts/ownership.json').read_text())['owners']


def _selected_test_files(root, owner):
    groups = owners(root)
    if owner not in groups:
        raise ValueError('Unknown owner. Choose: ' + ', '.join(sorted(groups)))
    selected = set()
    for suite, patterns in groups[owner]['tests'].items():
        folders = {'desktop': 'Python/tests', 'mobile': 'mobile_build/tests'}
        if suite not in folders:
            raise ValueError(f'{owner}: unknown test suite {suite!r}')
        folder = root / folders[suite]
        for pattern in patterns:
            matches = sorted(path for path in folder.rglob(pattern) if path.is_file())
            if not matches:
                raise ValueError(f'{owner}: no {suite} tests match {pattern}')
            for path in matches:
                if path.resolve() != folder.resolve() / path.relative_to(folder):
                    raise ValueError(f'{owner}: linked test source: {path}')
                selected.add((suite, path.relative_to(root).as_posix()))
    return sorted(selected)


def selected_tests(root, owner):
    return sorted({(suite, Path(path).name) for suite, path in _selected_test_files(root, owner)})


def test_owner(root, owner, python, *, dry_run=False, profile='full', mode='diagnostic', fail_fast=False):
    try:
        selected = _selected_test_files(root, owner)
        sys.path.insert(0, str(root / 'Python'))
        from commonUtils.testing.stages import PROFILES, validate
        stages = set(PROFILES[profile])
        included = {row.path for row in validate(root / path for _, path in selected)
                    if stages.intersection({level for _, level, _ in row.cases} or {row.default})}
        selected = [(suite, path) for suite, path in selected if root / path in included]
        if not selected:
            raise ValueError(f'{owner}: no test sources selected for profile {profile!r}')
    except ValueError as error:
        print(error)
        return 2
    groups = {}
    for suite, path in selected:
        groups.setdefault(suite, []).append(path)
    failed = False
    for suite, paths in groups.items():
        command = [str(python), str(root / 'dev.py'), 'test', suite,
                   '--profile', profile, '--mode', mode]
        for path in paths:
            command.extend(['--exact-file', path])
        if fail_fast:
            command.append('--fail-fast')
        if dry_run:
            for path in paths:
                print(f'{suite}: {path}')
        else:
            code = subprocess.run(command, cwd=root).returncode
            failed |= code != 0
            if code and (fail_fast or mode == 'fast'):
                print('Remaining owner selections not run after failure.')
                break
    return int(failed)
