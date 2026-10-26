"""Stage current local sources, build and install a normal Android debug app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

from ..tools import stage
from .deployment_paths import output_root, prepare_workspace

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = 'io.github.ispaure.logisticsmobile'
PROJECT = output_root(ROOT) / 'build/logisticsmobile/android/gradle'


def run(command, env, *, log=None, timeout=20):
    if log is None:
        return subprocess.run(command, cwd=output_root(ROOT), env=env, check=True, capture_output=True, text=True, timeout=timeout).stdout
    log.parent.mkdir(parents=True, exist_ok=True)
    print('Running ' + str(command[0]) + '; log: ' + str(log), flush=True)
    with log.open('w') as output:
        result = subprocess.run(command, cwd=output_root(ROOT), env=env, stdout=output, stderr=subprocess.STDOUT)
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
    """Reconnect advertised paired devices, including Bonjour-only macOS peers."""
    from .wireless_adb import discover
    discover(adb, env, run)


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
        fields = line.rsplit(None, 1)
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
    workspace = prepare_workspace(ROOT)
    with tempfile.TemporaryDirectory(prefix='logistics-android-', dir=workspace / 'build') as temporary:
        replacement = Path(temporary) / 'payload'
        stage(ROOT.parent, replacement, allow_dirty=True)
        payload = workspace / 'payload'
        previous = Path(temporary) / 'previous-payload'
        if payload.exists():
            payload.rename(previous)
        replacement.rename(payload)
        try:
            run([sys.executable, str(ROOT / 'cloud_build.py'), 'licenses'], env, log=workspace / 'logs/android-licenses.log')
        except Exception:
            shutil.rmtree(payload)
            if previous.exists():
                previous.rename(payload)
            raise
    action = 'update' if (PROJECT / 'gradlew').exists() else 'create'
    command = [sys.executable, '-m', 'briefcase', action, 'android', '--no-input']
    if action == 'update':
        command.append('--update-requirements')
    run(command, env, log=workspace / 'logs/android-update.log')


def installed_version(adb, env, serial):
    details = run([str(adb), '-s', serial, 'shell', 'dumpsys', 'package', BUNDLE], env)
    match = re.search(r'\bversionCode=(\d+)', details)
    return int(match[1]) if match else 0


def deployment_version(adb, env, serials, configured):
    """Reserve above installed and tester builds before compiling anything."""
    numbers = [configured, *(installed_version(adb, env, serial) + 1 for serial in serials)]
    for record, field in ((ROOT / '.android-beta/build.json', 'last_build'),
                          (ROOT / '.tools/android-deployment-build.json', 'last_build')):
        if record.exists():
            numbers.append(int(json.loads(record.read_text())[field]) + 1)
    number = max(numbers)
    if number > 2100000000:
        raise ValueError('Android version code limit exceeded.')
    record = ROOT / '.tools/android-deployment-build.json'
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(dict(last_build=number)) + '\n')
    return number


def build_tools(env):
    candidates = [p for p in (Path(env['ANDROID_HOME']) / 'build-tools').iterdir()
                  if re.fullmatch(r'\d+(\.\d+)+', p.name) and (p / 'apksigner').is_file()]
    return max(candidates, key=lambda p: tuple(map(int, p.name.split('.'))))


def apk_certificate(apk, tools, env):
    report = run([str(tools / 'apksigner'), 'verify', '--print-certs', str(apk)], env)
    match = re.search(r'Signer #1 certificate SHA-256 digest: ([a-fA-F0-9]{64})', report)
    if not match:
        raise ValueError('Cannot verify Android APK signing certificate.')
    return match[1].lower()


def compatible_apk(adb, env, serial, apk):
    """Retain debug signing unless the installed app requires our saved beta key."""
    tools = build_tools(env)
    paths = run([str(adb), '-s', serial, 'shell', 'pm', 'path', BUNDLE], env)
    installed = next((line.removeprefix('package:') for line in paths.splitlines()
                      if line.startswith('package:') and line.endswith('/base.apk')), None)
    if installed is None:
        return apk
    with tempfile.TemporaryDirectory(prefix='logistics-signing-') as directory:
        previous = Path(directory) / 'installed.apk'
        run([str(adb), '-s', serial, 'pull', installed, str(previous)], env)
        certificate = apk_certificate(previous, tools, env)
    if apk_certificate(apk, tools, env) == certificate:
        return apk
    private = ROOT / '.android-beta'
    key, record = private / 'signing.p12', private / 'signing.json'
    if not key.is_file() or not record.is_file():
        raise ValueError('Installed app requires a different signing key. Restore mobile_build/.android-beta; app data is preserved.')
    password = json.loads(record.read_text())['password']
    signing_env = dict(env, LOGISTICS_BETA_STORE_PASSWORD=password)
    public = subprocess.check_output([str(Path(env['JAVA_HOME']) / 'bin/keytool'), '-exportcert',
        '-keystore', str(key), '-alias', 'logistics-beta', '-storepass:env',
        'LOGISTICS_BETA_STORE_PASSWORD'], env=signing_env, stderr=subprocess.PIPE)
    if hashlib.sha256(public).hexdigest() != certificate:
        raise ValueError('Saved beta key does not match the installed app. Restore its original key; app data is preserved.')
    signed = output_root(ROOT) / 'build' / ('compatible-' + re.sub(r'[^a-zA-Z0-9_-]', '_', serial) + '.apk')
    signed.parent.mkdir(parents=True, exist_ok=True)
    run([str(tools / 'apksigner'), 'sign', '--ks', str(key), '--ks-key-alias', 'logistics-beta',
         '--ks-pass', 'env:LOGISTICS_BETA_STORE_PASSWORD', '--out', str(signed), str(apk)], signing_env)
    if apk_certificate(signed, tools, env) != certificate:
        raise ValueError('Compatible APK signing verification failed.')
    print('Using the existing beta signing identity for ' + serial + '.', flush=True)
    return signed


def deploy(device=None, *, build_only=False, devices=None, discover=True):
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['briefcase']
    if config['bundle'] + '.logisticsmobile' != BUNDLE:
        raise ValueError('Android bundle identity changed; deployment stopped.')
    env = deployment_environment()
    env, adb = tools_environment(env)
    if discover:
        discover_wireless(adb, env)
    if devices is None:
        output = run([str(adb), 'devices'], env)
        devices = ([line.split()[0] for line in output.splitlines()
                    if len(line.split()) == 2 and line.split()[1] == 'device'] if build_only
                   else [select_device(output, device)])
    number = deployment_version(adb, env, devices,
        config.get('app', {}).get('logisticsmobile', {}).get('android', {}).get('version_code', 1))
    print('Building Android version code ' + str(number) + '.', flush=True)
    refresh_sources(env)
    settings = ROOT / '.tools/android-sdk.json'
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({name: env[name] for name in ('ANDROID_HOME', 'BRIEFCASE_HOME') if name in env}))
    # The bridge helper also installs current launcher/appearance resources.
    run([sys.executable, str(ROOT / 'cloud_build.py'), 'android'], env, log=output_root(ROOT) / 'logs/android-bridge.log')
    init = output_root(ROOT) / 'build/deployment-version.gradle'
    init.parent.mkdir(parents=True, exist_ok=True)
    init.write_text('gradle.beforeProject { p ->\n'
        '  p.pluginManager.withPlugin("com.android.application") {\n'
        '    p.androidComponents.finalizeDsl { dsl ->\n'
        f'      dsl.defaultConfig.versionCode = {number}\n'
        f'      dsl.defaultConfig.versionName = {json.dumps(config["version"])}\n' + '    }\n  }\n}\n')
    run([str(PROJECT / 'gradlew'), '--no-daemon', '-p', str(PROJECT), '-I', str(init), ':app:assembleDebug'], env,
        log=output_root(ROOT) / 'logs/android-build.log')
    apk = PROJECT / 'app/build/outputs/apk/debug/app-debug.apk'
    if not apk.is_file():
        raise ValueError('Expected debug APK was not produced: ' + str(apk))
    if build_only:
        print('Android APK: ' + str(apk))
        return
    install_apk(adb, env, devices[0], apk)


def install_apk(adb, env, serial, apk):
    """Update one authorized target without changing its identity or data."""
    prefix = [str(adb), '-s', serial]
    apk = compatible_apk(adb, env, serial, apk)
    # In-place update only. Signature/version failures never trigger uninstall.
    run([*prefix, 'install', '-r', str(apk)], env, log=output_root(ROOT) / 'logs/android-install.log')
    run([*prefix, 'shell', 'am', 'force-stop', BUNDLE], env)
    result = run([*prefix, 'shell', 'am', 'start', '-W', '-n', BUNDLE + '/org.beeware.android.MainActivity'], env, timeout=90)
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
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
