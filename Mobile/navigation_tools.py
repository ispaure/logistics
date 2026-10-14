"""External Android native lifecycle proof using only a disposable test-mode app.

Requires a booted emulator with the current test APK installed. Does not inspect
credentials or user documents. Size/density changes are reset in finally.
"""
import argparse
import json
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import time

BUNDLE = 'io.github.ispaure.logisticsmobile'
PROBE = 'cache/navigation-foundation-probe'


def android(adb, device, output):
    output.mkdir(parents=True, exist_ok=True)
    prefix = [str(adb), '-s', device]
    def run(*args, data=None, check=True):
        return subprocess.run([*prefix, *args], input=data, capture_output=True, check=check, timeout=30)
    def launch():
        run('shell', 'am', 'start', '-n', BUNDLE + '/org.beeware.android.MainActivity',
            '--es', 'org.beeware.ENVIRON', shlex.quote(json.dumps({'LOGISTICS_NAVIGATION_HOLD': '1'})))
    def wait(predicate, timeout=30):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            result = run('exec-out', 'run-as', BUNDLE, 'cat', PROBE + '/probe.json', check=False)
            try:
                last = json.loads(result.stdout)
            except (ValueError, UnicodeError):
                pass
            if last and predicate(last):
                return last
            time.sleep(.2)
        raise RuntimeError('Native lifecycle condition timed out; last state: ' + repr(last))
    sequence = 0
    def command(action, **values):
        nonlocal sequence
        sequence += 1
        payload = json.dumps(dict(sequence=sequence, action=action, **values)).encode()
        # Fixed fixture path; stdin carries data rather than shell interpolation.
        script = 'cat > ' + PROBE + '/control.tmp && mv ' + PROBE + '/control.tmp ' + PROBE + '/control.json'
        run('shell', 'run-as', BUNDLE, 'sh', '-c', "'" + script + "'", data=payload)
        return wait(lambda state: state['sequence'] == sequence)
    checks = []
    def record(name, state):
        checks.append({'case': name, 'state': state})
        (output / (name + '.png')).write_bytes(run('exec-out', 'screencap', '-p').stdout)
        print('NAVIGATION_LIFECYCLE_CASE=' + name, flush=True)
    try:
        run('shell', 'am', 'force-stop', BUNDLE)
        run('shell', 'run-as', BUNDLE, 'rm', '-rf', PROBE)
        run('shell', 'wm', 'size', 'reset')
        run('shell', 'wm', 'density', 'reset')
        launch()
        initial = wait(lambda state: state['width'] > 0 and 0 < state['content_height'] <= state['height'] - 48)
        record('phone', initial)
        changed = command('edit', text='Durable native navigation draft')
        assert changed['recovered_text'] == changed['text']
        record('draft', command('select', destination='documents'))
        command('focus')
        keyboard = wait(lambda state: state['content_height'] < initial['content_height'] - 100)
        assert keyboard['editor_bottom'] <= keyboard['visible_bottom']
        record('keyboard_insets', keyboard)
        command('blur')
        wait(lambda state: state['keyboard_inset'] == 0
             and state['content_height'] > keyboard['content_height'] + 100)
        record('settings', command('select', destination='settings'))
        command('select', destination='documents')
        run('shell', 'wm', 'size', '1860x2480')
        run('shell', 'wm', 'density', '300')
        tablet = wait(lambda state: state['width'] >= 600 and state['mode'] == 'rail')
        assert tablet['text'] == changed['text']
        record('android15_tablet', tablet)
        run('shell', 'wm', 'size', '2480x1860')
        rotated = wait(lambda state: state['width'] > state['height'] and state['mode'] == 'rail')
        record('tablet_landscape', rotated)
        before = wait(lambda state: state['width'] > state['height'] and state['mode'] == 'rail')
        command('recreate')
        recreated = wait(lambda state: state['boots'] > before['boots']
                         and state['activity'] != before['activity'] and state['pid'] == before['pid']
                         and state['width'] > 0 and state['height'] > 0 and state['mode'] == 'rail')
        assert recreated['pid'] == before['pid'] and recreated['activity'] != before['activity']
        assert recreated['text'] == changed['text'] and recreated['document_id'] == changed['document_id']
        record('activity_recreation', recreated)
        run('shell', 'am', 'force-stop', BUNDLE)
        launch()
        restored = wait(lambda state: state['boots'] > recreated['boots'] and state['pid'] != recreated['pid']
                       and state['width'] > 0 and state['height'] > 0)
        assert restored['pid'] != recreated['pid'] and restored['text'] == changed['text']
        record('process_restoration', restored)
        run('shell', 'wm', 'size', 'reset')
        run('shell', 'wm', 'density', 'reset')
        compact = wait(lambda state: state['width'] < 600 and state['mode'] == 'bottom')
        record('return_to_phone', compact)
        source = json.loads(Path('payload/source.json').read_text())
        report = dict(schema=1, suite='navigation-lifecycle-matrix', success=True,
                      source=source, physical_boox_tested=False, checks=checks)
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        return report
    finally:
        run('shell', 'wm', 'size', 'reset', check=False)
        run('shell', 'wm', 'density', 'reset', check=False)
        run('shell', 'am', 'force-stop', BUNDLE, check=False)


def apple(device, output):
    output.mkdir(parents=True, exist_ok=True)
    prefix = ['xcrun', 'simctl']
    def run(*args, env=None):
        return subprocess.run([*prefix, *args], env=env, capture_output=True, check=True, timeout=30)
    data_root = Path(run('get_app_container', device, BUNDLE, 'data').stdout.decode().strip())
    root = data_root / 'Library/Caches/navigation-foundation-probe'
    if root.exists():
        shutil.rmtree(root)  # Only this explicitly isolated test fixture.
    def launch():
        run('launch', '--terminate-running-process', device, BUNDLE,
            env=dict(os.environ, SIMCTL_CHILD_LOGISTICS_NAVIGATION_HOLD='1'))
    def wait(predicate, timeout=30):
        end, last = time.monotonic() + timeout, None
        while time.monotonic() < end:
            try:
                last = json.loads((root / 'probe.json').read_text())
            except (OSError, ValueError):
                pass
            if last and predicate(last):
                return last
            time.sleep(.2)
        raise RuntimeError('Native Apple geometry condition timed out: ' + repr(last))
    sequence = 0
    def command(action, **values):
        nonlocal sequence
        sequence += 1
        temporary = root / 'control.tmp'
        temporary.write_text(json.dumps(dict(sequence=sequence, action=action, **values)))
        temporary.replace(root / 'control.json')
        return wait(lambda state: state['sequence'] == sequence)
    checks = []
    def record(name, state):
        checks.append(dict(case=name, state=state))
        run('io', device, 'screenshot', str((output / (name + '.png')).resolve()))
        print('NAVIGATION_LIFECYCLE_CASE=' + name, flush=True)
    try:
        launch()
        initial = wait(lambda state: state['width'] > 0)
        record('initial', initial)
        changed = command('edit', text='Durable Apple navigation draft')
        command('select', destination='documents')
        command('rotate', orientation='portrait')
        portrait = wait(lambda state: state['height'] > state['width'])
        assert portrait['text'] == changed['text']
        record('portrait', portrait)
        command('rotate', orientation='landscape')
        landscape = wait(lambda state: state['width'] > state['height'])
        assert landscape['text'] == changed['text']
        record('landscape', landscape)
        run('launch', device, 'com.apple.Preferences')
        run('launch', device, BUNDLE)
        resumed = wait(lambda state: state['destination'] == 'documents' and state['application_active'])
        assert resumed['text'] == changed['text']
        record('background_resume', resumed)
        run('terminate', device, BUNDLE)
        launch()
        restored = wait(lambda state: state['pid'] != initial['pid'])
        assert restored['text'] == changed['text'] and restored['document_id'] == changed['document_id']
        record('process_restoration', restored)
        report = dict(schema=1, suite='navigation-apple-lifecycle-matrix', success=True,
                      source=json.loads(Path('payload/source.json').read_text()), checks=checks)
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        return report
    finally:
        run('terminate', device, BUNDLE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', type=Path, default=Path(os.environ.get('ANDROID_HOME', '')) / 'platform-tools/adb')
    parser.add_argument('--device', required=True)
    parser.add_argument('--ios', action='store_true', help='Exercise an installed Apple test-mode app')
    parser.add_argument('--output', type=Path, default=Path('logs/navigation/android-lifecycle'))
    args = parser.parse_args()
    if args.ios:
        apple(args.device, args.output)
    else:
        android(args.adb, args.device, args.output)
