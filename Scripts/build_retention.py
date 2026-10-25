"""Logistics build retention and disposable scratch workspaces.

Run without --apply to preview expired outputs. A .keep file pins an artifact.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from build_manager.retention import lease, prune

ROOT = Path(__file__).resolve().parents[1]


def clean(root=ROOT, *, apply=False, snapshots=True):
    root = Path(root)
    mobile = root / 'mobile_build'
    removed = []
    for provider in ('testflight', 'firebase'):
        removed += prune(mobile / 'build' / provider, eligible=lambda p: p.name.isdigit(), order_key=lambda p: int(p.name), apply=apply)
    if snapshots:
        removed += prune(mobile / '.tools/build-manager/snapshots',
                         eligible=lambda p: bool(re.fullmatch('[0-9a-f]{64}', p.name)) and (p / '.manager-source.json').is_file(),
                         age_days=7, apply=apply, lock_path=lambda p: p.with_suffix('.lock'))
    removed += prune(root / 'test-results/build-scratch',
                     eligible=lambda p: (p / '.manager-scratch').is_file(), keep=1, age_days=1, apply=apply)
    return removed


def clean_builds(mobile):
    """Deployment helpers also run outside the UI and inside source snapshots."""
    try:
        removed = clean(Path(mobile).parent, apply=True, snapshots=False)
        if removed:
            print('Build retention removed ' + str(len(removed)) + ' expired directories.', flush=True)
    except (OSError, RuntimeError) as error:
        print('Build retention incomplete: ' + str(error), flush=True)


@contextmanager
def scratch(root=ROOT):
    parent = Path(root) / 'test-results/build-scratch'
    parent.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    with lease(path):
        (path / '.manager-scratch').touch()
        try:
            yield path
        finally:
            # Retain reports outside this directory before leaving the context.
            if not (path / '.keep').exists():
                shutil.rmtree(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true', help='Delete expired owned outputs')
    parser.add_argument('--scratch', nargs=argparse.REMAINDER,
                        help='Run a command in a disposable cwd; {workspace} arguments expand to its path')
    args = parser.parse_args()
    if args.scratch:
        with scratch(args.root) as path:
            command = [value.replace('{workspace}', str(path)) for value in args.scratch]
            return subprocess.call(command, cwd=path)
    print(json.dumps(dict(apply=args.apply, expired=clean(args.root, apply=args.apply)), indent=2))
    return 0


def storage_groups(root=ROOT):
    """Manual cleanup owns the same provider, snapshot and scratch trees as retention."""
    root = Path(root)
    mobile = root / 'mobile_build'
    return {
        'iOS / TestFlight': dict(root=mobile / 'build/testflight', eligible=lambda p: p.name.isdigit()),
        'Android / Firebase': dict(root=mobile / 'build/firebase', eligible=lambda p: p.name.isdigit()),
        'Source snapshots': dict(root=mobile / '.tools/build-manager/snapshots',
            eligible=lambda p: bool(re.fullmatch('[0-9a-f]{64}', p.name)) and (p / '.manager-source.json').is_file(),
            lock_path=lambda p: p.with_suffix('.lock')),
        'Disposable scratch': dict(root=root / 'test-results/build-scratch', eligible=lambda p: (p / '.manager-scratch').is_file()),
    }


def storage_inventory(root=ROOT):
    from build_manager.retention import owned_entries
    return [dict(row, group=group) for group, spec in storage_groups(root).items()
            for row in owned_entries(**spec)]


def delete_storage(root, selections):
    from build_manager.retention import delete_owned
    groups = storage_groups(root)
    result = dict(removed=[], skipped=[])
    if any(group not in groups for group in selections):
        raise ValueError('Unknown cleanup group')
    for group, names in selections.items():
        outcome = delete_owned(**groups[group], names=names)
        for key in result:
            result[key].extend(outcome[key])
    return result


if __name__ == '__main__':
    raise SystemExit(main())
