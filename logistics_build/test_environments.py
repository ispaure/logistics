"""Shared project test environments, edited in Settings and read by CI."""
import argparse
import json
import platform
import sys
from pathlib import Path, PureWindowsPath
import re

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    'macos_runner': 'macos-26', 'windows_runner': 'windows-2025',
    'linux_runner': 'ubuntu-24.04-arm', 'ios_runner': 'xcode-27',
    'android_runner': 'ubuntu-24.04', 'python_version': '3.12.2',
    'macos_major': '26', 'macos_local_major': '', 'windows_major': '11',
    'fedora_image': 'fedora:44', 'ios_sdk': '27.1',
    'iphone_runtime': '27.0', 'duo_runtime': '27.1', 'ipad_runtime': '27.0',
    'android_api': '36', 'android_model': 'pixel_9',
    'android_local_abi': 'arm64-v8a', 'android_github_abi': 'x86_64',
}
WINDOWS_SERVER_RUNNERS = {'windows-2022': 20348, 'windows-2025': 26100, 'windows-2025-vs2026': 26100}
DESCRIPTIONS = {
    **{key: 'Explicit GitHub runner label. OS patches still follow that runner image; never use a floating latest label.'
       for key in DEFAULTS if key.endswith('_runner')},
    'windows_runner': 'Explicit native x64 Windows runner for GitHub. windows-2025 uses Windows Server 2025. '
                      'The dedicated local Windows client and its Python architecture are configured separately.',
    'macos_major': 'Required macOS major version for GitHub desktop tests and the fallback for local desktop tests.',
    'macos_local_major': 'Required macOS major version for local desktop tests. Leave blank to use the GitHub requirement.',
    'windows_major': 'Required version for the local Windows client and any custom hosted Windows client runner.',
    'python_version': 'Desktop/build Python version shared with GitHub. Existing local interpreters must match; saving does not install tools.',
    'fedora_image': 'Single Linux desktop test distribution, also required for the local dedicated guest. Ubuntu is only the container host.',
    'ios_sdk': 'Required iOS Simulator SDK major.minor series for local and GitHub native tests.',
    **{key: 'Exact simulator runtime version for this family, shared by local and GitHub native tests.'
       for key in ('iphone_runtime', 'duo_runtime', 'ipad_runtime')},
    'android_api': 'Android API level shared by local and GitHub native emulator images.',
    'android_model': 'Android emulator hardware profile shared by local and GitHub.',
    'android_local_abi': 'Local emulator ABI. Apple Silicon requires arm64-v8a for accelerated tests.',
    'android_github_abi': 'Hosted emulator ABI. Linux x64/KVM requires x86_64; this difference is explicit and prevents claiming identical environments.',
}

LABELS = {
    'macos_runner': 'macOS GitHub runner', 'windows_runner': 'Windows x64 GitHub runner',
    'linux_runner': 'Fedora container host runner', 'ios_runner': 'iOS GitHub runner',
    'android_runner': 'Android GitHub runner', 'python_version': 'Desktop / build Python version',
    'macos_major': 'Hosted macOS major version', 'macos_local_major': 'Local macOS major version',
    'windows_major': 'Windows client version',
    'fedora_image': 'Fedora version / container image', 'ios_sdk': 'iOS Simulator SDK series',
    'iphone_runtime': 'iPhone simulator runtime', 'duo_runtime': 'Duo simulator runtime',
    'ipad_runtime': 'iPad simulator runtime', 'android_api': 'Android API level',
    'android_model': 'Android native device profile', 'android_local_abi': 'Local Android emulator ABI',
    'android_github_abi': 'GitHub Android emulator ABI',
}


def validate(values):
    values = {'macos_local_major': '', **values}
    if set(values) != set(DEFAULTS):
        raise ValueError('Test environment fields differ from the supported schema.')
    for key, value in values.items():
        if key == 'macos_local_major' and value == '':
            continue
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]+', value):
            raise ValueError('Invalid test environment value: ' + key)
        if key.endswith('_runner') and 'latest' in value:
            raise ValueError('Choose an explicit runner version: ' + key)
    for key in ('ios_sdk', 'iphone_runtime', 'duo_runtime', 'ipad_runtime'):
        if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', values[key]):
            raise ValueError('Expected a numeric version: ' + key)
    if tuple(map(int, values['ios_sdk'].split('.')[:2])) < (27, 1) or tuple(map(int, values['duo_runtime'].split('.')[:2])) < (27, 1):
        raise ValueError('Required Duo coverage needs iOS SDK and runtime >= 27.1.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', values['python_version']):
        raise ValueError('Choose an exact Python patch version.')
    if not re.fullmatch(r'fedora:\d+', values['fedora_image']):
        raise ValueError('Choose a numbered Fedora image; Linux is tested once.')
    if not values['android_api'].isdigit() or int(values['android_api']) < 24:
        raise ValueError('Android API must be an integer >= 24.')
    for key in ('macos_major', 'macos_local_major', 'windows_major'):
        if values[key] and not values[key].isdigit():
            raise ValueError('OS major version must be numeric.')
    for key in ('android_local_abi', 'android_github_abi'):
        if values[key] not in ('arm64-v8a', 'x86_64'):
            raise ValueError('Unsupported Android emulator ABI.')
    return values


def load(root=ROOT):
    path = Path(root) / 'test-environments.json'
    data = json.loads(path.read_text()) if path.is_file() else dict(schema=1, **DEFAULTS)
    if data.pop('schema', None) != 1:
        raise ValueError('Unsupported test environment schema.')
    return validate(dict(DEFAULTS, **data))


def save(root, changes):
    values = validate(dict(load(root), **changes))
    if not values['macos_local_major']:
        del values['macos_local_major']
    path = Path(root) / 'test-environments.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(schema=1, **values), indent=2) + '\n')
    temporary.replace(path)


def android_image(values, *, hosted=False):
    return 'system-images;android-' + values['android_api'] + ';google_apis;' + values['android_github_abi' if hosted else 'android_local_abi']


def runtime_id(values, family):
    return 'com.apple.CoreSimulator.SimRuntime.iOS-' + values[family + '_runtime'].replace('.', '-')


def outputs(values, target='all'):
    platforms = [target] if target in ('macos', 'windows') else ['macos', 'windows']
    hosted_values = {key: value for key, value in values.items() if key != 'macos_local_major'}
    return dict(hosted_values, desktop_matrix=json.dumps({'include': [dict(target=p, runner=values[p + '_runner']) for p in platforms]}),
                android_device=json.dumps(dict(avd='LogisticsValidation', device_type=values['android_model'],
                    skin=None, system_image=android_image(values, hosted=True))))


def windows_webengine(path, sha256):
    """Validate the local guest artifact reference without accessing the VM."""
    if path == sha256 == '':
        return None
    if not isinstance(path, str) or not isinstance(sha256, str):
        raise ValueError('Set the Windows VM WebEngine wheel path and SHA-256 as text.')
    wheel = PureWindowsPath(path)
    if (not wheel.is_absolute() or not re.fullmatch(r'[A-Za-z]:', wheel.drive)
            or '..' in wheel.parts
            or not re.fullmatch(r'pyside6_webengine-[0-9.]+-(?:[0-9]+-)?cp310-abi3-win_arm64\.whl', wheel.name)):
        raise ValueError('Set an absolute guest path to a PySide6 WebEngine Windows ARM64 wheel.')
    if not re.fullmatch(r'[0-9a-f]{64}', sha256):
        raise ValueError('Set the 64-character lowercase SHA-256 of the Windows VM WebEngine wheel.')
    return dict(path=str(wheel), sha256=sha256)


def windows_python(values, architecture='x86_64', version=''):
    if architecture not in ('x86_64', 'arm64'):
        raise ValueError('Choose x86_64 or arm64 for the dedicated Windows test interpreter.')
    if version and not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Choose an exact Windows Python patch version.')
    selected = version or values['python_version']
    if architecture == 'arm64' and tuple(map(int, selected.split('.'))) < (3, 12, 11):
        if version:
            raise ValueError('Native Windows ARM64 requires managed Python 3.12.11 or later.')
        selected = '3.12.11'
    return selected


def verify_host(values, *, system=None, python=None, os_version=None, windows_client=None,
                hosted=False, runner_arch=None, interpreter_platform=None):
    """Fail before tests if the selected host differs from the shared profile."""
    system = system or platform.system()
    python = python or platform.python_version()
    if python != values['python_version']:
        raise ValueError('Test Python differs from project settings: ' + python)
    if system == 'Darwin':
        actual = os_version or platform.mac_ver()[0]
        required = (None if hosted else values.get('macos_local_major')) or values['macos_major']
        if actual.split('.')[0] != required:
            raise ValueError('macOS version differs from project settings: ' + actual)
    elif system == 'Windows':
        actual = os_version or platform.version()
        client = sys.getwindowsversion().product_type == 1 if windows_client is None else windows_client
        build = int(actual.split('.')[-1])
        if hosted:
            if runner_arch != 'X64' or interpreter_platform != 'win-amd64':
                raise ValueError('Hosted Windows needs a native x64 runner and x64 Python.')
            expected_server = WINDOWS_SERVER_RUNNERS.get(values['windows_runner'])
            if expected_server is not None:
                if client or build != expected_server:
                    raise ValueError('Windows Server build differs from the configured GitHub runner: ' + actual)
                return dict(system=system, python=python, os_version=actual, windows_client=False,
                            runner_arch=runner_arch, interpreter_platform=interpreter_platform)
        if not client:
            raise ValueError('Windows Server cannot replace the configured Windows client.')
        # Windows 11 retains NT 10.0; distinguish the client by its build.
        major = '11' if build >= 22000 else '10'
        if major != values['windows_major']:
            raise ValueError('Windows client version differs from project settings: ' + actual)
        if hosted:
            return dict(system=system, python=python, os_version=actual, windows_client=True,
                        runner_arch=runner_arch, interpreter_platform=interpreter_platform)
    elif system == 'Linux':
        actual = os_version or Path('/etc/os-release').read_text()
        fields = dict(line.split('=', 1) for line in actual.splitlines() if '=' in line)
        if fields.get('ID', '').strip('"') != 'fedora' or fields.get('VERSION_ID', '').strip('"') != values['fedora_image'].split(':')[1]:
            raise ValueError('Linux desktop tests require the configured Fedora version.')
    else:
        raise ValueError('Unsupported desktop test operating system: ' + system)
    return dict(system=system, python=python, os_version=actual)


def configure_android_testbed(path, values):
    """Keep the pinned upstream managed runtime emulator on the native API level."""
    path = Path(path)
    text = path.read_text()
    updated, count = re.subn(r'(?m)^(\s*targetSdk = )\d+\s*$',
                            lambda match: match[1] + values['android_api'], text)
    if count != 1:
        raise ValueError('Pinned Android testbed target SDK recipe changed; review it before testing.')
    updated, count = re.subn(r'(create\("maxVersion"\) \{.*?systemImageSource = )"[^"]+"',
                            r'\1"google_apis"', updated, flags=re.S)
    if count != 1:
        raise ValueError('Pinned Android managed-device recipe changed; review it before testing.')
    path.write_text(updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--target', default='all')
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--configure-android-testbed', type=Path)
    args = parser.parse_args()
    values = load(args.root)
    if args.configure_android_testbed:
        configure_android_testbed(args.configure_android_testbed, values)
        return
    result = outputs(values, args.target)
    if args.github_output:
        with args.github_output.open('a') as stream:
            for key, value in result.items():
                stream.write(key + '=' + value + '\n')
    else:
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
