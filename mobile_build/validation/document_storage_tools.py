"""Build and run focused document/notebook probes with owned disposable devices."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
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
UNIFIED_PROGRESS_BUNDLE = 'io.github.ispaure.logisticsunifiedprogressqa'
UNIFIED_PROGRESS_ENTRY = 'tests.logisticsmobile.unified_progress_probe'
UNIFIED_PROGRESS_RESULT = 'unified-progress-result.json'
UNIFIED_PROGRESS_ANDROID_ENTRY = 'tests.logisticsmobile.unified_progress_android_probe'
UNIFIED_PROGRESS_VIDEO_ENTRY = 'tests.logisticsmobile.unified_progress_video_probe'
QA_BUNDLES = {UNIFIED_PROGRESS_BUNDLE, BUNDLE, 'io.github.ispaure.logisticsnotesauditqa', 'io.github.ispaure.logisticscreationqa', 'io.github.ispaure.logisticsrawinkqa',
              'io.github.ispaure.logisticsnotebookqa', 'io.github.ispaure.logisticsfeaturesqa',
              'io.github.ispaure.logisticsreaderspaceqa', 'io.github.ispaure.logisticsviewerlayoutqa'}
NATIVE_DIAGNOSTICS = ('pdf-edge-left.png', 'pdf-edge-right.png', 'logistics-native-ui-timings.json', 'logistics-native-ui-error.txt', 'logistics-native-ui-webview-counts.json', 'notes-discovery.png', 'notes-file-hold.png', 'notes-compact-files.png',
                      'logistics-native-ui-fault.log', 'chat-laptop.png', 'reader-space.png', 'notes-landing.png', 'notes-fullscreen.png', 'notes-reading-portrait.png', 'notes-reading-landscape-left.png', 'notes-links-landscape-left.png', 'notes-links-portrait.png', 'notes-files-landscape-left.png', 'notes-files-portrait.png', 'sync-portrait.png', 'sync-landscape-left.png')

SYNC_SCREENSHOTS = tuple(f'sync-{orientation}-{destination}.png'
    for orientation in ('portrait', 'landscape-left')
    for destination in ('home', 'files', 'documents', 'chat', 'settings',
                        'files-rclone', 'files-Network-shares', 'files-Local', 'settings-panel'))


def diagnostics(entry_point):
    if entry_point == UNIFIED_PROGRESS_ANDROID_ENTRY:
        return ('progress-fixture-epub-before.png', 'progress-fixture-epub-after.png')
    if entry_point == UNIFIED_PROGRESS_ENTRY:
        return tuple(f'progress-{document}-{phase}.png' for phase in ('before', 'after')
                     for document in ('fixture-cbz', 'fixture-zip', 'fixture-pdf'))
    if entry_point.endswith('.drawer_privacy_probe'):
        return tuple(f'drawer-privacy-{side}-{phase}.png' for side in ('files', 'links')
                     for phase in ('open', 'returned', 'wrong', 'reopened'))
    if entry_point.endswith('.notes_rows_performance_probe'):
        return NATIVE_DIAGNOSTICS + ('notes-performance-progress.json', 'notes-performance-window.json')
    if entry_point.endswith('.speech_playback_probe'):
        return NATIVE_DIAGNOSTICS + ('feedback-progress.json', 'speech-initialization.jsonl',
            'feedback-speech-complete.png', 'feedback-speech-failure.png')
    if entry_point.endswith('.android_header_probe'):
        return NATIVE_DIAGNOSTICS + ('android-header-startup.json',)
    if entry_point.endswith('.notes_markdown_feedback_probe'):
        return NATIVE_DIAGNOSTICS + ('notes-markdown-progress.json', 'notes-markdown-tasks.json', 'notes-markdown-startup.log')
    if entry_point.endswith('.folder_feedback_probe'):
        return NATIVE_DIAGNOSTICS + ('folder-feedback-startup.json', 'folder-feedback-tasks.txt')
    if entry_point.endswith('.chat_notes_feedback_probe'):
        return tuple(dict.fromkeys((*diagnostics('.chat_settings_probe'),
            *diagnostics('.notes_search_probe'), 'chat-settings-result.json', 'notes-search-result.json')))
    if entry_point.endswith('.lockscreen_probe'):
        return tuple('lock-' + name + '.png' for name in
            [*(f'{i}-{pose}{suffix}' for i, pose in enumerate(('portrait', 'landscape-left', 'landscape-right', 'portrait'))
               for suffix in ('', '-keyboard')), 'unlock-keyboard'])
    if entry_point.endswith('.links_images_voices_probe'):
        return NATIVE_DIAGNOSTICS + ('feedback-progress.json',) + tuple(
            'feedback-' + name + '.png' for name in ('15-outgoing', '15-loading', '15-backlinks',
            '15-landscape-left', '15-portrait', '16-list', '16-tiles', '16-information',
            '16-landscape-left', '17-settings', 'failure'))
    if entry_point.endswith('.notes_search_probe'):
        return NATIVE_DIAGNOSTICS + tuple(f'notes-search-{pose}-{scope}.png'
            for pose in ('portrait', 'landscape-left') for scope in ('names', 'documents'))
    if entry_point.endswith('.chat_settings_probe'):
        return NATIVE_DIAGNOSTICS + ('chat-settings-hidden.png',) + tuple(
            f'chat-settings-{pose}-{panel}.png' for pose in ('portrait', 'landscape-left')
            for panel in ('server', 'limits', 'device'))
    if entry_point.endswith('.mobile_feedback_probe'):
        return NATIVE_DIAGNOSTICS + tuple(f'feedback-{name}.png' for name in ('notes-portrait', 'notes-landscape-left', 'help', 'more', 'about-loading', 'about-ready', 'licenses', 'licenses-landscape'))
    if entry_point.endswith('.documents_search_probe'):
        return NATIVE_DIAGNOSTICS + tuple(f'documents-search-{pose}.png'
            for pose in ('portrait', 'landscape-left'))
    if entry_point.endswith('.documents_hub_probe'):
        return NATIVE_DIAGNOSTICS + tuple(f'documents-hub-{orientation}-{panel}.png'
            for orientation in ('portrait', 'landscape-left')
            for panel in ('home', 'files', 'documents', 'libraries', 'search'))
    if entry_point.endswith('.file_transfer_probe'):
        return NATIVE_DIAGNOSTICS + ('file-transfer-progress.png',)
    if entry_point.endswith('.document_creation_probe'):
        return NATIVE_DIAGNOSTICS + ('creation-landscape-left.png', 'creation-portrait.png') + tuple(
            f'creation-{panel}-{pose}.png' for panel in ('formats', 'name', 'change-format', 'locations', 'location', 'folders')
            for pose in ('portrait', 'landscape-left', 'landscape-right'))
    return NATIVE_DIAGNOSTICS + (SYNC_SCREENSHOTS if entry_point.endswith('.sync_status_probe') else ())


def lockscreen_capture_name(raw):
    """Missing adb marker files are startup/polling state, not JSON requests."""
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return None
    name = value.get('name') if isinstance(value, dict) else None
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9-]+', name):
        raise ValueError('Unexpected lock-screen screenshot name')
    return name


def command(args, output, *, cwd=None, env=None, timeout=1200):
    print('Running ' + str(args[0]) + '; log: ' + str(output), flush=True)
    with output.open('w') as stream:
        result = subprocess.run(list(map(str, args)), cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(str(output) + '\n' + '\n'.join(output.read_text(errors='replace').splitlines()[-20:]))


def stage_progress_credentials(folder):
    # The desktop environment owns the project's WinZip AES dependency.
    from importlib.util import find_spec
    python = sys.executable if find_spec('pyzipper') else REPO / '.venv/bin/python'
    source = folder / 'localcrypt_fixture.json'
    target = folder / 'unified-progress-credentials.b64'
    subprocess.run([python, '-c',
                    'import sys; from mobile_build.validation.make_localcrypt_fixture import stage_encrypted_package; '
                    'stage_encrypted_package(*sys.argv[1:])',
                    str(source), str(target), 'synthetic-session-password'],
                   cwd=SOURCE, env=dict(os.environ, PYTHONPATH=os.pathsep.join((str(SOURCE / 'Python'), str(SOURCE)))),
                   check=True, capture_output=True, timeout=30)


def copy_payload(payload, target, *, entry_point='tests.logisticsmobile.document_storage_probe', android=False):
    for name in ('features', 'services', 'commonUtils', 'mobile', 'logisticsmobile'):
        shutil.rmtree(target / name, ignore_errors=True)
        shutil.copytree(payload / name, target / name)
    shutil.copytree(SOURCE / 'mobile_build/native_tests/tests', target / 'tests', dirs_exist_ok=True)
    if entry_point in (UNIFIED_PROGRESS_ENTRY, UNIFIED_PROGRESS_ANDROID_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY):
        stage_progress_credentials(target / 'tests/logisticsmobile')
    # Cached native shells predate notebooks. Supply the exact declared pure
    # Python dependency from the configured test environment.
    from importlib.metadata import distribution
    dependency = distribution('packaging')
    if dependency.version != '26.3':
        raise ValueError('The probe requires the declared packaging==26.3 dependency.')
    shutil.copytree(dependency.locate_file('packaging'), target / 'packaging', dirs_exist_ok=True)
    if entry_point in (UNIFIED_PROGRESS_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY):
        from tests.readers.video_fixtures import bundled_movie, multitrack_movie
        fixtures = target / 'tests/logisticsmobile/video-fixtures'
        source = bundled_movie('h264-aac.mp4', fixtures)
        long_source = fixtures / 'long.mp4'
        # Extend only the synthetic movie used by this probe. A short clip
        # would immediately qualify for the normal completion reset.
        codec = ['-c', 'copy']
        if android and entry_point == UNIFIED_PROGRESS_VIDEO_ENTRY:
            # The goldfish H.264 decoder has stalled on cold input in the
            # disposable emulator. Keep the real VLC acceptance independent
            # from that codec-specific emulator failure.
            codec = ['-c:v', 'mpeg4', '-threads', '1', '-q:v', '4', '-c:a', 'copy']
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-stream_loop', '14', '-i', str(source), *codec, str(long_source)],
                       check=True, capture_output=True, timeout=30)
        multitrack_movie(fixtures, long_source)
        for temporary in (source, long_source, fixtures / 'tracks.srt'):
            temporary.unlink()
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


def check_progress_report(result, initial_pid):
    """Accept one checkpoint followed by a report from a distinct process."""
    phase, pid = result.get('phase'), result.get('pid')
    if type(pid) is not int or pid <= 0:
        raise ValueError('Progress probe did not report a valid process ID')
    if initial_pid is None and phase == 'checkpoint':
        return pid
    if initial_pid is not None and phase == 'restarted' and pid != initial_pid:
        return pid
    raise ValueError(f'Unexpected progress probe phase/process: {phase!r}, {pid!r}')


def run_ios(workspace, payload, output, env, *, bundle=BUNDLE,
            entry_point='tests.logisticsmobile.document_storage_probe',
            result_name='document-storage-result.json', family='iPhone', increase_contrast=False, duoctl=None, source_app=None, pose=None, runtime_id=None):
    if bundle not in QA_BUNDLES:
        raise ValueError('Use an isolated QA bundle; the main app is not a probe target.')
    if source_app is None:
        project = workspace / 'build/logisticsmobile/ios/xcode'
        template = REPO / 'mobile_build/build/logisticsmobile/ios/xcode'
        if template.is_dir():
            shutil.copytree(template, project, ignore=lambda directory, names:
                [name for name in names if name == '__pycache__' or (Path(directory) == template and name == 'build')])
        else:
            from mobile_build.deployment.deployment_paths import prepare_workspace
            prepare_workspace(SOURCE / 'mobile_build')
            command([sys.executable, '-m', 'briefcase', 'create', 'iOS', '--no-input'],
                    output / 'ios-create.log', cwd=workspace, env=env)
        ios(project)
        if entry_point in (UNIFIED_PROGRESS_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY):
            from hashlib import sha256
            sources = sorted((payload / 'features/video/mobile/ios').glob('*.m'))
            if not {'VideoPlayer.m', 'PlaybackControls.m'} <= {path.name for path in sources}:
                raise ValueError('Captured payload is missing the native video progress adapters.')
            sources.append(payload / 'mobile/ios/ScreenAwake.m')
            for source in sources:
                shutil.copyfile(source, project / 'Support' / source.name)
            (output / 'ios-video-source.json').write_text(json.dumps(
                {path.name: sha256(path.read_bytes()).hexdigest() for path in sources}, indent=2))
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
        if entry_point in (UNIFIED_PROGRESS_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY):
            # Retry against the exact byte-checked native build produced by the
            # first acceptance pass, restaging only captured Python and fixtures.
            parents = source_app.resolve().parents
            if len(parents) < 5 or not all((parents[4] / name).is_file() for name in ('.manager-scratch', '.keep')):
                raise ValueError('Use a freshly built, retained manager progress QA shell.')
        # Reuse only an exact native source build. Python and tests are restaged;
        # a stale compiled adapter must never masquerade as current acceptance.
        from hashlib import sha256
        native_sources = source_app.parents[2] / 'Support'
        # Focused builds put DerivedData beside their generated project inside
        # a leased scratch workspace. Reuse that exact project's native inputs.
        if not native_sources.is_dir() and (source_app.parents[4] / '.manager-scratch').is_file():
            native_sources = source_app.parents[4] / 'build/logisticsmobile/ios/xcode/Support'
        hashes = {}
        for source in [*(SOURCE / 'Python/features/video/mobile/ios').glob('*.m'),
                       SOURCE / 'Python/mobile/ios/ScreenAwake.m']:
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
        # Managed test shells normally launch tests.logisticsmobile. Route
        # through the restaged application entry point for the selected probe.
        metadata['MainModule'] = 'logisticsmobile'
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
                    increase_contrast=increase_contrast, duoctl=duoctl, pose=pose, runtime_id=runtime_id))
            except Exception as error:
                reports.append(dict(success=False, family=label, error=str(error)))
            (output / 'matrix.json').write_text(json.dumps(reports, indent=2))
            print(json.dumps(dict(family=label, success=reports[-1]['success'],
                                  error=reports[-1].get('error'))), flush=True)
        (output / 'matrix.json').write_text(json.dumps(reports, indent=2))
        if not all(row['success'] for row in reports):
            raise RuntimeError('Viewer matrix has failures; inspect matrix.json')
        return reports
    return exercise_ios_app(app, output, env, bundle=bundle, entry_point=entry_point,
        result_name=result_name, family=family, increase_contrast=increase_contrast, duoctl=duoctl, pose=pose, runtime_id=runtime_id)


def simulator_selection(inventory, family, runtime_id=None):
    """Select a model/runtime for a new device; existing devices stay read-only."""
    for runtime, rows in inventory.items():
        if runtime_id is not None and runtime != runtime_id:
            continue
        for row in rows:
            if (row.get('isAvailable') and family in row['name']
                    and (family != 'iPhone' or 'Duo' not in row['name'])):
                return runtime, row['deviceTypeIdentifier']
    raise ValueError('No available simulator model for ' + family
                     + (' in runtime ' + runtime_id if runtime_id else ''))


def exercise_ios_app(app, output, env, *, bundle=BUNDLE,
        entry_point='tests.logisticsmobile.document_storage_probe',
        result_name='document-storage-result.json', family='iPhone', increase_contrast=False,
        duoctl=None, pose=None, keyboard_intro=None, runtime_id=None):
    output.mkdir(parents=True, exist_ok=True)
    client = AppleSimulators(env)
    inventory = client.devices()['devices']
    runtime, model = simulator_selection(inventory, family, runtime_id)
    name = 'Build Manager Focused QA ' + str(time.time_ns())
    device = client.create(name, model, runtime)
    (output / 'ios-lease.json').write_text(json.dumps(dict(device=device, name=name, runtime=runtime, model=model)))
    cache = console = console_stream = None
    initial_progress_pid = None
    try:
        client.boot(device)
        if entry_point.endswith(('.document_creation_probe', '.lockscreen_probe')):
            # Dismiss only the fresh QA simulator's first-use keyboard lesson.
            client.invoke('spawn', device, 'defaults', 'write', 'com.apple.keyboard.preferences',
                          'DidShowContinuousPathIntroduction', '-bool', 'true')
        if pose is not None:
            if duoctl is None:
                raise ValueError('Duo pose matrix requires --duoctl with the reviewed simulator helper.')
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
        client.invoke('install', device, str(app), timeout=180)
        cache = Path(client.invoke('get_app_container', device, bundle, 'data')) / 'Library/Caches'
        drive_folds = duoctl is not None and family == 'iPhone Duo' and entry_point.endswith('.reader_title_probe')
        creation_folds = (duoctl is not None and pose == 'partial'
                          and entry_point.endswith('.document_creation_probe'))
        if drive_folds or creation_folds:
            (cache / 'drive-folds').touch()
        if entry_point.endswith('.notes_library_probe'):
            (cache / 'notes-keyboard').touch()
        # duoctl rejects non-Duo models even when passed an explicit UUID.
        drive_notes = (duoctl is not None and family == 'iPhone Duo'
                       and entry_point.endswith(('.notes_drawers_probe', '.notes_header_probe', '.notebook_link_probe', '.notebook_native_pen_probe')))
        if drive_notes:
            (cache / 'drive-notes-touches').touch()
            if entry_point.endswith('.notebook_link_probe'):
                (cache / 'drive-link-touches').touch()
        if family == 'iPhone Duo' and pose == 'partial' and entry_point.endswith('.notes_library_probe'):
            (cache / 'notes-laptop-keyboard').touch()
        console_stream = (output / 'ios-console.log').open('w')
        console = subprocess.Popen(['xcrun', 'simctl', 'launch', '--console-pty', device, bundle],
            env=env, stdout=console_stream, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + (1800 if result_name == 'logistics-native-ui-result.json' else 600 if entry_point.endswith(('.notes_drawers_probe', '.links_images_voices_probe', '.folder_feedback_probe')) else 600 if entry_point in (UNIFIED_PROGRESS_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY) else 240)
        next_progress = 0
        while time.monotonic() < deadline:
            background_request = cache / 'file-transfer-background'
            if entry_point.endswith(('.file_transfer_probe', '.drawer_privacy_probe')) and background_request.exists():
                background_request.unlink()
                client.invoke('launch', device, 'com.apple.Preferences')
                time.sleep(1)
                client.invoke('launch', device, bundle)
            request = cache / 'notes-touch-request.json'
            if drive_notes and request.exists():
                touch = json.loads(request.read_text())
                action = touch.get('action', 'swipe')
                if action == 'capture-menu':
                    arguments = ['screenshot', str(output / 'notes-native-menu.png')]
                elif action == 'tap':
                    arguments = ['tap', *map(str, touch['points'])]
                elif action in ('swipe', 'long-press'):
                    arguments = [action, *map(str, touch['points']), '--duration', '.7' if action == 'long-press' else '.25']
                else:
                    raise ValueError('Unexpected Notes touch action')
                result = subprocess.run([sys.executable, str(duoctl), '-d', device, *arguments],
                                        timeout=60, env=env, capture_output=True)
                if result.returncode:
                    raise RuntimeError(result.stderr.decode(errors='replace')[-2000:])
                request.unlink()
                (cache / 'notes-touch-done').touch()
            if result_name == 'logistics-native-ui-result.json' and time.monotonic() >= next_progress:
                next_progress = time.monotonic() + 30
                timings = cache / 'logistics-native-ui-timings.json'
                if timings.exists():
                    value = json.loads(timings.read_text())
                    summary = value['summary']
                    checkpoints = summary['checkpoints']
                    print(json.dumps(dict(native_elapsed_s=round(summary['elapsed_s'], 1),
                        last_case=checkpoints[-1]['case'] if checkpoints else None,
                        active=[row['name'] for row in value['records'] if row['status'] == 'running'])), flush=True)
            if drive_folds or creation_folds:
                folder = 'document-creation-evidence' if creation_folds else 'viewer-layout'
                request = cache / folder / 'fold-request.json'
                done = request.with_name('fold-done.json')
                if request.exists() and not done.exists():
                    change = json.loads(request.read_text())
                    subprocess.run([sys.executable, str(duoctl), '-d', device, 'hinge', str(change['angle'])],
                        timeout=60, env=env, check=True, capture_output=True)
                    pending = done.with_suffix('.tmp')
                    pending.write_text(json.dumps(change))
                    pending.replace(done)
            keyboard_capture = cache / 'viewer-layout/keyboard-capture-request'
            if keyboard_capture.exists():
                if keyboard_intro is not None:
                    client.invoke('io', device, 'screenshot', str(output / 'keyboard-introduction.png'))
                    subprocess.run([sys.executable, str(duoctl), '-d', device, 'tap', *map(str, keyboard_intro)],
                                   env=env, timeout=60, check=True, capture_output=True)
                    keyboard_intro = None
                    time.sleep(.5)
                client.invoke('io', device, 'screenshot', str(output / 'duo-keyboard-screen.png'))
                keyboard_capture.unlink()
                (cache / 'viewer-layout/keyboard-capture-done').touch()
            request = cache / 'lockscreen-capture.json'
            if entry_point.endswith('.lockscreen_probe') and request.exists():
                capture_name = lockscreen_capture_name(request.read_bytes())
                if capture_name is None:
                    time.sleep(.1)
                    continue
                client.invoke('io', device, 'screenshot', str(output / ('screen-' + capture_name + '.png')))
                request.unlink()
                (cache / 'lockscreen-capture-done').touch()
            report = cache / result_name
            capture = cache / 'unified-progress-capture.json'
            if entry_point == UNIFIED_PROGRESS_ENTRY and capture.exists():
                capture_name = json.loads(capture.read_text()).get('name')
                if not isinstance(capture_name, str) or not re.fullmatch(
                        r'progress-(?:fixture-epub(?:-home)?|secret-passage-epub)-(?:before|after)', capture_name):
                    raise ValueError('Unexpected progress screenshot name')
                # A visible DOM range can precede the separate WebKit render
                # process drawing the frame into the simulated display.
                capture.unlink()
                time.sleep(.5)
                client.invoke('io', device, 'screenshot', str(output / (capture_name + '.png')), timeout=40)
                (cache / (capture_name + '.captured')).touch()
            if entry_point.endswith('.document_creation_probe'):
                request = cache / 'document-creation-evidence/keyboard-request.json'
                if request.exists():
                    pose = json.loads(request.read_text())['pose']
                    if pose not in ('portrait', 'landscape-left', 'landscape-right'):
                        raise ValueError('Unexpected creation keyboard pose')
                    client.invoke('io', device, 'screenshot', str(output / f'keyboard-{pose}.png'))
                    request.unlink()
                    request.with_name('keyboard-done').touch()
            if report.exists():
                result = json.loads(report.read_text())
                if entry_point.endswith('.drawer_privacy_probe') and result.get('phase') not in ('complete', 'failed'):
                    time.sleep(.1)
                    continue
                if entry_point.endswith('.lockscreen_probe') and result.get('phase') not in ('complete', 'failed'):
                    time.sleep(.2)
                    continue
                checkpoint = (entry_point in (UNIFIED_PROGRESS_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY)
                              and initial_progress_pid is None and result.get('success') and result.get('phase') == 'checkpoint')
                if not checkpoint:
                    (output / 'ios-result.json').write_text(json.dumps(result, indent=2))
                screenshot = 'ios-before-restart.png' if checkpoint else 'ios-final.png'
                client.invoke('io', device, 'screenshot', str(output / screenshot))
                if not result['success']:
                    raise RuntimeError(result.get('error') or result.get('errors') or 'Native layout assertions failed')
                if entry_point in (UNIFIED_PROGRESS_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY):
                    expected_scope = env.get('SIMCTL_CHILD_LOGISTICS_PROGRESS_CASE')
                    if expected_scope and result.get('scope') != expected_scope:
                        raise ValueError('Native progress probe ran a different case scope.')
                    pid = check_progress_report(result, initial_progress_pid)
                    if initial_progress_pid is None:
                        initial_progress_pid = pid
                        shutil.copyfile(report, output / 'ios-progress-before-restart.json')
                        report.unlink()
                        client.invoke('terminate', device, bundle, timeout=20)
                        # Keep the original launch log and a separate console
                        # receipt for exceptions raised during restart.
                        console.wait(timeout=20)
                        console_stream.close()
                        console_stream = (output / 'ios-restart-console.log').open('w')
                        console = subprocess.Popen(
                            ['xcrun', 'simctl', 'launch', '--console-pty', device, bundle],
                            env=env, stdout=console_stream, stderr=subprocess.STDOUT)
                        deadline = time.monotonic() + 600
                        continue
                if result_name == 'notebook-result.json':
                    result = notebook_lifecycle(
                        lambda name: (cache / name).read_bytes() if (cache / name).exists() else None,
                        lambda name, data: (cache / name).write_bytes(data),
                        lambda: client.invoke('launch', device, 'com.apple.Preferences'),
                        lambda: client.invoke('launch', device, bundle),
                        lambda: client.invoke('terminate', device, bundle))
                    (output / 'ios-result.json').write_text(json.dumps(result, indent=2))
                return result
            # A failed simctl launch cannot later produce an app result. Keep
            # result handling first: an app may finish before console teardown.
            # Exit0 can mean a detached console and is not itself acceptance.
            exit_code = console.poll()
            if exit_code not in (None, 0):
                failure = dict(stage='simctl-launch-before-result', exit_code=exit_code,
                               device=device, bundle=bundle, console_log='ios-console.log')
                try:
                    (output / 'ios-launch-failure.json').write_text(json.dumps(failure, indent=2))
                except OSError:
                    pass  # Optional evidence must not replace the launch error.
                raise RuntimeError('simctl launch console exited with status '
                                   + str(exit_code) + ' before the probe result; see '
                                   + str(output / 'ios-console.log'))
            time.sleep(.3)
        raise TimeoutError('iOS focused QA probe timed out')
    finally:
        try:
            if cache is not None:
                for artifact_name in diagnostics(entry_point):
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
            if cache is not None and (cache / 'editor-keyboard-evidence').is_dir():
                shutil.copytree(cache / 'editor-keyboard-evidence', output / 'editor-keyboard-evidence', dirs_exist_ok=True)
            if cache is not None and (cache / result_name).exists():
                shutil.copyfile(cache / result_name, output / 'ios-result.json')
        finally:
            cleanup_ios_probe(client, device, name, bundle, output,
                              installed=cache is not None, console=console, console_stream=console_stream)


def cleanup_ios_probe(client, device, name, bundle, output, *, installed=False,
                      console=None, console_stream=None):
    """Always remove the leased simulator, including after failed boot/termination."""
    if client.matching(device, name) is None:
        (output / 'ios-cleanup.json').write_text(json.dumps(dict(device=device, removed=True)))
        return
    errors = []
    try:
        if installed:
            try:
                client.invoke('terminate', device, bundle, timeout=10)
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                errors.append(type(error).__name__ + ': terminate')
        if console is not None:
            try:
                console.wait(timeout=10)
            except subprocess.TimeoutExpired:
                console.terminate()
        if console_stream is not None:
            console_stream.close()
        if installed:
            try:
                client.invoke('uninstall', device, bundle, timeout=10)
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                errors.append(type(error).__name__ + ': uninstall')
    finally:
        client.remove(device, name)
        (output / 'ios-cleanup.json').write_text(json.dumps(dict(device=device,
            removed=client.matching(device, name) is None, app_cleanup_errors=errors)))


def prepare_chat_notes_emulator(emulator, serial, output):
    """Keep unrelated Bluetooth first-boot crashes outside these UI scenarios."""
    emulator.invoke('-s', serial, 'shell', 'svc', 'bluetooth', 'disable')
    deadline = time.monotonic() + 10
    while emulator.invoke('-s', serial, 'shell', 'settings', 'get', 'global', 'bluetooth_on') != '0':
        if time.monotonic() >= deadline:
            raise RuntimeError('The disposable Chat/Notes emulator could not disable Bluetooth.')
        time.sleep(.2)
    windows = emulator.invoke('-s', serial, 'shell', 'dumpsys', 'window', 'windows')
    dismissed = any('mCurrentFocus' in line and 'bluetooth' in line.lower() for line in windows.splitlines())
    if dismissed:
        emulator.invoke('-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_BACK')
    (output / 'android-environment.json').write_text(json.dumps(dict(
        bluetooth_disabled=True, bluetooth_dialog_dismissed=dismissed), indent=2))


def run_android(workspace, payload, output, env, options, *, bundle=BUNDLE,
                entry_point='tests.logisticsmobile.document_storage_probe',
                result_name='document-storage-result.json', device=None, tablet=False, reuse_project=False,
                observe=None, probe_timeout=None):
    if bundle not in QA_BUNDLES:
        raise ValueError('Use an isolated QA bundle; the main app is not a probe target.')
    if entry_point in (UNIFIED_PROGRESS_ANDROID_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY) and device is not None:
        raise ValueError('Unified progress restart acceptance requires an owned emulator.')
    if probe_timeout is not None and (type(probe_timeout) is not int or not 1 <= probe_timeout <= 3600):
        raise ValueError('Probe timeout must be 1 to 3600 seconds.')
    memory_probe = entry_point.endswith(('.notebook_memory_probe', '.notebook_soak_probe', '.notebook_load_probe'))
    project = workspace / 'build/logisticsmobile/android/gradle'
    if reuse_project:
        if not (workspace / '.manager-scratch').is_file() or not project.is_dir():
            raise ValueError('Reuse requires the original manager-owned scratch project.')
    else:
        template = REPO / 'mobile_build/build/logisticsmobile/android/gradle'
        if template.is_dir():
            shutil.copytree(template, project, ignore=shutil.ignore_patterns('build', '.gradle', '__pycache__'))
        else:
            from mobile_build.deployment.deployment_paths import prepare_workspace
            prepare_workspace(SOURCE / 'mobile_build')
            command([sys.executable, '-m', 'briefcase', 'create', 'android', '--no-input'],
                    output / 'android-create.log', cwd=workspace, env=env)
        android()
    copy_payload(payload, project / 'app/src/main/python', entry_point=entry_point, android=True)
    gradle = project / 'app/build.gradle'
    gradle.write_text(re.sub(r'applicationId "[^"]+"', 'applicationId "' + bundle + '"', gradle.read_text()))
    manifest = project / 'app/src/main/AndroidManifest.xml'
    manifest.write_text(manifest.read_text().replace('io.github.ispaure.logisticsmobile', bundle))
    if entry_point.endswith('.notebook_input_probe') or memory_probe:
        with gradle.open('a') as stream:
            stream.write('\nandroid.sourceSets.main.java.srcDir(' + json.dumps(str(REPO / 'mobile_build/native_tests/android/notebooks')) + ')\n')
    raw_ink = entry_point.endswith('.boox_raw_ink_probe')
    if raw_ink:
        with gradle.open('a') as stream:
            stream.write('\nandroid.sourceSets.main.java.srcDir(' + json.dumps(str(REPO / 'mobile_build/native_tests/android/boox_raw')) + ')\n')
            stream.write('dependencies { implementation("com.onyx.android.sdk:onyxsdk-pen:1.5.8") { exclude group: "com.android.support" } }\n')
            stream.write('android { packagingOptions { pickFirst "lib/*/libc++_shared.so" } }\n')
        with (project / 'gradle.properties').open('a') as stream:
            stream.write('\nandroid.enableJetifier=true\n')
    command([project / 'gradlew', *([] if raw_ink else ['--offline']), '--no-daemon', 'assembleDebug'], output / 'android-build.log', cwd=project, env=env)
    return exercise_android_app(project / 'app/build/outputs/apk/debug/app-debug.apk',
        workspace, output, env, options, bundle=bundle, entry_point=entry_point,
        result_name=result_name, device=device, tablet=tablet, reuse_project=reuse_project,
        observe=observe, probe_timeout=probe_timeout)


def exercise_android_app(apk, workspace, output, env, options, *, bundle=BUNDLE,
        entry_point='tests.logisticsmobile.document_storage_probe',
        result_name='document-storage-result.json', device=None, tablet=False, startup_timeout=600, install_timeout=180, reuse_project=False,
        observe=None, probe_timeout=None):
    """Run a verified QA APK on an owned device, independently of its build phase."""
    from hashlib import file_digest
    from mobile_build.deployment.android_deploy import build_tools
    if bundle not in QA_BUNDLES:
        raise ValueError('Use an isolated QA bundle; the main app is not a probe target.')
    if probe_timeout is not None and (type(probe_timeout) is not int or not 1 <= probe_timeout <= 3600):
        raise ValueError('Probe timeout must be 1 to 3600 seconds.')
    output.mkdir(parents=True, exist_ok=True)
    metadata = subprocess.check_output([str(build_tools(env) / 'aapt2'), 'dump', 'badging', str(apk)],
                                      env=env, text=True, timeout=30)
    identity = re.search(r"package: name='([^']+)'", metadata)
    if identity is None or identity[1] != bundle or 'application-debuggable' not in metadata.splitlines():
        raise ValueError('The APK must be a Debug build of the selected isolated QA package.')
    with Path(apk).open('rb') as stream:
        digest = file_digest(stream, 'sha256').hexdigest()
    (output / 'android-apk.json').write_text(json.dumps(dict(apk=str(apk),
        sha256=digest, bundle=bundle, startup_timeout=startup_timeout, install_timeout=install_timeout)))
    memory_probe = entry_point.endswith(('.notebook_memory_probe', '.notebook_soak_probe', '.notebook_load_probe'))
    raw_ink = entry_point.endswith('.boox_raw_ink_probe')
    hands_on = entry_point.endswith('.boox_preview_probe')
    emulator_workspace = workspace / ('emulator-' + str(time.time_ns()) if reuse_project else 'emulator')
    # Keep the published manager pin compatible while local reviewed backends
    # expose additional probe controls. The lease records the actual selection.
    import inspect
    emulator_options = dict(environment=env)
    parameters = inspect.signature(AndroidEmulator).parameters
    for key, value in (('startup_timeout', startup_timeout), ('gpu', 'swiftshader')):
        if key in parameters:
            emulator_options[key] = value
    emulator = AndroidEmulator(options['tools.android_sdk'], emulator_workspace, **emulator_options)
    record = None
    try:
        if device is not None:
            if emulator.invoke('-s', device, 'get-state').strip() != 'device':
                raise RuntimeError('The selected Android device is unavailable.')
            record = dict(serial=device)
        else:
            record = emulator.start(options['android.image'], options['android.model'])
        serial = record['serial']
        if observe is not None:
            observe('ready', emulator, record, output)
        if device is None and not tablet and entry_point.endswith('.android_header_probe'):
            emulator.invoke('-s', serial, 'shell', 'wm', 'size', '720x1600')
            emulator.invoke('-s', serial, 'shell', 'wm', 'density', '320')
        if device is None and entry_point.endswith(('.document_creation_probe', '.lockscreen_probe')):
            emulator.invoke('-s', serial, 'shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '1')
        if tablet:
            emulator.invoke('-s', serial, 'shell', 'wm', 'size', '1600x2400')
            emulator.invoke('-s', serial, 'shell', 'wm', 'density', '320')
        if device is None and entry_point.endswith('.sync_status_probe'):
            emulator.invoke('-s', serial, 'shell', 'wm', 'size', '640x1136')
            emulator.invoke('-s', serial, 'shell', 'wm', 'density', '320')
        if device is None and entry_point.endswith('.lockscreen_probe'):
            # A fresh Pixel Launcher's first-boot ANR can steal the QA window's
            # input focus. Stop only that unrelated launcher on our disposable
            # emulator before installing the foreground form; retain app errors.
            emulator.invoke('-s', serial, 'shell', 'am', 'force-stop', 'com.google.android.apps.nexuslauncher')
            emulator.invoke('-s', serial, 'shell', 'wm', 'size', '720x1600')
            emulator.invoke('-s', serial, 'shell', 'wm', 'density', '320')
        emulator.invoke('-s', serial, 'install', str(apk), timeout=install_timeout)
        if device is not None:
            # Boox's launcher can auto-freeze a newly installed QA identity.
            # Only this disposable package is enabled, then removed in finally.
            time.sleep(2)
            emulator.invoke('-s', serial, 'shell', 'pm', 'enable', bundle)
        if device is None and entry_point.endswith('.chat_notes_feedback_probe'):
            prepare_chat_notes_emulator(emulator, serial, output)
        if observe is not None:
            observe('installed', emulator, record, output)
        emulator.invoke('-s', serial, 'shell', 'am', 'start', '-n', bundle + '/org.beeware.android.MainActivity')
        deadline = time.monotonic() + (probe_timeout if probe_timeout is not None else 2400 if hands_on or result_name == 'logistics-native-ui-result.json' else 900 if raw_ink or memory_probe else 600 if entry_point.endswith(('.lockscreen_probe', '.notes_drawers_probe', '.links_images_voices_probe', '.folder_feedback_probe', '.documentation_header_probe', '.android_header_probe')) else 240)
        last_stage = last_orientation = initial_progress_pid = None
        while time.monotonic() < deadline:
            if observe is not None:
                observe('poll', emulator, record, output)
            if entry_point.endswith(('.documentation_header_probe', '.android_header_probe')):
                capture = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                    'cat', 'cache/header-capture.json'], env=env, capture_output=True, timeout=15)
                try:
                    request = json.loads(capture.stdout) if capture.returncode == 0 else {}
                except (ValueError, UnicodeError):
                    request = {}  # Retry a marker observed during its write.
                name = request.get('name') if isinstance(request, dict) else None
                if name is not None:
                    if not isinstance(name, str) or not re.fullmatch(r'(?:help|notes)-[a-z-]+', name):
                        raise ValueError('Unexpected header screenshot name')
                    screen = subprocess.check_output([str(emulator.adb), '-s', serial,
                        'exec-out', 'screencap', '-p'], env=env, timeout=45)
                    if not screen.startswith(b'\x89PNG'):
                        raise RuntimeError('Android header screenshot was not a PNG')
                    directory = output / 'cache/viewer-layout'
                    directory.mkdir(parents=True, exist_ok=True)
                    (directory / (name + '.png')).write_bytes(screen)
                    emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'rm', 'cache/header-capture.json')
                    emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'touch', 'cache/header-capture-done')
            if tablet or (device is None and entry_point.endswith(('.workspace_edges_probe', '.document_creation_probe', '.documentation_header_probe', '.android_header_probe', '.lockscreen_probe', '.chat_settings_probe', '.notes_search_probe', '.chat_notes_feedback_probe'))):
                result = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                    'cat', 'cache/creation-orientation'], env=env, capture_output=True, timeout=15)
                pose = result.stdout.strip()
                if result.returncode == 0 and pose in (b'portrait', b'landscape-left', b'landscape-right') and pose != last_orientation:
                    emulator.invoke('-s', serial, 'shell', 'wm', 'user-rotation', 'lock',
                                    {b'landscape-left': '1', b'landscape-right': '3', b'portrait': '0'}[pose])
                    last_orientation = pose
            if entry_point.endswith('.lockscreen_probe'):
                request = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                    'cat', 'cache/lockscreen-capture.json'], env=env, capture_output=True, timeout=15)
                capture_name = lockscreen_capture_name(request.stdout) if request.returncode == 0 else None
                if capture_name is not None:
                    screen = subprocess.check_output([str(emulator.adb), '-s', serial, 'exec-out', 'screencap', '-p'], env=env, timeout=15)
                    (output / ('screen-' + capture_name + '.png')).write_bytes(screen)
                    emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'rm', 'cache/lockscreen-capture.json')
                    emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'touch', 'cache/lockscreen-capture-done')
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
            if entry_point.endswith('.document_creation_probe'):
                request = 'cache/document-creation-evidence/keyboard-request.json'
                pending = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'run-as', bundle,
                    'cat', request], env=env, capture_output=True, timeout=15)
                try:
                    keyboard_request = json.loads(pending.stdout) if pending.returncode == 0 else None
                except json.JSONDecodeError:
                    keyboard_request = None
                if keyboard_request is not None:
                    pose = keyboard_request['pose']
                    if pose not in ('portrait', 'landscape-left', 'landscape-right'):
                        raise ValueError('Unexpected creation keyboard pose')
                    screen = subprocess.run([str(emulator.adb), '-s', serial, 'exec-out', 'screencap', '-p'],
                        env=env, capture_output=True, check=True, timeout=15)
                    (output / f'keyboard-{pose}.png').write_bytes(screen.stdout)
                    emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'rm', request)
                    emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'touch',
                                    'cache/document-creation-evidence/keyboard-done')
            if value.returncode == 0:
                try:
                    result = json.loads(value.stdout)
                except json.JSONDecodeError:
                    time.sleep(.1)
                    continue
                if entry_point.endswith('.lockscreen_probe') and result.get('phase') not in ('complete', 'failed'):
                    time.sleep(.2)
                    continue
                (output / 'android-result.json').write_text(json.dumps(result, indent=2))
                if observe is not None:
                    observe('result', emulator, record, output)
                if not result['success']:
                    raise RuntimeError(result.get('error') or result.get('errors') or 'Native layout assertions failed')
                if entry_point in (UNIFIED_PROGRESS_ANDROID_ENTRY, UNIFIED_PROGRESS_VIDEO_ENTRY):
                    pid = check_progress_report(result, initial_progress_pid)
                    if initial_progress_pid is None:
                        initial_progress_pid = pid
                        (output / 'android-progress-before-restart.json').write_text(json.dumps(result, indent=2))
                        emulator.invoke('-s', serial, 'shell', 'am', 'force-stop', bundle)
                        emulator.invoke('-s', serial, 'shell', 'run-as', bundle, 'rm', 'cache/' + result_name)
                        emulator.invoke('-s', serial, 'shell', 'am', 'start', '-n', bundle + '/org.beeware.android.MainActivity')
                        deadline = time.monotonic() + (probe_timeout or 240)
                        continue
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
    except BaseException:
        import traceback
        (output / 'android-run-error.txt').write_text(traceback.format_exc())
        raise
    finally:
        try:
            if record is not None:
                if entry_point.endswith(('.dataview_probe', '.viewer_layout_probe', '.control_center_probe', '.rclone_transfer_probe', '.notes_library_probe', '.notes_audit_probe', '.notes_markdown_feedback_probe', '.documentation_header_probe', '.android_header_probe')):
                    import io
                    import tarfile
                    archive = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                        'run-as', bundle, 'tar', '-cf', '-', 'cache/viewer-layout'],
                        env=env, capture_output=True, timeout=45)
                    if archive.returncode == 0:
                        try:
                            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as evidence:
                                evidence.extractall(output, filter='data')
                        except (tarfile.TarError, EOFError):
                            # A startup failure can leave no evidence directory;
                            # Android's shell may still return status zero. Keep
                            # the original run failure and continue cleanup.
                            (output / 'android-evidence-archive-error.txt').write_text(
                                archive.stdout[:4096].decode(errors='replace'))
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
                    try:
                        json.loads(report_data.stdout)
                    except (ValueError, UnicodeDecodeError):
                        (output / 'android-result-read-error.txt').write_bytes(report_data.stdout)
                    else:
                        (output / 'android-result.json').write_bytes(report_data.stdout)
                for name in diagnostics(entry_point):
                    artifact = subprocess.run([str(emulator.adb), '-s', record['serial'], 'exec-out',
                        'run-as', bundle, 'cat', 'cache/' + name], env=env, capture_output=True, timeout=15)
                    if (artifact.returncode == 0 and not artifact.stdout.startswith((b'cat:', b'run-as:'))
                            and (not name.endswith('.png') or artifact.stdout.startswith(b'\x89PNG'))):
                        (output / name).write_bytes(artifact.stdout)
                (output / 'android-logcat.txt').write_text(emulator.invoke('-s', record['serial'], 'logcat', '-d', '-t', '2000'))
                try:
                    (output / 'android-exit-info.txt').write_text(emulator.invoke(
                        '-s', record['serial'], 'shell', 'dumpsys', 'activity', 'exit-info', bundle))
                except RuntimeError:
                    pass
        finally:
            boot_log = emulator.workspace / 'emulator.log'
            try:
                if boot_log.is_file():
                    shutil.copyfile(boot_log, output / 'android-emulator.log')
            except OSError:
                pass  # Evidence failure must not prevent owned cleanup.
            try:
                if record is not None:
                    installed = emulator.invoke('-s', record['serial'], 'shell', 'pm', 'list', 'packages', bundle)
                    if 'package:' + bundle in installed.splitlines():
                        emulator.invoke('-s', record['serial'], 'uninstall', bundle)
                    if device is not None:
                        remaining = emulator.invoke('-s', device, 'shell', 'pm', 'list', 'packages', 'logistics')
                        (output / 'remaining-packages.txt').write_text(remaining)
            finally:
                # An app install/uninstall error must not bypass owned-device cleanup.
                emulator.cleanup()
                for name in ('emulator.log', 'removed-lease.json'):
                    evidence = emulator.workspace / name
                    if evidence.is_file():
                        shutil.copyfile(evidence, output / ('android-' + name))
                completed_lease = emulator.workspace / 'removed-lease.json'
                if completed_lease.is_file():
                    shutil.copyfile(completed_lease, output / 'android-emulator-lease.json')
                (output / 'android-cleanup.json').write_text(json.dumps(dict(removed=not emulator.marker.exists())))


def main():
    global SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('ios', 'android'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=REPO,
                        help='Validate a manager-owned source snapshot using this checkout’s native templates.')
    parser.add_argument('--probe', choices=('workspace-edges', 'mobile-feedback', 'documents-search', 'documents-hub', 'file-transfer', 'notes-dataview', 'notes-audit', 'notes-library', 'rclone-transfer', 'markdown-typography', 'chat-laptop', 'chat-settings', 'notes-search', 'chat-notes-feedback', 'notebook-laptop', 'editor-keyboard', 'storage', 'reader-space', 'viewer-layout', 'reader-title', 'unified-progress', 'unified-progress-video', 'recent-deletion', 'notebook', 'documents', 'localcrypt', 'workspace-move', 'notes-folders', 'folder-feedback', 'notes-markdown-feedback', 'links-images-voices', 'speech-playback', 'native-suite', 'first-tap', 'storage-selector', 'notes-fullscreen', 'notes-drawers', 'notes-header', 'documentation-header', 'android-header', 'sync-status', 'control-center', 'creation', 'features', 'pdf-annotation', 'notebook-input', 'notebook-memory', 'notebook-soak', 'notebook-load', 'boox-raw-ink', 'boox-preview'), default='storage')
    parser.add_argument('--retain-build', action='store_true', help='Pin this managed QA build for reruns; caller must remove the pin and workspace afterward.')
    parser.add_argument('--device', help='Explicit connected Android serial; QA app is removed afterward')
    parser.add_argument('--family', choices=('iPhone', 'iPhone 17e', 'iPad', 'iPhone Duo', 'all'), default='iPhone')
    parser.add_argument('--ios-runtime', help='Explicit installed CoreSimulator runtime identifier for a disposable iOS probe.')
    parser.add_argument('--external-subtitle-only', action='store_true',
                        help='With iOS unified-progress, run only the external subtitle restart case.')
    parser.add_argument('--ios-app', type=Path, help='Reuse a managed simulator shell only when native video source bytes match')
    parser.add_argument('--pose', choices=('closed', 'open', 'partial'), help='Explicit Duo simulator posture')
    parser.add_argument('--duoctl', type=Path, help='Reviewed external simulator-only Duo pose helper')
    parser.add_argument('--increase-contrast', action='store_true')
    parser.add_argument('--android-tablet', action='store_true', help='Use a tablet viewport on the disposable Android emulator.')
    args = parser.parse_args()
    if args.external_subtitle_only and (args.platform != 'ios' or args.probe != 'unified-progress'):
        parser.error('--external-subtitle-only requires the iOS unified-progress probe.')
    if args.probe in ('unified-progress', 'unified-progress-video') and args.device:
        parser.error('Unified progress acceptance requires a disposable device.')
    if args.ios_runtime and args.platform != 'ios':
        parser.error('--ios-runtime requires iOS.')
    if args.probe == 'android-header' and args.platform != 'android':
        parser.error('The android-header probe requires Android.')
    if args.android_tablet and (args.platform != 'android' or args.device):
        parser.error('--android-tablet requires the disposable Android emulator.')
    if args.pose and (args.platform != 'ios' or args.family != 'iPhone Duo'):
        parser.error('--pose requires an iOS iPhone Duo run')
    if args.probe == 'mobile-feedback' and args.device:
        parser.error('Mobile feedback acceptance uses disposable devices; omit --device.')
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
    if args.probe == 'markdown-typography' and args.platform != 'ios':
        parser.error('The Markdown typography probe measures UIKit fonts and requires iOS.')
    if args.probe == 'file-transfer' and args.platform != 'ios':
        parser.error('The file-transfer probe measures the shared UIKit idle policy and requires iOS.')
    SOURCE = args.source_root.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    options, _ = manager_settings.settings(REPO / 'mobile_build')
    env = dict(os.environ, DEVELOPER_DIR=options['tools.xcode'], ANDROID_HOME=options['tools.android_sdk'],
               ANDROID_SDK_ROOT=options['tools.android_sdk'], JAVA_HOME=options['tools.java'])
    env['PATH'] = os.pathsep.join((str(Path(sys.executable).parent),
        str(REPO / 'mobile_build/.tools/go/bin'), env['PATH']))
    env.pop('SIMCTL_CHILD_LOGISTICS_PROGRESS_CASE', None)
    if args.external_subtitle_only:
        env['SIMCTL_CHILD_LOGISTICS_PROGRESS_CASE'] = 'external-subtitle'
    os.environ.update(env)
    with scratch(REPO) as workspace:
        if args.retain_build:
            (workspace / '.keep').touch()
            (args.output / 'retained-build.json').write_text(json.dumps(dict(workspace=str(workspace))))
        os.environ['LOGISTICS_DEPLOY_WORKSPACE'] = str(workspace)
        env['LOGISTICS_DEPLOY_WORKSPACE'] = str(workspace)
        env['XDG_CACHE_HOME'] = str(workspace / 'probe-tools')
        env['GOCACHE'] = str(workspace / 'go-cache')
        os.environ['GOCACHE'] = env['GOCACHE']
        shutil.copyfile(SOURCE / 'mobile_build/pyproject.toml', workspace / 'pyproject.toml')
        payload = workspace / 'payload'
        # stage() verifies the manager fingerprint before and after a focused
        # development snapshot. Other out-of-tree probes retain their policy.
        captured_progress = (args.probe in ('unified-progress', 'unified-progress-video')
                             and (SOURCE / '.manager-source.json').is_file())
        manifest = stage(SOURCE, payload, allow_dirty=SOURCE == REPO or captured_progress)
        (args.output / 'source.json').write_text(json.dumps(manifest, indent=2))
        creation_profile = dict(bundle='io.github.ispaure.logisticscreationqa',
            entry_point='tests.logisticsmobile.document_creation_probe',
            result_name='document-creation-evidence/result.json') if args.probe == 'creation' else {}
        if args.probe == 'workspace-edges':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.workspace_edges_probe', result_name='workspace-edges-result.json')
        if args.probe == 'android-header':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.android_header_probe', result_name='android-header-result.json')
        if args.probe == 'documentation-header':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.documentation_header_probe', result_name='documentation-header-result.json')
        if args.probe == 'mobile-feedback':
            creation_profile = dict(bundle=BUNDLE, entry_point='tests.logisticsmobile.mobile_feedback_probe',
                                    result_name='mobile-feedback-result.json')
        if args.probe == 'notes-audit':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotesauditqa',
                entry_point='tests.logisticsmobile.notes_audit_probe', result_name='notes-audit-result.json')
        if args.probe == 'documents-search':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.documents_search_probe', result_name='documents-search-result.json')
        if args.probe == 'documents-hub':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.documents_hub_probe', result_name='documents-hub-result.json')
        if args.probe == 'notes-library':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.notes_library_probe', result_name='notes-library-result.json')
        if args.probe == 'file-transfer':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.file_transfer_probe', result_name='file-transfer-result.json')
        if args.probe == 'notes-dataview':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.dataview_probe', result_name='dataview-result.json')
        if args.probe == 'rclone-transfer':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.rclone_transfer_probe', result_name='rclone-transfer-result.json')
        if args.probe == 'markdown-typography':
            creation_profile = dict(entry_point='tests.logisticsmobile.markdown_typography_probe',
                result_name='markdown-typography-result.json')
        if args.probe == 'unified-progress':
            entry = UNIFIED_PROGRESS_ENTRY if args.platform == 'ios' else UNIFIED_PROGRESS_ANDROID_ENTRY
            creation_profile = dict(bundle=UNIFIED_PROGRESS_BUNDLE, entry_point=entry,
                                    result_name=UNIFIED_PROGRESS_RESULT)
        if args.probe == 'unified-progress-video':
            creation_profile = dict(bundle=UNIFIED_PROGRESS_BUNDLE, entry_point=UNIFIED_PROGRESS_VIDEO_ENTRY,
                                    result_name=UNIFIED_PROGRESS_RESULT)
            if args.platform == 'android':
                creation_profile['probe_timeout'] = 480
        if args.probe == 'reader-space':
            creation_profile = dict(bundle='io.github.ispaure.logisticsreaderspaceqa',
                entry_point='tests.logisticsmobile.reader_space_probe', result_name='reader-space-result.json')
        if args.probe in ('viewer-layout', 'reader-title'):
            module = 'reader_title_probe' if args.probe == 'reader-title' else 'viewer_layout_probe'
            creation_profile = dict(bundle='io.github.ispaure.logisticsviewerlayoutqa',
                entry_point=f'tests.logisticsmobile.{module}', result_name='viewer-layout-result.json')
        if args.probe == 'features':
            creation_profile = dict(bundle='io.github.ispaure.logisticsfeaturesqa',
                entry_point='tests.logisticsmobile.features_probe', result_name='features-result.json')
        if args.probe == 'recent-deletion':
            creation_profile = dict(entry_point='tests.logisticsmobile.recent_deletion_probe',
                                    result_name='recent-deletion-result.json')
        if args.probe == 'pdf-annotation':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.pdf_annotation_probe', result_name='pdf-annotation-result.json')
        if args.probe == 'notes-search':
            creation_profile = dict(entry_point='tests.logisticsmobile.notes_search_probe',
                                    result_name='notes-search-result.json')
        if args.probe == 'chat-notes-feedback':
            creation_profile = dict(entry_point='tests.logisticsmobile.chat_notes_feedback_probe',
                                    result_name='chat-notes-feedback-result.json')
        if args.probe == 'chat-settings':
            creation_profile = dict(entry_point='tests.logisticsmobile.chat_settings_probe',
                                    result_name='chat-settings-result.json')
        if args.probe == 'chat-laptop':
            creation_profile = dict(entry_point='tests.logisticsmobile.chat_laptop_probe',
                                    result_name='chat-laptop-result.json')
        if args.probe == 'notebook-laptop':
            creation_profile = dict(entry_point='tests.logisticsmobile.notebook_laptop_probe',
                                    result_name='notebook-laptop-result.json')
        if args.probe == 'editor-keyboard':
            creation_profile = dict(entry_point='tests.logisticsmobile.editor_keyboard_probe',
                                    result_name='editor-keyboard-evidence/result.json')
        if args.probe == 'documents':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.document_workspace_probe', result_name='document-workspace-result.json')
        if args.probe == 'localcrypt':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.localcrypt_probe', result_name='localcrypt-result.json')
        if args.probe == 'workspace-move':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.workspace_move_probe', result_name='workspace-move-result.json')
        if args.probe == 'notes-markdown-feedback':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.notes_markdown_feedback_probe', result_name='notes-markdown-feedback-result.json')
        if args.probe == 'speech-playback':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.speech_playback_probe', result_name='speech-playback-result.json')
        if args.probe == 'links-images-voices':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.links_images_voices_probe', result_name='links-images-voices-result.json')
        if args.probe == 'notes-folders':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.notes_folders_probe', result_name='notes-folders-result.json')
        if args.probe == 'folder-feedback':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.folder_feedback_probe', result_name='folder-feedback-result.json')
        if args.probe == 'control-center':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.control_center_probe', result_name='control-center-result.json')
        if args.probe == 'sync-status':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.sync_status_probe', result_name='sync-status-result.json')
        if args.probe == 'notes-header':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.notes_header_probe', result_name='notes-header-result.json')
        if args.probe == 'notes-drawers':
            creation_profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.notes_drawers_probe', result_name='notes-drawers-result.json')
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
            run_ios(workspace, payload, args.output, env, family=args.family, increase_contrast=args.increase_contrast, duoctl=args.duoctl, source_app=args.ios_app, pose=args.pose, runtime_id=args.ios_runtime, **profile)
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
            run_android(workspace, payload, args.output, env, options, device=args.device, tablet=args.android_tablet, **profile)


if __name__ == '__main__':
    main()
