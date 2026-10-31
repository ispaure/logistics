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

from logistics_build.build_retention import scratch
from mobile_build.tools import stage
from mobile_build.deployment import manager_settings
from mobile_build.cloud_build import ios, android
from build_manager.apple_simulators import AppleSimulators
from build_manager.android_emulators import AndroidEmulator

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO
BUNDLE = 'io.github.ispaure.logisticsstorageqa'
QA_BUNDLES = {BUNDLE, 'io.github.ispaure.logisticscreationqa', 'io.github.ispaure.logisticsrawinkqa',
              'io.github.ispaure.logisticsnotebookqa', 'io.github.ispaure.logisticsfeaturesqa',
              'io.github.ispaure.logisticsreaderspaceqa', 'io.github.ispaure.logisticsviewerlayoutqa'}
NATIVE_DIAGNOSTICS = ('logistics-native-ui-timings.json', 'logistics-native-ui-error.txt',
                      'logistics-native-ui-fault.log', 'reader-space.png', 'notes-fullscreen.png', 'sync-portrait.png', 'sync-landscape-left.png')


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
    if entry_point.endswith(('.viewer_layout_probe', '.control_center_probe')):
        from tests.readers.video_fixtures import codec_matrix
        codec_matrix(target / 'tests/logisticsmobile/video-fixtures', duration=60)
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
            result_name='document-storage-result.json', family='iPhone', increase_contrast=False, duoctl=None, source_app=None, pose=None):
    if bundle not in QA_BUNDLES:
        raise ValueError('Use an isolated QA bundle; the main app is not a probe target.')
    if source_app is None:
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
    else:
        # Reuse only an exact native source build. Python and tests are restaged;
        # a stale compiled adapter must never masquerade as current acceptance.
        from hashlib import sha256
        native_sources = source_app.parents[4] / 'build/logisticsmobile/ios/xcode/Support'
        hashes = {}
        for source in (SOURCE / 'Python/features/video/mobile/ios').glob('*.m'):
            compiled = native_sources / source.name
            if not compiled.is_file() or compiled.read_bytes() != source.read_bytes():
                raise ValueError('Reusable shell has stale native video source: ' + source.name)
            hashes[source.name] = sha256(source.read_bytes()).hexdigest()
        app = workspace / 'Viewer Layout QA.app'
        shutil.copytree(source_app, app, symlinks=True)
        copy_payload(payload, app / 'app', entry_point=entry_point)
        info = app / 'Info.plist'
        metadata = plistlib.loads(info.read_bytes())
        metadata['CFBundleIdentifier'] = bundle
        info.write_bytes(plistlib.dumps(metadata))
        for directory in ('PlugIns', 'Extensions'):
            shutil.rmtree(app / directory, ignore_errors=True)
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True, capture_output=True)
        (output / 'native-reuse.json').write_text(json.dumps(dict(source=str(source_app), sources=hashes), indent=2))
    if family == 'all':
        reports = []
        for label, device_family, pose in (('iphone', 'iPhone', None), ('ipad', 'iPad', None),
                ('duo-closed', 'iPhone Duo', 'closed'), ('duo-open', 'iPhone Duo', 'open'),
                ('duo-partial', 'iPhone Duo', 'partial')):
            destination = output / label
            destination.mkdir(exist_ok=True)
            try:
                reports.append(exercise_ios_app(app, destination, env, bundle=bundle,
                    entry_point=entry_point, result_name=result_name, family=device_family,
                    increase_contrast=increase_contrast, duoctl=duoctl, pose=pose))
            except Exception as error:
                reports.append(dict(success=False, family=label, error=str(error)))
        (output / 'matrix.json').write_text(json.dumps(reports, indent=2))
        if not all(row['success'] for row in reports):
            raise RuntimeError('Viewer matrix has failures; inspect matrix.json')
        return reports
    return exercise_ios_app(app, output, env, bundle=bundle, entry_point=entry_point,
        result_name=result_name, family=family, increase_contrast=increase_contrast, duoctl=duoctl, pose=pose)


def exercise_ios_app(app, output, env, *, bundle=BUNDLE,
        entry_point='tests.logisticsmobile.document_storage_probe',
        result_name='document-storage-result.json', family='iPhone', increase_contrast=False,
        duoctl=None, pose=None):
    client = AppleSimulators(env)
    inventory = client.devices()['devices']
    runtime, model = next((rt, row['deviceTypeIdentifier']) for rt, rows in inventory.items()
                          for row in rows if row.get('isAvailable') and family in row['name']
                          and (family != 'iPhone' or 'Duo' not in row['name']))
    name = 'Build Manager Focused QA ' + str(time.time_ns())
    device = client.create(name, model, runtime)
    (output / 'ios-lease.json').write_text(json.dumps(dict(device=device, name=name)))
    cache = console = console_stream = None
    try:
        client.boot(device)
        if pose is not None:
            if duoctl is None:
                raise ValueError('Duo pose matrix requires --duoctl with the reviewed simulator helper.')
            import sys
            tool = [sys.executable, str(duoctl), '-d', device]
            if pose != 'closed':
                # A freshly booted Duo can report an open hinge while its cover
                # display is still active. Establish a real closed-to-open change.
                subprocess.run([*tool, 'hinge', '0'], timeout=60, env=env, check=True, capture_output=True)
            for attempt in range(3):
                changed = subprocess.run([*tool, 'hinge', str({'closed': 0, 'open': 180, 'partial': 127}[pose])],
                    timeout=60, env=env, capture_output=True)
                if changed.returncode == 0:
                    break
                (output / f'pose-attempt-{attempt}.log').write_bytes(changed.stdout + changed.stderr)
                if attempt == 2:
                    changed.check_returncode()
                time.sleep(1)
            (output / 'pose.json').write_bytes(subprocess.check_output([*tool, 'state'], env=env, timeout=30))
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
        deadline = time.monotonic() + (1800 if result_name == 'logistics-native-ui-result.json' else 240)
        next_progress = 0
        while time.monotonic() < deadline:
            if result_name == 'logistics-native-ui-result.json' and time.monotonic() >= next_progress:
                next_progress = time.monotonic() + 30
                timings = cache / NATIVE_DIAGNOSTICS[0]
                if timings.exists():
                    value = json.loads(timings.read_text())
                    summary = value['summary']
                    checkpoints = summary['checkpoints']
                    print(json.dumps(dict(native_elapsed_s=round(summary['elapsed_s'], 1),
                        last_case=checkpoints[-1]['case'] if checkpoints else None,
                        active=[row['name'] for row in value['records'] if row['status'] == 'running'])), flush=True)
            report = cache / result_name
            if report.exists():
                result = json.loads(report.read_text())
                (output / 'ios-result.json').write_text(json.dumps(result, indent=2))
                client.invoke('io', device, 'screenshot', str(output / 'ios-final.png'))
                if not result['success']:
                    raise RuntimeError(result.get('error') or result.get('errors') or 'Native layout assertions failed')
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
        if cache is not None:
            for artifact_name in NATIVE_DIAGNOSTICS:
                if (cache / artifact_name).exists():
                    shutil.copyfile(cache / artifact_name, output / artifact_name)
        if cache is not None and entry_point.endswith('.notebook_apple_memory_probe'):
            for artifact_name in ('notebook-memory-progress.json', 'notebook-memory.rmdoc', 'notebook-memory.png'):
                if (cache / artifact_name).exists():
                    shutil.copyfile(cache / artifact_name, output / artifact_name)
        if cache is not None and (cache / 'notebook-ui').is_dir():
            shutil.copytree(cache / 'notebook-ui', output / 'notebook-ui', dirs_exist_ok=True)
        if cache is not None and (cache / 'viewer-layout').is_dir():
            shutil.copytree(cache / 'viewer-layout', output / 'viewer-layout', dirs_exist_ok=True)
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
                result_name='document-storage-result.json', device=None):
    if bundle not in QA_BUNDLES:
        raise ValueError('Use an isolated QA bundle; the main app is not a probe target.')
    memory_probe = entry_point.endswith(('.notebook_memory_probe', '.notebook_soak_probe', '.notebook_load_probe'))
    project = workspace / 'build/logisticsmobile/android/gradle'
    shutil.copytree(REPO / 'mobile_build/build/logisticsmobile/android/gradle', project,
                    ignore=shutil.ignore_patterns('build', '.gradle', '__pycache__'))
    android()
    copy_payload(payload, project / 'app/src/main/python', entry_point=entry_point)
    gradle = project / 'app/build.gradle'
    gradle.write_text(re.sub(r'applicationId "[^"]+"', 'applicationId "' + bundle + '"', gradle.read_text()))
    manifest = project / 'app/src/main/AndroidManifest.xml'
    manifest.write_text(manifest.read_text().replace('io.github.ispaure.logisticsmobile', bundle))
    if entry_point.endswith('.notebook_input_probe') or memory_probe:
        with gradle.open('a') as stream:
            stream.write('\nandroid.sourceSets.main.java.srcDir(' + json.dumps(str(REPO / 'mobile_build/native_tests/android/notebooks')) + ')\n')
    raw_ink = entry_point.endswith('.boox_raw_ink_probe')
    hands_on = entry_point.endswith('.boox_preview_probe')
    if raw_ink:
        with gradle.open('a') as stream:
            stream.write('\nandroid.sourceSets.main.java.srcDir(' + json.dumps(str(REPO / 'mobile_build/native_tests/android/boox_raw')) + ')\n')
            stream.write('dependencies { implementation("com.onyx.android.sdk:onyxsdk-pen:1.5.8") { exclude group: "com.android.support" } }\n')
            stream.write('android { packagingOptions { pickFirst "lib/*/libc++_shared.so" } }\n')
        with (project / 'gradle.properties').open('a') as stream:
            stream.write('\nandroid.enableJetifier=true\n')
    command([project / 'gradlew', *([] if raw_ink else ['--offline']), '--no-daemon', 'assembleDebug'], output / 'android-build.log', cwd=project, env=env)
    emulator = AndroidEmulator(options['tools.android_sdk'], workspace / 'emulator', environment=env)
    record = None
    try:
        if device is not None:
            if emulator.invoke('-s', device, 'get-state').strip() != 'device':
                raise RuntimeError('The selected Android device is unavailable.')
            record = dict(serial=device)
        else:
            record = emulator.start(options['android.image'], options['android.model'])
        serial = record['serial']
        emulator.invoke('-s', serial, 'install', str(project / 'app/build/outputs/apk/debug/app-debug.apk'), timeout=90)
        if device is not None:
            # Boox's launcher can auto-freeze a newly installed QA identity.
            # Only this disposable package is enabled, then removed in finally.
            time.sleep(2)
            emulator.invoke('-s', serial, 'shell', 'pm', 'enable', bundle)
        emulator.invoke('-s', serial, 'shell', 'am', 'start', '-n', bundle + '/org.beeware.android.MainActivity')
        deadline = time.monotonic() + (2400 if hands_on or result_name == 'logistics-native-ui-result.json' else 900 if raw_ink or memory_probe else 240)
        last_stage = None
        while time.monotonic() < deadline:
            if memory_probe:
                progress = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                    'cat', 'cache/notebook-memory-progress.json'], env=env, capture_output=True, timeout=15)
                if progress.returncode == 0 and progress.stdout != last_stage:
                    last_stage = progress.stdout
                    (output / 'memory-progress.json').write_bytes(progress.stdout)
                    try:
                        print('Memory QA: ' + json.dumps(json.loads(progress.stdout)['samples'][-1]), flush=True)
                        ordinal = len(json.loads(progress.stdout)['samples'])
                        (output / f'android-memory-{ordinal:02d}.txt').write_text(
                            emulator.invoke('-s', serial, 'shell', 'dumpsys', 'meminfo', '--package', bundle))
                    except (ValueError, KeyError, IndexError):
                        pass
            if raw_ink or hands_on:
                ready = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                    'cat', 'cache/boox-raw-ink/stage.json'], env=env, capture_output=True, timeout=15)
                try:
                    ready_stage = json.loads(ready.stdout) if ready.returncode == 0 else None
                except json.JSONDecodeError:
                    ready_stage = None
                if isinstance(ready_stage, dict) and 'stage' in ready_stage and ready.stdout != last_stage:
                    last_stage = ready.stdout
                    (output / 'stage.json').write_bytes(ready.stdout)
                    print('Raw ink QA: ' + ready.stdout.decode().strip(), flush=True)
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
                    raise RuntimeError(result.get('error') or result.get('errors') or 'Native layout assertions failed')
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
            if entry_point.endswith(('.viewer_layout_probe', '.control_center_probe')):
                import io
                import tarfile
                archive = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                    'run-as', bundle, 'tar', '-cf', '-', 'cache/viewer-layout'],
                    env=env, capture_output=True, timeout=45)
                if archive.returncode == 0:
                    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as evidence:
                        evidence.extractall(output, filter='data')
            if raw_ink or hands_on:
                for name in ('baseline.png', 'raw-final.png', 'comparison.rmdoc', 'stage.json', 'observations.json'):
                    artifact = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                        'run-as', bundle, 'cat', 'cache/boox-raw-ink/' + name], env=env, capture_output=True, timeout=15)
                    if artifact.returncode == 0 and not artifact.stdout.startswith(b'cat: '):
                        (output / name).write_bytes(artifact.stdout)
            if entry_point.endswith('.notebook_input_probe'):
                for name in ('canvas.png', 'dropdown.png', 'overview.png'):
                    artifact = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                        'run-as', bundle, 'cat', 'cache/notebook-input/' + name], env=env, capture_output=True, timeout=15)
                    if artifact.returncode == 0:
                        (output / name).write_bytes(artifact.stdout)
            if memory_probe:
                for name in ('notebook-memory-progress.json', 'notebook-memory.rmdoc', 'notebook-memory.png',
                             *[f'notebook-soak-{index:02d}.png' for index in range(8)]):
                    artifact = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                        'run-as', bundle, 'cat', 'cache/' + name], env=env, capture_output=True, timeout=15)
                    if artifact.returncode == 0:
                        (output / name).write_bytes(artifact.stdout)
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
            for name in NATIVE_DIAGNOSTICS:
                artifact = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                    'run-as', bundle, 'cat', 'cache/' + name], env=env, capture_output=True, timeout=15)
                if artifact.returncode == 0:
                    (output / name).write_bytes(artifact.stdout)
            (output / 'android-logcat.txt').write_text(emulator.invoke('-s', record['serial'], 'logcat', '-d', '-t', '2000'))
            try:
                (output / 'android-exit-info.txt').write_text(emulator.invoke(
                    '-s', record['serial'], 'shell', 'dumpsys', 'activity', 'exit-info', bundle))
            except RuntimeError:
                pass
            emulator.invoke('-s', record['serial'], 'uninstall', bundle)
            if device is not None:
                remaining = emulator.invoke('-s', device, 'shell', 'pm', 'list', 'packages', 'logistics')
                (output / 'remaining-packages.txt').write_text(remaining)
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
    parser.add_argument('--probe', choices=('storage', 'reader-space', 'viewer-layout', 'recent-deletion', 'notebook', 'documents', 'localcrypt', 'native-suite', 'first-tap', 'storage-selector', 'notes-fullscreen', 'sync-status', 'control-center', 'creation', 'features', 'pdf-annotation', 'notebook-input', 'notebook-memory', 'notebook-soak', 'notebook-load', 'boox-raw-ink', 'boox-preview'), default='storage')
    parser.add_argument('--device', help='Explicit connected Android serial; QA app is removed afterward')
    parser.add_argument('--family', choices=('iPhone', 'iPad', 'iPhone Duo', 'all'), default='iPhone')
    parser.add_argument('--ios-app', type=Path, help='Reuse a managed simulator shell only when native video source bytes match')
    parser.add_argument('--pose', choices=('closed', 'open', 'partial'), help='Explicit Duo simulator posture')
    parser.add_argument('--duoctl', type=Path, help='Reviewed external simulator-only Duo pose helper')
    parser.add_argument('--increase-contrast', action='store_true')
    args = parser.parse_args()
    if args.pose and (args.platform != 'ios' or args.family != 'iPhone Duo'):
        parser.error('--pose requires an iOS iPhone Duo run')
    if args.device and args.platform != 'android':
        parser.error('--device requires Android.')
    if args.probe == 'notebook-input' and args.platform != 'android':
        parser.error('The notebook-input native probe requires Android.')
    if args.probe in ('notebook-soak', 'notebook-load') and (args.platform != 'android' or not args.device):
        parser.error('The notebook soak/load probe requires an explicit physical Android --device.')
    if args.probe == 'recent-deletion' and args.platform != 'android':
        parser.error('The recent-deletion native probe requires Android.')
    if args.probe in ('boox-raw-ink', 'boox-preview') and (args.platform != 'android' or not args.device):
        parser.error('The raw ink probe requires an explicit physical Android --device.')
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
        if args.probe == 'reader-space':
            creation_profile = dict(bundle='io.github.ispaure.logisticsreaderspaceqa',
                entry_point='tests.logisticsmobile.reader_space_probe', result_name='reader-space-result.json')
        if args.probe == 'viewer-layout':
            creation_profile = dict(bundle='io.github.ispaure.logisticsviewerlayoutqa',
                entry_point='tests.logisticsmobile.viewer_layout_probe', result_name='viewer-layout-result.json')
        if args.probe == 'features':
            creation_profile = dict(bundle='io.github.ispaure.logisticsfeaturesqa',
                entry_point='tests.logisticsmobile.features_probe', result_name='features-result.json')
        if args.probe == 'recent-deletion':
            creation_profile = dict(entry_point='tests.logisticsmobile.recent_deletion_probe',
                                    result_name='recent-deletion-result.json')
        if args.probe == 'pdf-annotation':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.pdf_annotation_probe', result_name='pdf-annotation-result.json')
        if args.probe == 'documents':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.document_workspace_probe', result_name='document-workspace-result.json')
        if args.probe == 'localcrypt':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.localcrypt_probe', result_name='localcrypt-result.json')
        if args.probe == 'control-center':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.control_center_probe', result_name='control-center-result.json')
        if args.probe == 'sync-status':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.sync_status_probe', result_name='sync-status-result.json')
        if args.probe == 'notes-fullscreen':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.notes_fullscreen_probe', result_name='notes-fullscreen-result.json')
        if args.probe == 'storage-selector':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.storage_selector_probe', result_name='storage-selector-result.json')
        if args.probe == 'first-tap':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.first_tap_probe', result_name='first-tap-result.json')
        if args.probe == 'native-suite':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.native_suite_probe', result_name='logistics-native-ui-result.json')
        if args.platform == 'ios' and (args.family == 'all' or args.pose) and args.duoctl is None:
            from urllib.request import urlopen
            from hashlib import sha256
            # Simulator-only external helper; never copied into an app payload.
            approved = {'duoctl': '9d9d151afb303ddec426beffadb9bfb21309e8ca9ce52fdd6cc4dcc3fd1dbf45',
                'duoctl-helper.m': 'b2d8fb45b0abab1802316ac0c0fa953e9cf644ac54dfbf06281593d4bae28b1f'}
            folder = workspace / 'duo-pose-tool'
            folder.mkdir()
            for name, expected in approved.items():
                with urlopen('https://raw.githubusercontent.com/skarol/duoctl/caad72ec15cae2e6090a4ae2749c6fed721b275e/skills/duoctl/scripts/' + name, timeout=30) as stream:
                    data = stream.read(256 * 1024)
                if sha256(data).hexdigest() != expected:
                    raise ValueError('Simulator helper differs from the previously reviewed source: ' + name)
                (folder / name).write_bytes(data)
            args.duoctl = folder / 'duoctl'
            env['XDG_CACHE_HOME'] = str(workspace / 'duo-tool-cache')
            (args.output / 'pose-tool.json').write_text(json.dumps(approved, indent=2))
        if args.platform == 'ios':
            profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                           entry_point='tests.logisticsmobile.notebook_probe',
                           result_name='notebook-result.json') if args.probe == 'notebook' else creation_profile
            if args.probe == 'notebook-memory':
                profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                    entry_point='tests.logisticsmobile.notebook_apple_memory_probe', result_name='notebook-memory-result.json')
            run_ios(workspace, payload, args.output, env, family=args.family, increase_contrast=args.increase_contrast, duoctl=args.duoctl, source_app=args.ios_app, pose=args.pose, **profile)
        else:
            profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                           entry_point='tests.logisticsmobile.notebook_probe',
                           result_name='notebook-result.json') if args.probe == 'notebook' else creation_profile
            if args.probe == 'notebook-input':
                profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                    entry_point='tests.logisticsmobile.notebook_input_probe', result_name='notebook-input-result.json')
            if args.probe == 'notebook-memory':
                profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                    entry_point='tests.logisticsmobile.notebook_memory_probe', result_name='notebook-memory-result.json')
            if args.probe == 'notebook-soak':
                profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                    entry_point='tests.logisticsmobile.notebook_soak_probe', result_name='notebook-memory-result.json')
            if args.probe == 'notebook-load':
                profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                    entry_point='tests.logisticsmobile.notebook_load_probe', result_name='notebook-memory-result.json')
            if args.probe == 'boox-raw-ink':
                profile = dict(bundle='io.github.ispaure.logisticsrawinkqa',
                    entry_point='tests.logisticsmobile.boox_raw_ink_probe', result_name='boox-raw-ink-result.json')
            if args.probe == 'boox-preview':
                profile = dict(bundle='io.github.ispaure.logisticsrawinkqa',
                    entry_point='tests.logisticsmobile.boox_preview_probe', result_name='boox-preview-result.json')
            run_android(workspace, payload, args.output, env, options, device=args.device, **profile)


if __name__ == '__main__':
    main()
