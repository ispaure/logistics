"""Machine-readable source ownership and focused test selection."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def owners(root=ROOT):
    return json.loads((root / 'Scripts/ownership.json').read_text())['owners']


def selected_tests(root, owner):
    groups = owners(root)
    if owner not in groups:
        raise ValueError('Unknown owner. Choose: ' + ', '.join(sorted(groups)))
    selected = []
    for suite, patterns in groups[owner]['tests'].items():
        folders = {'desktop': 'Python/tests', 'mobile': 'mobile_build/tests'}
        if suite not in folders:
            raise ValueError(f'{owner}: unknown test suite {suite!r}')
        folder = root / folders[suite]
        for pattern in patterns:
            matches = sorted(path for path in folder.rglob(pattern) if path.is_file())
            if not matches:
                raise ValueError(f'{owner}: no {suite} tests match {pattern}')
            selected.extend((suite, path.name) for path in matches)
    return sorted(set(selected))


def test_owner(root, owner, python, *, dry_run=False):
    try:
        selected = selected_tests(root, owner)
    except ValueError as error:
        print(error)
        return 2
    failed = False
    for suite, pattern in selected:
        command = [str(python), str(root / 'dev.py'), 'test', suite, pattern]
        if dry_run:
            print(f'{suite}: {pattern}')
        else:
            failed |= subprocess.run(command, cwd=root).returncode != 0
    return int(failed)
