"""Drive the disposable reader resume probe on an explicitly selected emulator."""
import argparse
import json
from pathlib import Path
import subprocess
import time

BUNDLE = 'io.github.ispaure.logisticsreaderresumeqa'
RESULT = 'cache/reader-resume-result.json'


def check(adb, device, output):
    if not device.startswith('emulator-'):
        raise ValueError('This synthetic sleep/trim driver requires an explicit Android emulator.')
    output.mkdir(parents=True, exist_ok=True)
    def run(*args, check=True):
        return subprocess.run([str(adb), '-s', device, *args], capture_output=True,
                              check=check, timeout=30)
    run('shell', 'am', 'force-stop', BUNDLE)
    run('shell', 'run-as', BUNDLE, 'rm', '-f', RESULT)
    run('shell', 'input', 'keyevent', '224')
    run('shell', 'wm', 'dismiss-keyguard')
    run('shell', 'am', 'start', '-W', '-n', BUNDLE + '/org.beeware.android.MainActivity')
    (output / 'driver.json').write_text(json.dumps(dict(device=device,
        lifecycle='HOME, screen off, native trim, screen on, resume existing activity',
        injected_trim_levels='80 + case sequence; native callback delivery required'), indent=2) + '\n')
    handled, last = set(), None
    try:
        started = time.monotonic()
        deadline = started + 600
        while time.monotonic() < deadline:
            response = run('exec-out', 'run-as', BUNDLE, 'cat', RESULT, check=False)
            if response.returncode:
                time.sleep(.2)
                continue
            try:
                state = json.loads(response.stdout)
            except ValueError:
                time.sleep(.2)
                continue
            (output / 'result.json').write_text(json.dumps(state, indent=2) + '\n')
            phase = state.get('phase'), state.get('case')
            if phase != last:
                print(f'{time.monotonic() - started:.1f}s {phase}', flush=True)
                last = phase
            if state.get('phase') == 'complete':
                return bool(state.get('success'))
            sequence = state.get('sequence', 0)
            if state.get('phase') == 'await_sleep' and sequence not in handled:
                handled.add(sequence)
                # Put the activity in the background before injecting a background
                # trim: Android treats a screen-off top activity as foreground.
                run('shell', 'input', 'keyevent', '3')
                time.sleep(.5)
                run('shell', 'input', 'keyevent', '223')
                time.sleep(1)
                # ActivityManager rejects equal/lower levels for the same live
                # process. Increasing background levels ensure every case gets
                # a real onTrimMemory callback instead of relying on deduped UI_HIDDEN.
                trim_deadline = time.monotonic() + 12
                while True:
                    trim = run('shell', 'am', 'send-trim-memory', BUNDLE, str(80 + sequence), check=False)
                    if not trim.returncode:
                        break
                    message = trim.stderr.decode(errors='replace')
                    if ('background trim level on a foreground process' not in message
                            or time.monotonic() >= trim_deadline):
                        raise RuntimeError('Emulator trim command failed: ' + message)
                    # Activity pause precedes onStop/process-state bookkeeping.
                    time.sleep(.2)
                time.sleep(1)
                run('shell', 'input', 'keyevent', '224')
                run('shell', 'wm', 'dismiss-keyguard')
                run('shell', 'am', 'start', '-W', '-n', BUNDLE + '/org.beeware.android.MainActivity')
            time.sleep(.2)
        raise TimeoutError('Reader resume probe timed out; see collected emulator diagnostics.')
    finally:
        screenshots = run('exec-out', 'run-as', BUNDLE, 'tar', '-cf', '-', 'cache/reader-resume-evidence', check=False)
        (output / 'screenshots.tar').write_bytes(screenshots.stdout)
        (output / 'screen.png').write_bytes(run('exec-out', 'screencap', '-p').stdout)
        (output / 'logcat.txt').write_bytes(run('logcat', '-d', '-t', '1500').stdout)
        run('shell', 'input', 'keyevent', '224', check=False)
        run('shell', 'wm', 'dismiss-keyguard', check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if check(args.adb, args.device, args.output) else 1)
