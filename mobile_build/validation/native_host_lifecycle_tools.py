"""Run an installed, isolated full-host IME/scene/Activity probe, then remove it."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

BUNDLE = 'io.github.ispaure.logisticslifecyclecontinuation'
RESULT = 'native-host-lifecycle.json'
FILES = (RESULT, 'native-host-lifecycle-phase.json', 'native-host-lifecycle-progress.json',
         'native-host-lifecycle-history.json', 'logistics-native-ui-fault.log', 'native-host-python-stderr.log')


def require_clean_callbacks(errors):
    assert not any(marker in errors for marker in (b'Error in handler:', b'Traceback (most recent call last)',
                                                   b'Task exception was never retrieved')), 'Native Python callback errors; see platform stderr log'


def validate(platform, device, output, *, adb='adb', timeout=180):
    if platform not in ('android', 'ios'):
        raise ValueError('Choose android or ios')
    if platform == 'android' and not device.startswith('emulator-'):
        raise ValueError('Use a dedicated Android emulator')
    output.mkdir(parents=True, exist_ok=True)

    def run(*args, check=True):
        return subprocess.run(args, capture_output=True, check=check, timeout=30).stdout

    prefix = [adb, '-s', device] if platform == 'android' else ['xcrun', 'simctl']
    original_keyboard = None
    if platform == 'android':
        def read(name):
            return run(*prefix, 'exec-out', 'run-as', BUNDLE, 'cat', 'cache/' + name, check=False)
        def remove_reports():
            run(*prefix, 'shell', 'run-as', BUNDLE, 'rm', '-f', *('cache/' + name for name in FILES))
        def uninstall():
            run(*prefix, 'uninstall', BUNDLE)
        original_keyboard = run(*prefix, 'shell', 'settings', 'get', 'secure', 'show_ime_with_hard_keyboard').decode().strip()
        run(*prefix, 'shell', 'am', 'force-stop', BUNDLE)
    else:
        cache = Path(run(*prefix, 'get_app_container', device, BUNDLE, 'data').decode().strip()) / 'Library/Caches'
        def read(name):
            path = cache / name
            return path.read_bytes() if path.exists() else b''
        def remove_reports():
            for name in FILES:
                (cache / name).unlink(missing_ok=True)
        def uninstall():
            run(*prefix, 'uninstall', device, BUNDLE)
        run(*prefix, 'terminate', device, BUNDLE, check=False)
    accepted = False
    try:
        remove_reports()
        if platform == 'android':
            run(*prefix, 'shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '1')
            run(*prefix, 'shell', 'am', 'start', '-n', BUNDLE + '/org.beeware.android.MainActivity')
        else:
            run(*prefix, 'launch', '--stdout=' + str(output.resolve() / 'ios-stdout.log'),
                '--stderr=' + str(output.resolve() / 'ios-stderr.log'), device, BUNDLE)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = json.loads(read(RESULT))
            except (ValueError, UnicodeError):
                time.sleep(.5)
                continue
            assert result['success'], result.get('error', result)
            assert len(result['ime']) == 3
            errors = read('native-host-python-stderr.log')
            assert b'NATIVE_HOST_STDERR_CAPTURE=started' in errors, 'Python stderr capture was not installed'
            require_clean_callbacks(errors)
            if platform == 'ios':
                assert len(result['windows']) == 3
            else:
                assert result['boots'] == 4 and len(result['activity_runs']) == 4
                assert len({item['activity'] for item in result['activity_runs']}) == 4
                assert len({item['run_id'] for item in result['activity_runs']}) == 4
                assert all(item['retired_previous'] for item in result['activity_runs'][1:])
                assert len(result['activity_runs'][0]['landscape_ime']) == 3
                errors = run(*prefix, 'logcat', '-d', '--pid=' + str(result['pid']), '-s', 'python.stderr:W')
                (output / 'android-python-stderr.log').write_bytes(errors)
                require_clean_callbacks(errors)
            accepted = True
            return result
        raise TimeoutError('Native host lifecycle timed out; see saved phase and fault diagnostics')
    finally:
        # Preserve failure evidence too, before deleting this QA package.
        try:
            (output / 'host-validation.json').write_text(json.dumps(dict(accepted=accepted, platform=platform)) + '\n')
            for name in FILES:
                value = read(name)
                if value:
                    (output / name).write_bytes(value)
        finally:
            try:
                if platform == 'android':
                    if original_keyboard == 'null':
                        run(*prefix, 'shell', 'settings', 'delete', 'secure', 'show_ime_with_hard_keyboard')
                    else:
                        run(*prefix, 'shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', original_keyboard)
            finally:
                uninstall()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('android', 'ios'))
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--adb', default=shutil.which('adb') or 'adb')
    args = parser.parse_args()
    report = validate(args.platform, args.device, args.output, adb=args.adb)
    print(json.dumps(dict(success=report['success'], checks=report['checks'])))


if __name__ == '__main__':
    main()
