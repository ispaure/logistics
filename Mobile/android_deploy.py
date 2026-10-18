"""Stage current local sources, build and install a normal Android debug app."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib

try:
    from .tools import stage
except ImportError:
    from tools import stage

ROOT = Path(__file__).resolve().parent
BUNDLE = 'io.github.ispaure.logisticsmobile'
PROJECT = ROOT / 'build/logisticsmobile/android/gradle'


def run(command, env, *, log=None):
    if log is None:
        return subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True, text=True, timeout=20).stdout
    log.parent.mkdir(parents=True, exist_ok=True)
    print('Running ' + str(command[0]) + '; log: ' + str(log), flush=True)
    with log.open('w') as output:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('Android deployment stopped. See ' + str(log) + '\n' + '\n'.join(log.read_text(errors='replace').splitlines()[-18:]))


def deployment_environment():
    env = dict(os.environ)
    settings = ROOT / '.tools/android-sdk.json'
    if settings.is_file():
        try:
            saved = json.loads(settings.read_text())
            if not isinstance(saved, dict):
                raise ValueError('Invalid SDK settings.')
            for name in ('ANDROID_HOME', 'BRIEFCASE_HOME'):
                if isinstance(saved.get(name), str) and Path(saved[name]).is_dir():
                    env.setdefault(name, saved[name])
        except (OSError, ValueError, TypeError):
            pass
    return env


def discover_wireless(adb, env):
    """Reconnect advertised TLS endpoints; pairing remains an explicit action."""
    try:
        services = run([str(adb), 'mdns', 'services'], env)
    except (OSError, subprocess.SubprocessError):
        return
    for line in services.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[1] != '_adb-tls-connect._tcp':
            continue
        # adb itself authenticates each peer with the existing pairing keys.
        try:
            run([str(adb), 'connect', parts[2]], env)
        except (OSError, subprocess.SubprocessError):
            continue


def tools_environment(env):
    if env.get('BRIEFCASE_HOME'):
        cache = Path(env['BRIEFCASE_HOME'])
    else:
        from platformdirs import PlatformDirs
        cache = PlatformDirs(
            'org.beeware.briefcase' if platform.system() == 'Darwin' else 'briefcase', 'BeeWare').user_cache_path
    sdk = Path(env.get('ANDROID_HOME') or env.get('ANDROID_SDK_ROOT') or cache / 'tools/android_sdk')
    adb = sdk / 'platform-tools/adb'
    if not adb.is_file():
        raise ValueError('Android SDK platform-tools are unavailable at ' + str(sdk) + '. Check ANDROID_HOME and the Briefcase setup log.')
    env = dict(env, ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk))
    java = cache / 'tools/java17'
    if platform.system() == 'Darwin':
        java /= 'Contents/Home'
    if not env.get('JAVA_HOME') and (java / 'bin/javac').is_file():
        env['JAVA_HOME'] = str(java)
        env['PATH'] = str(java / 'bin') + os.pathsep + env.get('PATH', '')
    return env, adb


def select_device(output, requested=None, *, ask=input):
    states = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in ('device', 'offline', 'unauthorized'):
            states[fields[0]] = fields[1]
    online = [serial for serial, state in states.items() if state == 'device']
    if requested:
        if states.get(requested) != 'device':
            raise ValueError('Device ' + requested + ' is unavailable or unauthorized. Unlock it and accept USB debugging.')
        return requested
    if len(online) == 1:
        return online[0]
    if not online:
        raise ValueError('Wake the tablet and enable Wireless debugging on the same Wi-Fi, connect an authorized USB device, or start an emulator, then run again.')
    print('Choose the Android device to update:')
    for number, serial in enumerate(online, 1):
        print(f'  {number}. {serial}')
    try:
        choice = int(ask('Device number: '))
    except (EOFError, ValueError):
        raise ValueError('Specify a device with --device SERIAL.') from None
    if not 1 <= choice <= len(online):
        raise ValueError('Invalid device selection.')
    return online[choice - 1]


def refresh_sources(env):
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='logistics-android-', dir=ROOT / 'build') as temporary:
        replacement = Path(temporary) / 'payload'
        stage(ROOT.parent, replacement, allow_dirty=True)
        payload = ROOT / 'payload'
        previous = Path(temporary) / 'previous-payload'
        if payload.exists():
            payload.rename(previous)
        replacement.rename(payload)
        try:
            run([sys.executable, 'cloud_build.py', 'licenses'], env, log=ROOT / 'logs/android-licenses.log')
        except Exception:
            shutil.rmtree(payload)
            if previous.exists():
                previous.rename(payload)
            raise
    action = 'update' if (PROJECT / 'gradlew').exists() else 'create'
    command = [sys.executable, '-m', 'briefcase', action, 'android', '--no-input']
    if action == 'update':
        command.append('--update-requirements')
    run(command, env, log=ROOT / 'logs/android-update.log')


def deploy(device=None, *, build_only=False):
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['briefcase']
    if config['bundle'] + '.logisticsmobile' != BUNDLE:
        raise ValueError('Android bundle identity changed; deployment stopped.')
    env = deployment_environment()
    refresh_sources(env)
    env, adb = tools_environment(env)
    settings = ROOT / '.tools/android-sdk.json'
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({name: env[name] for name in ('ANDROID_HOME', 'BRIEFCASE_HOME') if name in env}))
    # The bridge helper also installs current launcher/appearance resources.
    run([sys.executable, 'cloud_build.py', 'android'], env, log=ROOT / 'logs/android-bridge.log')
    run([sys.executable, '-m', 'briefcase', 'build', 'android', '--no-input'], env, log=ROOT / 'logs/android-build.log')
    apk = PROJECT / 'app/build/outputs/apk/debug/app-debug.apk'
    if not apk.is_file():
        raise ValueError('Expected debug APK was not produced: ' + str(apk))
    if build_only:
        print('Android APK: ' + str(apk))
        return
    discover_wireless(adb, env)
    serial = select_device(run([str(adb), 'devices'], env), device)
    prefix = [str(adb), '-s', serial]
    # In-place update only. Signature/version failures never trigger uninstall.
    run([*prefix, 'install', '-r', str(apk)], env, log=ROOT / 'logs/android-install.log')
    run([*prefix, 'shell', 'am', 'force-stop', BUNDLE], env)
    result = run([*prefix, 'shell', 'am', 'start', '-W', '-n', BUNDLE + '/org.beeware.android.MainActivity'], env)
    if 'Error' in result or 'Exception' in result:
        raise ValueError('Android could not launch the installed app: ' + result)
    print('Installed and launched Logistics on ' + serial + '. Existing app data was retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='ADB serial; otherwise choose the connected device')
    parser.add_argument('--build-only', action='store_true', help='Build without installing')
    args = parser.parse_args()
    try:
        deploy(args.device, build_only=args.build_only)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
