"""Build and run focused document/notebook probes with owned disposable devices."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import time

from Scripts.build_retention import scratch
from mobile_build.tools import stage
from mobile_build.deployment import manager_settings
from mobile_build.cloud_build import ios, android
from build_manager.apple_simulators import AppleSimulators
from build_manager.android_emulators import AndroidEmulator

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO
BUNDLE = 'io.github.ispaure.logisticsstorageqa'
QA_BUNDLES = {BUNDLE, 'io.github.ispaure.logisticscreationqa',
              'io.github.ispaure.logisticsnotebookqa'}


def command(args, output, *, cwd=None, env=None, timeout=1200):
    print('Running ' + str(args[0]) + '; log: ' + str(output), flush=True)
    with output.open('w') as stream:
        result = subprocess.run(list(map(str, args)), cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(str(output) + '\n' + '\n'.join(output.read_text(errors='replace').splitlines()[-20:]))


def copy_payload(payload, target, *, entry_point='tests.logisticsmobile.document_storage_probe'):
    for name in ('features', 'services', 'commonUtils', 'mobile', 'logisticsmobile'):
        shutil.rmtree(target / name, ignore_errors=True)
        shutil.copytree(payload / name, target / name)
    shutil.copytree(SOURCE / 'mobile_build/native_tests/tests', target / 'tests', dirs_exist_ok=True)
    # Cached native shells predate notebooks. Supply the exact declared pure
    # Python dependency from the configured test environment.
    from importlib.metadata import distribution
    dependency = distribution('packaging')
    if dependency.version != '26.3':
        raise ValueError('The probe requires the declared packaging==26.3 dependency.')
    shutil.copytree(dependency.locate_file('packaging'), target / 'packaging', dirs_exist_ok=True)
    (target / 'logisticsmobile/__main__.py').write_text(
        f'from {entry_point} import main\nmain().main_loop()\n')


def notebook_lifecycle(read, write, background, launch, stop):
    """Background/resume, then terminate/relaunch only the isolated notebook QA app."""
    background()
    time.sleep(1)
    launch()
    time.sleep(1)
    write('notebook-ui/acceptance/resume', b'resume')
    def wait(name):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            value = read(name)
            if value:
                try:
                    result = json.loads(value)
                except json.JSONDecodeError:
                    time.sleep(.1)
                    continue
                if not result['success']:
                    raise RuntimeError(result.get('error', 'Notebook lifecycle failed'))
                return result
            time.sleep(.2)
        raise TimeoutError('Notebook lifecycle acknowledgement missing: ' + name)
    wait('notebook-ui/acceptance/resumed.json')
    write('notebook-result.json', b'')
    stop()
    launch()
    result = wait('notebook-result.json')
    if not result.get('process_restart') or not result.get('background_resume'):
        raise RuntimeError('Notebook process restart/resume was not verified')
    return result


def run_ios(workspace, payload, output, env, *, bundle=BUNDLE,
            entry_point='tests.logisticsmobile.document_storage_probe',
            result_name='document-storage-result.json', family='iPhone', increase_contrast=False):
    if bundle not in QA_BUNDLES:
        raise ValueError('Use an isolated QA bundle; the main app is not a probe target.')
    project = workspace / 'build/logisticsmobile/ios/xcode'
    template = REPO / 'mobile_build/build/logisticsmobile/ios/xcode'
    shutil.copytree(template, project, ignore=lambda directory, names:
        [name for name in names if name == '__pycache__' or (Path(directory) == template and name == 'build')])
    ios(project)
    copy_payload(payload, project / 'LogisticsMobile/app', entry_point=entry_point)
    for path in [project / 'Logistics Mobile.xcodeproj/project.pbxproj',
                 *project.rglob('*Info.plist'), *project.rglob('*.entitlements')]:
        try:
            text = path.read_text()
        except UnicodeError:
            value = plistlib.loads(path.read_bytes())
            text = plistlib.dumps(value).decode()
        path.write_text(text.replace('io.github.ispaure.logisticsmobile', bundle))
    command(['xcodebuild', '-project', project / 'Logistics Mobile.xcodeproj', '-scheme', 'Logistics Mobile',
             '-sdk', 'iphonesimulator', '-configuration', 'Debug', '-derivedDataPath', workspace / 'derived',
             'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'CODE_SIGN_STYLE=Manual', 'DEVELOPMENT_TEAM=', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'build'], output / 'ios-build.log', env=env)
    app = workspace / 'derived/Build/Products/Debug-iphonesimulator/Logistics Mobile.app'
    client = AppleSimulators(env)
    inventory = client.devices()['devices']
    runtime, model = next((rt, row['deviceTypeIdentifier']) for rt, rows in inventory.items()
                          for row in rows if row.get('isAvailable') and family in row['name'])
    name = 'Build Manager Focused QA ' + str(time.time_ns())
    device = client.create(name, model, runtime)
    (output / 'ios-lease.json').write_text(json.dumps(dict(device=device, name=name)))
    cache = console = console_stream = None
    try:
        client.boot(device)
        if increase_contrast:
            client.invoke('ui', device, 'increase_contrast', 'enabled')
            contrast = client.invoke('ui', device, 'increase_contrast')
            (output / 'ios-contrast.json').write_text(json.dumps(dict(increase_contrast=contrast)))
            if contrast != 'enabled':
                raise RuntimeError('iOS Increase Contrast could not be enabled.')
        client.invoke('install', device, str(app))
        cache = Path(client.invoke('get_app_container', device, bundle, 'data')) / 'Library/Caches'
        console_stream = (output / 'ios-console.log').open('w')
        console = subprocess.Popen(['xcrun', 'simctl', 'launch', '--console-pty', device, bundle],
            env=env, stdout=console_stream, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            report = cache / result_name
            if report.exists():
                result = json.loads(report.read_text())
                (output / 'ios-result.json').write_text(json.dumps(result, indent=2))
                client.invoke('io', device, 'screenshot', str(output / 'ios-final.png'))
                if not result['success']:
                    raise RuntimeError(result['error'])
                if result_name == 'notebook-result.json':
                    result = notebook_lifecycle(
                        lambda name: (cache / name).read_bytes() if (cache / name).exists() else None,
                        lambda name, data: (cache / name).write_bytes(data),
                        lambda: client.invoke('launch', device, 'com.apple.Preferences'),
                        lambda: client.invoke('launch', device, bundle),
                        lambda: client.invoke('terminate', device, bundle))
                    (output / 'ios-result.json').write_text(json.dumps(result, indent=2))
                return result
            time.sleep(.3)
        raise TimeoutError('iOS focused QA probe timed out')
    finally:
        if cache is not None and (cache / 'notebook-ui').is_dir():
            shutil.copytree(cache / 'notebook-ui', output / 'notebook-ui', dirs_exist_ok=True)
        if cache is not None and (cache / result_name).exists():
            shutil.copyfile(cache / result_name, output / 'ios-result.json')
        try:
            client.invoke('terminate', device, bundle)
        except RuntimeError:
            pass
        if console is not None:
            try:
                console.wait(timeout=10)
            except subprocess.TimeoutExpired:
                console.terminate()
        if console_stream is not None:
            console_stream.close()
        try:
            client.invoke('uninstall', device, bundle)
        finally:
            client.remove(device, name)
            (output / 'ios-cleanup.json').write_text(json.dumps(dict(device=device, removed=client.matching(device, name) is None)))


def run_android(workspace, payload, output, env, options, *, bundle=BUNDLE,
                entry_point='tests.logisticsmobile.document_storage_probe',
                result_name='document-storage-result.json'):
    if bundle not in QA_BUNDLES:
        raise ValueError('Use an isolated QA bundle; the main app is not a probe target.')
    project = workspace / 'build/logisticsmobile/android/gradle'
    shutil.copytree(REPO / 'mobile_build/build/logisticsmobile/android/gradle', project,
                    ignore=shutil.ignore_patterns('build', '.gradle', '__pycache__'))
    android()
    copy_payload(payload, project / 'app/src/main/python', entry_point=entry_point)
    gradle = project / 'app/build.gradle'
    gradle.write_text(re.sub(r'applicationId "[^"]+"', 'applicationId "' + bundle + '"', gradle.read_text()))
    command([project / 'gradlew', '--offline', '--no-daemon', 'assembleDebug'], output / 'android-build.log', cwd=project, env=env)
    emulator = AndroidEmulator(options['tools.android_sdk'], workspace / 'emulator', environment=env)
    record = None
    try:
        record = emulator.start(options['android.image'], options['android.model'])
        serial = record['serial']
        emulator.invoke('-s', serial, 'install', str(project / 'app/build/outputs/apk/debug/app-debug.apk'), timeout=90)
        emulator.invoke('-s', serial, 'shell', 'am', 'start', '-n', bundle + '/org.beeware.android.MainActivity')
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            value = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                'cat', 'cache/' + result_name], env=env, capture_output=True, timeout=15)
            if value.returncode == 0:
                try:
                    result = json.loads(value.stdout)
                except json.JSONDecodeError:
                    time.sleep(.1)
                    continue
                (output / 'android-result.json').write_text(json.dumps(result, indent=2))
                if not result['success']:
                    raise RuntimeError(result['error'])
                if result_name == 'notebook-result.json':
                    def read(name):
                        found = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                            'cat', 'cache/' + name], env=env, capture_output=True, timeout=15)
                        return found.stdout if found.returncode == 0 else None
                    def write(name, data):
                        subprocess.run([str(emulator.adb), '-s', serial, 'shell', 'run-as', bundle,
                            'tee', 'cache/' + name], input=data, env=env, capture_output=True, check=True, timeout=15)
                    result = notebook_lifecycle(read, write,
                        lambda: emulator.invoke('-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_HOME'),
                        lambda: emulator.invoke('-s', serial, 'shell', 'am', 'start', '-n', bundle + '/org.beeware.android.MainActivity'),
                        lambda: emulator.invoke('-s', serial, 'shell', 'am', 'force-stop', bundle))
                    (output / 'android-result.json').write_text(json.dumps(result, indent=2))
                    for name in ('acceptance.rmdoc', 'modern.rmdoc'):
                        archive = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                            'cat', 'cache/notebook-ui/acceptance/' + name], env=env, capture_output=True, check=True, timeout=15)
                        (output / name).write_bytes(archive.stdout)
                return result
            time.sleep(.3)
        raise TimeoutError('Android document storage probe timed out')
    finally:
        if record is not None:
            try:
                screen = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                    'screencap', '-p'], env=env, capture_output=True, timeout=15)
                if screen.returncode == 0:
                    (output / 'android-final.png').write_bytes(screen.stdout)
            except (OSError, subprocess.SubprocessError):
                pass  # A missing screenshot must not prevent owned cleanup.
            report_data = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                'run-as', bundle, 'cat', 'cache/' + result_name], env=env, capture_output=True, timeout=15)
            if report_data.returncode == 0 and report_data.stdout:
                (output / 'android-result.json').write_bytes(report_data.stdout)
            (output / 'android-logcat.txt').write_text(emulator.invoke('-s', record['serial'], 'logcat', '-d', '-t', '2000'))
            emulator.invoke('-s', record['serial'], 'uninstall', bundle)
        # The manager's lease validates ownership before removing the AVD.
        emulator.cleanup()
        (output / 'android-cleanup.json').write_text(json.dumps(dict(removed=not emulator.marker.exists())))


def main():
    global SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('ios', 'android'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=REPO,
                        help='Validate a manager-owned source snapshot using this checkout’s native templates.')
    parser.add_argument('--probe', choices=('storage', 'notebook', 'creation'), default='storage')
    parser.add_argument('--family', choices=('iPhone', 'iPad'), default='iPhone')
    parser.add_argument('--increase-contrast', action='store_true')
    args = parser.parse_args()
    SOURCE = args.source_root.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    options, _ = manager_settings.settings(REPO / 'mobile_build')
    env = dict(os.environ, DEVELOPER_DIR=options['tools.xcode'], ANDROID_HOME=options['tools.android_sdk'],
               ANDROID_SDK_ROOT=options['tools.android_sdk'], JAVA_HOME=options['tools.java'])
    env['PATH'] = str(REPO / 'mobile_build/.tools/go/bin') + os.pathsep + env['PATH']
    os.environ.update(env)
    with scratch(REPO) as workspace:
        os.environ['LOGISTICS_DEPLOY_WORKSPACE'] = str(workspace)
        env['LOGISTICS_DEPLOY_WORKSPACE'] = str(workspace)
        shutil.copyfile(SOURCE / 'mobile_build/pyproject.toml', workspace / 'pyproject.toml')
        payload = workspace / 'payload'
        manifest = stage(SOURCE, payload, allow_dirty=SOURCE == REPO)
        (args.output / 'source.json').write_text(json.dumps(manifest, indent=2))
        creation_profile = dict(bundle='io.github.ispaure.logisticscreationqa',
            entry_point='tests.logisticsmobile.document_creation_probe',
            result_name='document-creation-evidence/result.json') if args.probe == 'creation' else {}
        if args.platform == 'ios':
            profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                           entry_point='tests.logisticsmobile.notebook_probe',
                           result_name='notebook-result.json') if args.probe == 'notebook' else creation_profile
            run_ios(workspace, payload, args.output, env, family=args.family, increase_contrast=args.increase_contrast, **profile)
        else:
            profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                           entry_point='tests.logisticsmobile.notebook_probe',
                           result_name='notebook-result.json') if args.probe == 'notebook' else creation_profile
            run_android(workspace, payload, args.output, env, options, **profile)


if __name__ == '__main__':
    main()
