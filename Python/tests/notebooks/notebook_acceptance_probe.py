"""Retain synthetic hardware handoff archives and non-physical storage evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys

from Scripts.build_retention import scratch
from mobile_build.native_tests.tests.logisticsmobile.notebook_acceptance_checks import exercise_storage


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    with scratch() as root:
        report = exercise_storage(root)
        for name in ('acceptance.rmdoc', 'modern.rmdoc'):
            shutil.copyfile(root / name, output / name)
    owner = Path(__file__).resolve().parents[2] / 'features/notebooks'
    report['source_sha256'] = {str(p.relative_to(owner)): sha256(p.read_bytes()).hexdigest()
                             for p in sorted(owner.rglob('*'))
                             if p.is_file() and p.suffix in ('.py', '.js', '.css', '.html')}
    report['success'] = True
    (output / 'desktop-storage.json').write_text(json.dumps(report, indent=2))
    subprocess.run([sys.executable, str(Path(__file__).with_name('notebook_recovery_acceptance.py')),
                    '--output', str(output / 'desktop-restart.json')], check=True)
    print('Long legacy/modern archives, two layers, nine tools, failed writes, cancellation and killed-writer recovery passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
