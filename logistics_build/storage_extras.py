"""Explicit adoption of disposable probes and recovery of owned simulator leases."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
from uuid import UUID, uuid4

from build_manager.locking import workspace_lock
from build_manager.profiles import save_json
from build_manager.retention import allocated_bytes, linked, protection_reason

MARKER = '.logistics-owned-scratch.json'


def private(root):
    return Path(root) / 'mobile_build/.tools/build-manager'


def read(path, default=None):
    if not path.exists() and default is not None:
        return default
    if linked(path) or path.stat().st_size > 262144:
        raise ValueError('Invalid owned-storage record.')
    return json.loads(path.read_text())


def registry(root):
    return private(root) / 'storage-extras.json'


def enroll(root, kind, location):
    root = Path(root).absolute()
    if any(linked(p) for p in (private(root), *private(root).parents)):
        raise ValueError('Adoption refuses linked project storage.')
    with workspace_lock(private(root) / 'storage-extras.lock'):
        data = read(registry(root), dict(directories={}, simulators={}))
        if kind == 'legacy':
            from logistics_build.build_retention import enroll_output
            path = Path(location).absolute()
            if path.parent != root / 'mobile_build/build':
                raise ValueError('Choose a legacy direct child of mobile_build/build.')
            return dict(path=str(enroll_output(path.name, root)), retention_days=7)
        if kind == 'directory':
            requested = Path(location).expanduser().absolute()
            if linked(requested):
                raise ValueError('Adoption refuses linked directories.')
            path = requested.resolve()
            allowed = {Path(tempfile.gettempdir()).resolve(), Path('/private/tmp'), root / 'test-results'}
            if path.parent not in allowed or not path.is_dir() or path == root:
                raise ValueError('Choose a disposable direct child of the system temporary folder or project test-results.')
            if any(linked(p) for p in (path, *path.parents)):
                raise ValueError('Adoption refuses linked ancestors.')
            marker = path / MARKER
            if marker.exists():
                existing = read(marker)
                if existing.get('project') != str(root) or existing.get('path') != str(path):
                    raise ValueError('Directory already belongs to another storage owner.')
            token = uuid4().hex
            save_json(marker, dict(schema=1, project=str(root), path=str(path), token=token))
            data['directories'][str(path)] = token
            result = dict(path=str(path), retention_days=7)
        elif kind == 'simulator':
            from build_manager.apple_simulators import AppleSimulators
            UUID(location)
            rows = [d for devices in AppleSimulators().devices()['devices'].values() for d in devices if d['udid'] == location]
            if len(rows) != 1:
                raise ValueError('Choose one existing disposable simulator UUID.')
            data['simulators'][location] = dict(name=rows[0]['name'], enrolled=time.time())
            result = dict(device=location, name=rows[0]['name'], retention_days=1)
        else:
            raise ValueError('Unknown disposable storage kind.')
        save_json(registry(root), data)
        return result


def directory_groups(root):
    root = Path(root).absolute()
    data = read(registry(root), dict(directories={}, simulators={}))
    for name, token in data['directories'].items():
        path = Path(name)
        allowed = {Path(tempfile.gettempdir()).resolve(), Path('/private/tmp'), root / 'test-results'}
        if path.parent not in allowed or not path.is_absolute() or not path.is_dir() or any(linked(p) for p in (path, *path.parents)):
            continue
        def eligible(candidate, path=path, token=token):
            if candidate != path:
                return False
            try:
                record = read(path / MARKER)
                if record != dict(schema=1, project=str(root), path=str(path), token=token):
                    return False
                processes = subprocess.check_output(['/bin/ps', '-Ao', 'command='], text=True, timeout=15)
                # Legacy probes did not take manager locks. Require absence of
                # native writers as well as the new ownership lock.
                return not any(str(path) in line and any(word in line for word in ('xcodebuild', 'briefcase', 'gradle', 'logistics_build'))
                               for line in processes.splitlines())
            except (OSError, ValueError, TypeError, subprocess.SubprocessError):
                return False
        yield ('Adopted temporary builds / ' + path.name, dict(root=path.parent, eligible=eligible))


def simulator_records(root):
    root = Path(root).absolute()
    workspace = private(root) / 'workspaces/ios'
    # Existing leases prove a unique session identity; never infer ownership
    # from a global simulator's display name alone.
    records = {}
    if workspace.is_dir() and not any(linked(p) for p in (workspace, *workspace.parents)):
        for lease in workspace.glob('simulators-*/*-lease.json'):
            if any(linked(p) for p in (lease, lease.parent)):
                continue
            try:
                data = read(lease)
                device, name = data['device'], data['name']
                UUID(device)
                if re.fullmatch(r'Build Manager (iphone|ipad|duo|core) [0-9a-f]{32}', name):
                    records[device] = dict(device=device, name=name, stamp=lease.stat().st_mtime,
                        lease=lease, lock=workspace / 'operation.lock')
            except (OSError, ValueError, KeyError, TypeError):
                continue
    for device, data in read(registry(root), dict(directories={}, simulators={}))['simulators'].items():
        UUID(device)
        records.setdefault(device, dict(device=device, name=data['name'], stamp=data['enrolled'],
            lease=None, lock=private(root) / 'storage-extras.lock'))
    return records


def simulator_inventory(root):
    rows = []
    for device, record in simulator_records(root).items():
        path = Path.home() / 'Library/Developer/CoreSimulator/Devices' / device
        if not path.is_dir() or any(linked(p) for p in (path, *path.parents)):
            continue
        reason = protection_reason(path)
        try:
            with workspace_lock(record['lock']):
                pass
        except RuntimeError:
            reason = 'In use by an active operation'
        try:
            size = allocated_bytes(path)
        except OSError:
            size = None
        rows.append(dict(group='Owned disposable simulators', name=device, label=record['name'],
            path=str(path), protected=reason, allocated_bytes=size))
    return rows


def delete_simulators(root, names, *, expired_only=False):
    from build_manager.apple_simulators import AppleSimulators
    result = dict(removed=[], skipped=[])
    for device in names:
        record = simulator_records(root).get(device)
        if not record:
            result['skipped'].append(device + ': no owned simulator record')
            continue
        try:
            with workspace_lock(record['lock']):
                current = simulator_records(root).get(device)
                if current != record:
                    raise ValueError('Simulator ownership changed; refresh inventory.')
                path = Path.home() / 'Library/Developer/CoreSimulator/Devices' / device
                if any(linked(p) for p in (path, *path.parents)) or protection_reason(path):
                    raise ValueError('Simulator storage is linked or pinned.')
                if expired_only and time.time() - record['stamp'] < 86400:
                    continue
                if path.exists():
                    AppleSimulators().remove(device, record['name'])
                if record['lease']:
                    record['lease'].unlink(missing_ok=True)
                result['removed'].append(str(path))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            result['skipped'].append(device + ': ' + str(error))
    return result


def clean_simulators(root, *, apply=False):
    result = []
    for device, record in simulator_records(root).items():
        if time.time() - record['stamp'] < 86400:
            continue
        path = Path.home() / 'Library/Developer/CoreSimulator/Devices' / device
        if not path.is_dir() or protection_reason(path):
            continue
        try:
            with workspace_lock(record['lock']):
                pass
        except RuntimeError:
            continue
        if apply:
            outcome = delete_simulators(root, [device], expired_only=True)
            result.extend(outcome['removed'])
            if outcome['skipped']:
                print('Owned simulator cleanup incomplete: ' + '; '.join(outcome['skipped']))
        else:
            result.append(str(path))
    return result


def with_storage_owner(plan, root):
    from dataclasses import replace
    return replace(plan, phases=tuple(replace(phase, environment=dict(phase.environment,
        LOGISTICS_STORAGE_OWNER_ROOT=str(root))) for phase in plan.phases))
