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
from build_manager.retention import lease, linked, prune, prune_cache_groups, remove_tree, explicitly_pinned, has_retention_protection, nested_workflow_hold_reason

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


def owned_snapshot(path):
    marker = path / '.manager-source.json'
    return bool(re.fullmatch('[0-9a-f]{64}', path.name)) and not linked(marker) and marker.is_file()


def owned_scratch(path):
    marker = path / '.manager-scratch'
    return not linked(marker) and marker.is_file()


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

    return dict(root=parent, eligible=eligible, lock_path=lambda p: p / 'operation.lock', ownership_files=('recipe.json',))


def device_access(path):
    # Opening operation.lock must not make an abandoned workspace look newly used.
    files = [p for p in path.glob('*.json') if not linked(p) and p.is_file()]
    return max((p.stat().st_mtime for p in files), default=path.stat().st_mtime)


def cache_idle(path):
    """Non-manager native writers do not necessarily take our operation locks."""
    try:
        processes = subprocess.check_output(['/bin/ps', '-Ao', 'command='], text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    for line in processes.splitlines():
        if re.search(r'/Xcode[^/]*\.app/Contents/MacOS/Xcode(?:\s|$)', line):
            return False
        if str(path) in line and any(word in line for word in ('xcodebuild', 'briefcase', 'gradle', 'logistics_build')):
            return False
    return True


def device_intermediates(root):
    """Keep reviewed packages/receipts while retiring their reproducible build tree."""
    for platform in ('ios', 'android'):
        spec = device_group(root, platform)
        parent = spec['root']
        if not parent.is_dir() or any(linked(p) for p in (parent, *parent.parents)):
            continue
        for workspace in sorted(parent.iterdir()):
            if linked(workspace) or not workspace.is_dir() or not spec['eligible'](workspace):
                continue
            def eligible(path, workspace=workspace, platform=platform, owner=spec['eligible']):
                if path.name != 'build' or not owner(workspace) or explicitly_pinned(workspace) or not cache_idle(workspace):
                    return False
                prepared = workspace / 'prepared.json'
                try:
                    if linked(prepared) or prepared.stat().st_size > 262144:
                        return False
                    data = json.loads(prepared.read_text())
                    package = workspace / ('app.zip' if platform == 'ios' else 'app.apk')
                    return (data.get('workspace') == str(workspace) and data.get('platform') == platform
                            and data.get('package') == str(package) and package.is_file() and not linked(package)
                            and re.fullmatch('[0-9a-f]{64}', data.get('package_sha256', '')) is not None)
                except (OSError, ValueError, TypeError, AttributeError):
                    return False
            yield ('Device build caches / ' + platform + ' / ' + workspace.name,
                   dict(root=workspace, eligible=eligible, lock_path=lambda p: p.parent / 'operation.lock'))


def cache_access(path):
    return (path.parent / 'prepared.json').stat().st_mtime


def snapshot_intermediates(root):
    parent = Path(root) / 'mobile_build/.tools/build-manager/snapshots'
    if not parent.is_dir() or any(linked(p) for p in (parent, *parent.parents)):
        return
    for snapshot in sorted(parent.iterdir()):
        marker = snapshot / '.manager-source.json'
        if (linked(snapshot) or not snapshot.is_dir() or not re.fullmatch('[0-9a-f]{64}', snapshot.name)
                or linked(marker) or not marker.is_file()):
            continue
        build = snapshot / 'mobile_build/build'
        specs = [
            (build / 'logisticsmobile/android/gradle/app/build', {'intermediates', 'tmp', 'generated'}),
            (build / 'logisticsmobile/android/gradle', {'.gradle'}),
            (build / 'logisticsmobile/ios/xcode/build', {'Logistics Mobile.build', 'XCBuildData',
                'EagerLinkingTBDs', 'ExplicitPrecompiledModules', 'SharedPrecompiledHeaders', 'SwiftExplicitPrecompiledModules'}),
        ]
        provider = build / 'testflight'
        if provider.is_dir() and not linked(provider):
            specs.extend((path, {'derived'}) for path in provider.iterdir() if path.name.isdigit() and path.is_dir() and not linked(path))
        for cache_root, names in specs:
            def eligible(path, names=names, snapshot=snapshot):
                return path.name in names and not explicitly_pinned(snapshot) and cache_idle(snapshot)
            yield ('Snapshot build caches / ' + snapshot.name[:12] + ' / ' + cache_root.relative_to(snapshot).as_posix(),
                   dict(root=cache_root, eligible=eligible, lock_path=lambda p, snapshot=snapshot: snapshot.with_suffix('.lock')))


def clean(root=ROOT, *, apply=False, snapshots=True, warnings=None):
    root = Path(root)
    mobile = root / 'mobile_build'
    removed = []
    for provider in ('testflight', 'firebase'):
        removed += prune(mobile / 'build' / provider, eligible=lambda p: p.name.isdigit(), order_key=lambda p: int(p.name), apply=apply)
    removed += prune(mobile / 'build', eligible=reviewed_output, ownership_files=(OUTPUT_MARKER,), age_days=5, apply=apply)
    if snapshots:
        removed += prune(mobile / '.tools/build-manager/snapshots',
                         eligible=owned_snapshot, ownership_files=('.manager-source.json',),
                         age_days=5, max_bytes=SNAPSHOT_BUDGET, grace_days=1/24,
                         apply=apply, lock_path=lambda p: p.with_suffix('.lock'))
        for platform in ('ios', 'android'):
            removed += prune(**device_group(root, platform), age_days=1, max_bytes=DEVICE_BUDGET,
                             grace_days=1/24, last_used=device_access, apply=apply)
        caches = [dict(spec, last_used=cache_access) for _, spec in device_intermediates(root)]
        caches += [spec for _, spec in snapshot_intermediates(root)]
        removed += prune_cache_groups(caches, age_days=1, max_bytes=12 * GIB, grace_days=1/24, apply=apply)
        if sys.platform == 'darwin':
            from logistics_build.xcode_storage import storage_group, access_order
            try:
                removed += prune(**storage_group(root), age_days=1, max_bytes=12 * GIB,
                                 order_key=access_order, last_used=lambda p: access_order(p)[0], apply=apply)
            except (OSError, subprocess.SubprocessError) as error:
                message = 'Xcode cache cleanup unavailable: ' + str(error)
                print(message, file=sys.stderr)
                if warnings is not None:
                    warnings.append(message)
        from logistics_build.storage_extras import directory_groups, MARKER, clean_simulators
        for _, spec in directory_groups(root):
            removed += prune(**spec, keep=0, age_days=5,
                             last_used=lambda p: (p / MARKER).stat().st_mtime, apply=apply)
        if sys.platform == 'darwin':
            removed += clean_simulators(root, apply=apply, warnings=warnings)
    removed += prune(root / 'test-results/build-scratch',
                     eligible=owned_scratch, ownership_files=('.manager-scratch',), protection=nested_workflow_hold_reason, keep=1, age_days=1, apply=apply)
    return removed


def storage_maintenance(root=ROOT):
    warnings = []
    removed = clean(root, apply=True, warnings=warnings)
    return dict(status='incomplete' if warnings else 'passed', removed=removed, warnings=warnings)


def clean_builds(mobile):
    """Deployment helpers also run outside the UI and inside source snapshots."""
    try:
        owner = Path(os.environ.get('LOGISTICS_STORAGE_OWNER_ROOT', Path(mobile).parent))
        removed = clean(owner, apply=True, snapshots='LOGISTICS_STORAGE_OWNER_ROOT' in os.environ)
        if removed:
            print('Build retention removed ' + str(len(removed)) + ' expired directories.', flush=True)
    except (OSError, RuntimeError) as error:
        print('Build retention incomplete: ' + str(error), flush=True)


@contextmanager
def scratch(root=ROOT):
    parent = Path(root).resolve() / 'test-results/build-scratch'
    parent.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    with lease(path):
        (path / '.manager-scratch').touch()
        try:
            yield path
        finally:
            # Retain reports outside this directory before leaving the context.
            if not has_retention_protection(path) and not nested_workflow_hold_reason(path):
                remove_tree(path, ownership_files=('.manager-scratch',))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true', help='Delete expired owned outputs')
    parser.add_argument('--enroll-directory', type=Path, help='Adopt a reviewed disposable temporary build directory (five days)')
    parser.add_argument('--enroll-simulator', help='Adopt an explicitly disposable simulator UUID (one day)')
    parser.add_argument('--enroll-output', action='append', default=[], metavar='NAME',
                        help='Enroll a reviewed disposable build folder; save useful evidence first. Does not prune.')
    parser.add_argument('--scratch', nargs=argparse.REMAINDER,
                        help='Run a command with disposable cwd and commonUtils storage; {workspace} arguments expand to its path')
    args = parser.parse_args()
    if args.enroll_directory or args.enroll_simulator:
        if args.apply or args.enroll_output or args.scratch or args.enroll_directory and args.enroll_simulator:
            parser.error('Adopt one disposable location separately from other operations.')
        from logistics_build.storage_extras import enroll
        print(json.dumps(enroll(args.root, 'directory' if args.enroll_directory else 'simulator',
                                str(args.enroll_directory or args.enroll_simulator)), indent=2))
        return 0
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
            # Native probes can open document hosts that automatically record
            # recent files. A disposable cwd alone still writes to the user's
            # real cache; override inherited storage before the child imports UI.
            environment = dict(os.environ, COMMONUTILS_STORAGE_ROOT=str(path / 'commonutils'))
            return subprocess.call(command, cwd=path, env=environment)
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
        'Reviewed build outputs': dict(root=mobile / 'build', eligible=reviewed_output, ownership_files=(OUTPUT_MARKER,)),
        'Source snapshots': dict(root=mobile / '.tools/build-manager/snapshots',
            eligible=owned_snapshot, ownership_files=('.manager-source.json',),
            lock_path=lambda p: p.with_suffix('.lock')),
        **{'Device workspaces / ' + platform: device_group(root, platform) for platform in ('ios', 'android')},
        'Disposable scratch': dict(root=root / 'test-results/build-scratch', eligible=owned_scratch, ownership_files=('.manager-scratch',),
            protection=nested_workflow_hold_reason),
    }
    groups.update(device_intermediates(root))
    groups.update(snapshot_intermediates(root))
    from logistics_build.storage_extras import directory_groups
    groups.update(directory_groups(root))

    if sys.platform == 'darwin':
        from logistics_build.xcode_storage import storage_group
        try:
            groups['Xcode project caches'] = storage_group(root)
        except (OSError, subprocess.SubprocessError) as error:
            print('Xcode cache inventory unavailable: ' + str(error), file=sys.stderr)
    return groups


def storage_inventory(root=ROOT):
    from build_manager.retention import owned_entries
    rows = [dict(row, group=group) for group, spec in storage_groups(root).items()
            for row in owned_entries(**spec)]
    for row in rows:
        if row['group'].startswith(('Device build caches / ', 'Snapshot build caches / ')):
            platform = 'Android' if '/android/' in row['path'] or '/devices/android/' in row['path'] else 'iOS'
            row['category'] = 'Rebuildable caches / ' + platform
            parts = row['group'].split(' / ')
            owner = parts[-1] if parts[0] == 'Device build caches' else parts[1]
            row['label'] = owner[:12] + ' / ' + row['name']
    if sys.platform == 'darwin':
        from logistics_build.storage_extras import simulator_inventory
        rows += simulator_inventory(root)
    return rows


def delete_storage(root, selections):
    from build_manager.retention import delete_owned
    groups = storage_groups(root)
    result = dict(removed=[], skipped=[])
    if any(group not in groups and group != 'Owned disposable simulators' for group in selections):
        raise ValueError('Unknown cleanup group')
    for group, names in selections.items():
        if group == 'Owned disposable simulators':
            if sys.platform != 'darwin':
                raise ValueError('Simulator cleanup requires macOS.')
            from logistics_build.storage_extras import delete_simulators
            outcome = delete_simulators(root, names)
        else:
            outcome = delete_owned(**groups[group], names=names)
        for key in result:
            result[key].extend(outcome[key])
    return result


if __name__ == '__main__':
    raise SystemExit(main())
