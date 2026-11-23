"""Drive the File Browser with native touch on a disposable Android emulator."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
import subprocess
import time

BUNDLE = 'io.github.ispaure.logisticsnotebookqa'
REQUEST = 'cache/file-drag-android-request.json'


def checked_point(value):
    if not isinstance(value, list) or len(value) != 2 or any(type(n) is not int or n < 0 for n in value):
        raise ValueError('Expected a synthetic touch point on the Android emulator.')
    return value


def observe_touch(event, emulator, record, evidence):
    if event != 'poll':
        return
    serial = record['serial']
    adb = [str(emulator.adb), '-s', serial]
    probe = subprocess.run([*adb, 'exec-out', 'run-as', BUNDLE, 'cat', REQUEST],
                           capture_output=True, timeout=10)
    if probe.returncode:
        return
    data = json.loads(probe.stdout)
    gesture = data['gesture']
    point = checked_point(data['start'])
    if gesture not in ('drag', 'menu'):
        raise ValueError('Unknown File Browser test gesture.')
    target = checked_point(data['target']) if gesture == 'drag' else point

    def motion(action, position):
        emulator.invoke('-s', serial, 'shell', 'input', 'motionevent', action, *map(str, position))

    with (evidence / 'input.jsonl').open('a') as receipt:
        receipt.write(json.dumps(data) + '\n')
    motion('DOWN', point)
    try:
        if gesture == 'menu':
            time.sleep(1.15)
            pending = subprocess.run([*adb, 'shell', 'run-as', BUNDLE, 'test', '-f',
                                      'cache/file-drag-held-menu.txt'], timeout=10)
            assert pending.returncode == 0, 'The tile menu did not open while the finger was down.'
        else:
            time.sleep(.57)
            motion('MOVE', [(4 * start + end) // 5 for start, end in zip(point, target)])
            motion('MOVE', target)
            time.sleep(1.4)
    finally:
        motion('UP', target)
    if gesture == 'menu':
        emulator.invoke('-s', serial, 'shell', 'input', 'keyevent', '4')
    emulator.invoke('-s', serial, 'shell', 'run-as', BUNDLE, 'rm', REQUEST)
