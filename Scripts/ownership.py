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
        folder = root / ('Python/tests' if suite == 'desktop' else 'Mobile/tests')
        for pattern in patterns:
            matches = sorted(folder.rglob(pattern))
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
