"""Drive the isolated native_lifecycle_probe entry point on installed test apps.

The fixed test bundle is deliberately different from the main Logistics app.
Build/stage current commonUtils plus the probe before running this driver.
"""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time

BUNDLE = 'io.github.ispaure.logisticsnativelifecycle'


def validate(platform, device, output, adb='adb'):
    output.mkdir(parents=True, exist_ok=True)

    def run(*args, check=True, data=None):
        return subprocess.run(args, input=data, capture_output=True, check=check, timeout=30)

    if platform == 'android':
        if not device.startswith('emulator-'):
            raise ValueError('This driver requires a dedicated Android emulator')
        prefix = [adb, '-s', device]
        cache = 'cache/'

        def read(name):
            return run(*prefix, 'exec-out', 'run-as', BUNDLE, 'cat', cache + name, check=False).stdout

        def write(name, value):
            command = shlex.quote('cat > ' + cache + name)
            run(*prefix, 'shell', 'run-as', BUNDLE, 'sh', '-c', command, data=value.encode())

        def launch():
            run(*prefix, 'shell', 'am', 'start', '-n', BUNDLE + '/org.beeware.android.MainActivity')

        def background():
            run(*prefix, 'shell', 'input', 'keyevent', 'KEYCODE_HOME')

        run(*prefix, 'shell', 'am', 'force-stop', BUNDLE)
        run(*prefix, 'shell', 'run-as', BUNDLE, 'rm', '-f',
            cache + 'native-lifecycle.json', cache + 'native-lifecycle-continue', cache + 'native-lifecycle-phase.json')
    else:
        prefix = ['xcrun', 'simctl']
        data = run(*prefix, 'get_app_container', device, BUNDLE, 'data').stdout.decode().strip()
        cache = Path(data) / 'Library/Caches'
        cache.mkdir(parents=True, exist_ok=True)

        def read(name):
            path = cache / name
            return path.read_bytes() if path.exists() else b''

        def write(name, value):
            (cache / name).write_text(value)

        def launch():
            run(*prefix, 'launch', device, BUNDLE)

        def background():
            run(*prefix, 'launch', device, 'com.apple.mobilesafari')

        run(*prefix, 'terminate', device, BUNDLE, check=False)
        for name in ('native-lifecycle.json', 'native-lifecycle-continue', 'native-lifecycle-phase.json'):
            (cache / name).unlink(missing_ok=True)

    expected_run = None

    def wait(filename, predicate, timeout=45):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = json.loads(read(filename))
            except (ValueError, UnicodeError):
                pass
            if last and expected_run is not None and last.get('run_id') != expected_run:
                raise AssertionError('Native probe instance was replaced during validation')
            if last and predicate(last):
                return last
            # Report an earlier case failure instead of timing out at its checkpoint.
            if filename != 'native-lifecycle.json':
                try:
                    finished = json.loads(read('native-lifecycle.json'))
                except (ValueError, UnicodeError):
                    pass
                else:
                    (output / (platform + '-lifecycle.json')).write_text(json.dumps(finished, indent=2) + '\n')
                    raise AssertionError(f'Probe finished before checkpoint: {finished}')
            time.sleep(.2)
        raise TimeoutError(f'{filename}: last native state {last!r}')

    write('native-lifecycle-external', '1')
    checks = []
    try:
        launch()
        for name in ('navigation', 'canvas', 'speech'):
            phase = wait('native-lifecycle-phase.json', lambda value: value['name'] == name)
            if expected_run is None:
                expected_run = phase['run_id']
            background()
            time.sleep(1)
            suspended = wait('native-lifecycle-phase.json', lambda value: value['name'] == name)
            launch()
            resumed = wait('native-lifecycle-phase.json', lambda value: value['name'] == name
                           and value['tick'] > suspended['tick'])
            assert resumed['pid'] == phase['pid'], 'Background/resume replaced the process'
            if platform == 'android' and name == 'navigation':
                for size, mode in (('1860x2480', 'rail'), ('2480x1860', 'rail')):
                    run(*prefix, 'shell', 'wm', 'size', size)
                    run(*prefix, 'shell', 'wm', 'density', '300')
                    state = wait('native-lifecycle-phase.json', lambda value: value['state']['mode'] == mode
                                 and value['state']['width'] >= 600
                                 and (size != '2480x1860' or value['state']['width'] > value['state']['height']))
                    checks.append(dict(case=size, phase=state))
                run(*prefix, 'shell', 'wm', 'size', 'reset')
                run(*prefix, 'shell', 'wm', 'density', 'reset')
                wait('native-lifecycle-phase.json', lambda value: value['state']['mode'] == 'bottom')
            checks.append(dict(case=name + '-resume', phase=resumed))
            write('native-lifecycle-continue', name)
        result = wait('native-lifecycle.json', lambda value: True)
        result['external_checks'] = checks
        result['external_passed'] = (result['visibility_events'].count('hide') >= 3
                                     and result['visibility_events'].count('show') >= 4)
        result['passed'] = result['passed'] and result['external_passed']
        (output / (platform + '-lifecycle.json')).write_text(json.dumps(result, indent=2) + '\n')
        assert result['passed'], result['cases']
        assert result['visibility_events'].count('hide') >= 3, 'Native background events were not observed'
        assert result['visibility_events'].count('show') >= 4, 'Native foreground events were not observed'
        return result
    finally:
        if platform == 'android':
            run(*prefix, 'shell', 'wm', 'size', 'reset', check=False)
            run(*prefix, 'shell', 'wm', 'density', 'reset', check=False)
            run(*prefix, 'shell', 'run-as', BUNDLE, 'rm', '-f', 'cache/native-lifecycle-external', check=False)
        else:
            (cache / 'native-lifecycle-external').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('android', 'ios'))
    parser.add_argument('--device', required=True, help='Dedicated simulator UUID or ADB serial')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--adb', default=shutil.which('adb') or 'adb')
    args = parser.parse_args()
    result = validate(args.platform, args.device, args.output, args.adb)
    print(json.dumps(dict(platform=args.platform, passed=result['passed'], cases=len(result['cases']))))


if __name__ == '__main__':
    main()
