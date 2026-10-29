"""Select the pinned Apple SDK series for repeatable Duo release validation."""
import argparse
import json
import os
import platform
from pathlib import Path
import re
import subprocess


def version(value):
    if not re.fullmatch(r'\d+(?:\.\d+){1,2}', value):
        raise ValueError('Expected a numeric SDK version.')
    return tuple(int(part) for part in value.split('.')) + (0,) * (3 - len(value.split('.')))


def choose(candidates, minimum='27.1'):
    requested = version(minimum)
    # Pin the required SDK minor instead of silently opting release validation
    # into a newer beta installed on the runner image.
    supported = [(version(sdk), path, sdk) for path, sdk in candidates
                 if version(sdk)[:2] == requested[:2] and version(sdk) >= requested]
    if not supported:
        raise RuntimeError(f'Install Xcode with iOS Simulator SDK {requested[0]}.{requested[1]}.x; release validation requires that SDK series.')
    _, path, sdk = max(supported)
    return path, sdk


def installed():
    paths = {str(path / 'Contents/Developer') for path in Path('/Applications').glob('Xcode*.app')}
    if os.environ.get('DEVELOPER_DIR'):
        paths.add(os.environ['DEVELOPER_DIR'])
    candidates = []
    for path in sorted(paths):
        result = subprocess.run(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'],
            env=dict(os.environ, DEVELOPER_DIR=path), capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            candidates.append((path, result.stdout.strip()))
    return candidates


def simulator_data(kind, env):
    return json.loads(subprocess.check_output(
        ['xcrun', 'simctl', 'list', kind, '--json'], env=env, text=True))


def prepare_duo(path, sdk, required_runtime='27.1'):
    """Provision the required runtime/device; never substitute an ordinary phone."""
    if version(sdk) < version('27.1'):
        raise RuntimeError('Duo requires an iOS Simulator SDK >= 27.1.')
    env = dict(os.environ, DEVELOPER_DIR=path)
    data = simulator_data('devices', env)
    def is_duo(device):
        identity = device.get('deviceTypeIdentifier') or device.get('name', '')
        return 'iPhone-Duo' in identity or 'iPhone Duo' in identity
    required_id = 'com.apple.CoreSimulator.SimRuntime.iOS-' + required_runtime.replace('.', '-')
    devices = [device for runtime, items in data['devices'].items() if runtime == required_id
               for device in items if device.get('isAvailable')
               and is_duo(device)]
    if devices:
        return sorted(devices, key=lambda device: device['state'] != 'Booted')[0]['udid']

    def compatible():
        return [runtime for runtime in simulator_data('runtimes', env)['runtimes']
                if runtime.get('isAvailable') and '.iOS-' in runtime['identifier']
                and version(runtime['version']) == version(required_runtime)
                and any('iPhone-Duo' in device['identifier']
                        for device in runtime.get('supportedDeviceTypes', ()))]
    runtimes = compatible()
    if not runtimes:
        # Duo has a dedicated 27.1 runtime; a newer generic runtime can omit it.
        subprocess.run(['xcodebuild', '-downloadPlatform', 'iOS', '-buildVersion', required_runtime,
                        '-architectureVariant', 'arm64' if platform.machine() == 'arm64' else 'universal'],
                       env=env, check=True, timeout=1800)
        runtimes = compatible()
    if not runtimes:
        raise RuntimeError('No Duo-compatible iOS Simulator runtime after provisioning.')
    runtime = max(runtimes, key=lambda row: version(row['version']))
    types = [row for row in simulator_data('devicetypes', env)['devicetypes']
             if 'iPhone-Duo' in row['identifier'] or 'iPhone Duo' in row['name']]
    if not types:
        raise RuntimeError('The selected Xcode has no iPhone Duo simulator device type.')
    device = subprocess.check_output(['xcrun', 'simctl', 'create', 'Logistics Validation Duo',
        types[0]['identifier'], runtime['identifier']], env=env, text=True).strip()
    if not device:
        raise RuntimeError('Creating the required Duo simulator returned no device identifier.')
    return device


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minimum-sdk', default=None,
                        help='Pin this SDK major/minor series and require at least this patch version.')
    parser.add_argument('--github-env', type=Path)
    parser.add_argument('--path-only', action='store_true')
    parser.add_argument('--prepare-duo', action='store_true')
    args = parser.parse_args()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from logistics_build.test_environments import load
    environments = load()
    path, sdk = choose(installed(), args.minimum_sdk or environments['ios_sdk'])
    if args.github_env:
        with args.github_env.open('a') as stream:
            stream.write('DEVELOPER_DIR=' + path + '\n')
    result = dict(developer_dir=path, simulator_sdk=sdk)
    if args.prepare_duo:
        result['duo_device'] = prepare_duo(path, sdk, environments['duo_runtime'])
    print(path if args.path_only else json.dumps(result))
