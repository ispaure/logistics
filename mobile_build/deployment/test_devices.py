"""Discover and update available local test devices without terminal questions."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from . import android_deploy as android, device_tools as ios
from .deployment_paths import WORKSPACE_ENV

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / '.tools/test-devices.json'
WORKSPACES = ROOT / '.deploy-workspaces'


def android_devices():
    env, adb = android.tools_environment(android.deployment_environment())
    android.discover_wireless(adb, env)
    devices = {}
    for line in android.run([str(adb), 'devices'], env).splitlines():
        fields = line.rsplit(None, 1)
        if len(fields) != 2 or fields[1] != 'device':
            continue
        serial = fields[0]
        try:
            def prop(name):
                return android.run([str(adb), '-s', serial, 'shell', 'getprop', name], env).strip()
            hardware = prop('ro.serialno')
            # Emulators may share generic hardware properties; retain their ADB IDs.
            key = hardware if hardware and hardware != 'unknown' and not serial.startswith('emulator-') else serial
            item = dict(platform='Android', id=key, connection=serial,
                        name=prop('ro.product.model') or serial, online=True)
            # Prefer USB over a wireless endpoint for the same physical device.
            if key not in devices or (':' not in serial and not serial.startswith('adb-')):
                devices[key] = item
        except (OSError, subprocess.SubprocessError) as error:
            print('Cannot inspect Android device ' + serial + ': ' + str(error), file=sys.stderr)
    return list(devices.values())


def ios_devices():
    if not ios.CONFIG.exists():
        return []
    config = ios.saved_config()
    targets = list(dict.fromkeys(config.get('device_ids', [config['device_id']])))
    developer, _ = ios.choose(ios.installed())
    with tempfile.TemporaryDirectory(prefix='logistics-device-list-') as directory:
        path = Path(directory) / 'devices.json'
        subprocess.run(['xcrun', 'devicectl', 'list', 'devices', '--timeout', '30',
                        '--json-output', str(path)], env=dict(os.environ, DEVELOPER_DIR=developer),
                       capture_output=True, text=True, check=True, timeout=40)
        discovered = json.loads(path.read_text())['result']['devices']
    result = []
    for target in targets:
        try:
            device, _, _ = ios.select_device(discovered, target)
            name = device.get('deviceProperties', {}).get('name') or target
            result.append(dict(platform='iOS', id=target, name=name, online=True))
        except RuntimeError:
            result.append(dict(platform='iOS', id=target, name=target, online=False))
    return result


def inventory():
    previous = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else []
    known = {(d['platform'], d['id']): dict(d, online=False) for d in previous}
    errors = []
    for label, discover in [('Android', android_devices), ('iOS', ios_devices)]:
        try:
            for device in discover():
                known[device['platform'], device['id']] = device
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(label + ': ' + str(error))
    # iOS membership is owned by .device.json, not this Android discovery cache.
    config = ios.saved_config() if ios.CONFIG.exists() else {}
    ios_ids = config.get('device_ids', [config.get('device_id')])
    devices = [d for d in known.values() if d['platform'] != 'iOS' or d['id'] in ios_ids]
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(devices, indent=2) + '\n')
    return devices, errors


def deploy_platform(available):
    """Run inside one platform worker; devices on that platform stay sequential."""
    failed = []
    android_targets = [d for d in available if d['platform'] == 'Android']
    if android_targets:
        try:
            android.deploy(build_only=True, devices=[d['connection'] for d in android_targets])
            env, adb = android.tools_environment(android.deployment_environment())
            apk = android.PROJECT / 'app/build/outputs/apk/debug/app-debug.apk'
            for device in android_targets:
                try:
                    print('Updating ' + device['name'], flush=True)
                    android.install_apk(adb, env, device['connection'], apk)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    failed.append(device['name'])
                    print(str(error), file=sys.stderr, flush=True)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            failed.append('Android build')
            print(str(error), file=sys.stderr, flush=True)
    for device in available:
        if device['platform'] == 'iOS':
            try:
                subprocess.run([sys.executable, '-m', 'mobile_build.deployment.device_tools', 'deploy',
                                '--device', device['id'], '--allow-wired'], cwd=ROOT.parent, check=True)
            except (OSError, subprocess.SubprocessError) as error:
                failed.append(device['name'])
                print(str(error), file=sys.stderr, flush=True)
    if failed:
        raise RuntimeError('Failed: ' + ', '.join(failed))
    print('Updated ' + str(len(available)) + ' test device(s).', flush=True)


def run_platform(platform, devices):
    """Use a separate process so workspace settings never cross platform threads."""
    workspace = WORKSPACES / platform.lower()
    workspace.mkdir(parents=True, exist_ok=True)
    targets = workspace / 'targets.json'
    targets.write_text(json.dumps(devices, indent=2) + '\n')
    logs = workspace / 'logs'
    logs.mkdir(exist_ok=True)
    log = logs / 'deployment.log'
    print('Starting ' + platform + '; log: ' + str(log), flush=True)
    env = dict(os.environ, **{WORKSPACE_ENV: str(workspace)}, PYTHONUNBUFFERED='1')
    command = [sys.executable, '-m', 'mobile_build.deployment.test_devices', '--worker-platform', platform,
               '--targets-file', str(targets)]
    with log.open('w') as stream, subprocess.Popen(
            command, cwd=ROOT.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors='replace') as process:
        for line in process.stdout:
            stream.write(line)
            stream.flush()
            print('[' + platform + '] ' + line.rstrip('\n'), flush=True)
        if process.wait():
            raise RuntimeError(platform + ' deployment failed. See ' + str(log))


def deploy_devices(devices, *, target=None):
    if target is not None:
        devices = [d for d in devices if (d['platform'], d['id']) == target]
        if not devices or not devices[0]['online']:
            raise ValueError('Selected device is unavailable. Connect or wake it, then Refresh. No other devices were updated.')
    available = [d for d in devices if d['online']]
    if not available:
        raise ValueError('No test devices available. Connect and authorize the S8+ over USB, or wake a paired device, then Refresh.')
    WORKSPACES.mkdir(parents=True, exist_ok=True)
    # Fixed platform workspaces retain build caches. Hold the lock until every
    # worker exits so another CLI/GUI batch cannot modify their active files.
    with (WORKSPACES / 'deploy.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A test-device deployment is already running. Wait for it to finish.') from None
        failed = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            for platform in ('Android', 'iOS'):
                selected = [d for d in available if d['platform'] == platform]
                if selected:
                    futures[executor.submit(run_platform, platform, selected)] = platform
            for future in as_completed(futures):
                platform = futures[future]
                try:
                    future.result()
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    failed.append(platform)
                    print(str(error), file=sys.stderr, flush=True)
        if failed:
            raise RuntimeError('Deployment failed for: ' + ', '.join(sorted(failed)))
    print('Updated all ' + str(len(available)) + ' available test devices.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--platform', choices=('Android', 'iOS'))
    parser.add_argument('--repair-android', action='store_true',
                        help='Restart local ADB, then refresh paired Android connections')
    parser.add_argument('--device', help='Stable device ID from the device list')
    parser.add_argument('--worker-platform', choices=('Android', 'iOS'), help=argparse.SUPPRESS)
    parser.add_argument('--targets-file', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repair_android and (not args.list or args.worker_platform or args.targets_file):
        parser.error('--repair-android requires --list and cannot run during a deployment worker.')
    if args.worker_platform or args.targets_file:
        if not args.worker_platform or not args.targets_file or args.list or args.platform or args.device:
            parser.error('Invalid platform worker arguments.')
        targets = json.loads(args.targets_file.read_text())
        if not targets or any(d['platform'] != args.worker_platform or not d['online'] for d in targets):
            parser.error('Worker targets must be available devices on one platform.')
        deploy_platform(targets)
        return
    if bool(args.platform) != bool(args.device) or (args.list and args.device):
        parser.error('Use --platform and --device together, without --list.')
    if args.repair_android:
        from .wireless_adb import restart
        WORKSPACES.mkdir(parents=True, exist_ok=True)
        with (WORKSPACES / 'deploy.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('A test-device deployment is running. Wait before repairing Android.') from None
            env, adb = android.tools_environment(android.deployment_environment())
            restart(adb, env, android.run)
    devices, errors = inventory()
    if args.list:
        print(json.dumps(dict(devices=devices, errors=errors)))
        return
    target = (args.platform, args.device) if args.device else None
    if target:
        errors = [error for error in errors if error.startswith(args.platform + ':')]
    for error in errors:
        print(error, file=sys.stderr)
    for device in devices:
        if target and (device['platform'], device['id']) != target:
            continue
        print(device['platform'] + ' · ' + device['name'] + (' — ready' if device['online'] else ' — offline; skipped'), flush=True)
    deploy_devices(devices, target=target)
    if errors:
        raise RuntimeError('Available devices updated, but discovery was incomplete: ' + '; '.join(errors))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
