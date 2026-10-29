"""Logistics build retention and disposable scratch workspaces.

Run without --apply to preview expired outputs. A .keep file pins an artifact.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from build_manager.locking import workspace_lock
from build_manager.retention import lease, linked, prune, remove_tree

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_MARKER = '.manager-build-output'
GIB = 1024 ** 3
SNAPSHOT_BUDGET = 24 * GIB
DEVICE_BUDGET = 12 * GIB  # Per platform; newest three and active/pinned work win.

RESERVED_OUTPUTS = {'firebase', 'testflight', 'mobile_app', 'logisticsmobile',
                    'physical-device', 'cloud-host', 'go-cache'}


def enroll_output(name, root=ROOT):
    """Explicitly enroll a reviewed, disposable legacy build; never infer ownership."""
    if (not name or name in {'.', '..'} or name.startswith('.')
            or '/' in name or '\\' in name or name in RESERVED_OUTPUTS):
        raise ValueError('Select a named disposable build, not a provider or persistent build root.')
    parent = Path(root).absolute() / 'mobile_build/build'
    path = parent / name
    if any(linked(part) for part in (path, *path.parents)):
        raise ValueError('Build output enrollment refuses linked paths.')
    if not path.is_dir():
        raise ValueError('Build output must already exist under mobile_build/build.')
    with workspace_lock(parent / '.retention.lock'):
        with workspace_lock(parent / ('.' + name + '.retention.lock')):
            marker = path / OUTPUT_MARKER
            if marker.is_symlink():
                raise ValueError('Build output marker must not be a link.')
            # Enrollment starts a fresh review window; it never deletes on its own.
            marker.write_text('Reviewed disposable build output; evidence saved separately.\n')
            os.utime(path, None)
    return path


def device_group(root, platform):
    parent = Path(root) / 'mobile_build/.tools/build-manager/workspaces/devices' / platform

    def eligible(path):
        if not re.fullmatch('[0-9a-f]{32}', path.name):
            return False
        recipe = path / 'recipe.json'
        try:
            if linked(recipe) or recipe.stat().st_size > 262144:
                return False
            data = json.loads(recipe.read_text())
            return (data.get('schema') == 1 and data.get('platform') == platform
                    and Path(data.get('workspace', '')).absolute() == path.absolute())
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    return dict(root=parent, eligible=eligible, lock_path=lambda p: p / 'operation.lock')


def device_access(path):
    # Opening operation.lock must not make an abandoned workspace look newly used.
    files = [p for p in path.glob('*.json') if not linked(p) and p.is_file()]
    return max((p.stat().st_mtime for p in files), default=path.stat().st_mtime)


def clean(root=ROOT, *, apply=False, snapshots=True):
    root = Path(root)
    mobile = root / 'mobile_build'
    removed = []
    for provider in ('testflight', 'firebase'):
        removed += prune(mobile / 'build' / provider, eligible=lambda p: p.name.isdigit(), order_key=lambda p: int(p.name), apply=apply)
    removed += prune(mobile / 'build', eligible=reviewed_output, age_days=7, apply=apply)
    if snapshots:
        removed += prune(mobile / '.tools/build-manager/snapshots',
                         eligible=lambda p: bool(re.fullmatch('[0-9a-f]{64}', p.name)) and (p / '.manager-source.json').is_file(),
                         age_days=7, max_bytes=SNAPSHOT_BUDGET, grace_days=1/24,
                         apply=apply, lock_path=lambda p: p.with_suffix('.lock'))
        for platform in ('ios', 'android'):
            removed += prune(**device_group(root, platform), age_days=1, max_bytes=DEVICE_BUDGET,
                             grace_days=1/24, last_used=device_access, apply=apply)
        if sys.platform == 'darwin':
            from logistics_build.xcode_storage import storage_group, access_order
            try:
                removed += prune(**storage_group(root), age_days=1, max_bytes=12 * GIB,
                                 order_key=access_order, last_used=lambda p: access_order(p)[0], apply=apply)
            except (OSError, subprocess.SubprocessError) as error:
                print('Xcode cache cleanup unavailable: ' + str(error), file=sys.stderr)
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
                remove_tree(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true', help='Delete expired owned outputs')
    parser.add_argument('--enroll-output', action='append', default=[], metavar='NAME',
                        help='Enroll a reviewed disposable build folder; save useful evidence first. Does not prune.')
    parser.add_argument('--scratch', nargs=argparse.REMAINDER,
                        help='Run a command in a disposable cwd; {workspace} arguments expand to its path')
    args = parser.parse_args()
    if args.enroll_output:
        if args.apply or args.scratch:
            parser.error('Enroll outputs separately from pruning or scratch execution.')
        try:
            enrolled = [str(enroll_output(name, args.root)) for name in args.enroll_output]
        except (OSError, ValueError, RuntimeError) as error:
            parser.error(str(error))
        print(json.dumps(dict(enrolled=enrolled), indent=2))
        return 0
    if args.scratch:
        with scratch(args.root) as path:
            command = [value.replace('{workspace}', str(path)) for value in args.scratch]
            return subprocess.call(command, cwd=path)
    print(json.dumps(dict(apply=args.apply, expired=clean(args.root, apply=args.apply)), indent=2))
    return 0


def reviewed_output(path):
    marker = path / OUTPUT_MARKER
    return path.name not in RESERVED_OUTPUTS and not linked(marker) and marker.is_file()


def storage_groups(root=ROOT):
    """Manual cleanup owns the same declared generated trees as retention."""
    root = Path(root)
    mobile = root / 'mobile_build'
    groups = {
        'iOS / TestFlight': dict(root=mobile / 'build/testflight', eligible=lambda p: p.name.isdigit()),
        'Android / Firebase': dict(root=mobile / 'build/firebase', eligible=lambda p: p.name.isdigit()),
        'Reviewed build outputs': dict(root=mobile / 'build', eligible=reviewed_output),
        'Source snapshots': dict(root=mobile / '.tools/build-manager/snapshots',
            eligible=lambda p: bool(re.fullmatch('[0-9a-f]{64}', p.name)) and (p / '.manager-source.json').is_file(),
            lock_path=lambda p: p.with_suffix('.lock')),
        **{'Device workspaces / ' + platform: device_group(root, platform) for platform in ('ios', 'android')},
        'Disposable scratch': dict(root=root / 'test-results/build-scratch', eligible=lambda p: (p / '.manager-scratch').is_file()),
    }

    if sys.platform == 'darwin':
        from logistics_build.xcode_storage import storage_group
        try:
            groups['Xcode project caches'] = storage_group(root)
        except (OSError, subprocess.SubprocessError) as error:
            print('Xcode cache inventory unavailable: ' + str(error), file=sys.stderr)
    return groups


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
