"""Finish an installed disposable Destination QA probe on an iOS simulator."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

BUNDLE = 'io.github.ispaure.logisticsdestinationqa'


def finish(device, output):
    def sim(*args):
        return subprocess.check_output(['xcrun', 'simctl', *args], text=True, timeout=30).strip()
    cache = Path(sim('get_app_container', device, BUNDLE, 'data')) / 'Library/Caches'
    output.mkdir(parents=True, exist_ok=True)
    original = sim('ui', device, 'appearance').lower()
    if original not in ('light', 'dark'):
        raise ValueError('Cannot preserve simulator appearance: ' + original)
    try:
        sim('launch', device, BUNDLE)
        for phase in ('hidden-light', 'hidden-tiles', 'hidden-dark'):
            for _ in range(300):
                path = cache / 'destination-state.json'
                state = json.loads(path.read_text()) if path.exists() else {}
                if state.get('phase') == phase:
                    break
                if state.get('phase') == 'complete':
                    raise RuntimeError(state)
                time.sleep(.1)
            else:
                raise TimeoutError('QA did not reach ' + phase)
            if phase == 'hidden-dark':
                sim('ui', device, 'appearance', 'dark')
                time.sleep(.5)
            (cache / 'destination-command').write_text('next')
            time.sleep(.3)
        result = cache / 'destination-result.json'
        for _ in range(150):
            if result.exists():
                break
            time.sleep(.1)
        report = json.loads(result.read_text())
        if not report.get('success'):
            raise RuntimeError(report)
        return report
    finally:
        for name in ('destination-state.json', 'destination-result.json', 'destination-python.log'):
            if (cache / name).exists():
                shutil.copyfile(cache / name, output / name)
        for path in cache.glob('hidden-*.png'):
            shutil.copyfile(path, output / path.name)
        sim('ui', device, 'appearance', original)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(finish(args.device, args.output), indent=2))
