"""Run notebook native acceptance on the selected desktop guest, with owned display cleanup."""
import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time


def main(output, rendering=None, probes=None):
    root = Path(__file__).resolve().parents[3]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    backend = {'Windows': 'windows', 'Linux': 'xcb', 'Darwin': 'cocoa'}[system]
    modes = ('native', 'software', 'chromium-software', *(['warp'] if system == 'Windows' else [])) if rendering == 'all' else (
        rendering or ('software' if system == 'Linux' and not os.environ.get('DISPLAY') else 'native'),)
    env = dict(os.environ, QT_QPA_PLATFORM=backend, PYTHONUNBUFFERED='1')
    prefix = []
    if system == 'Linux' and not env.get('DISPLAY'):
        if not shutil.which('xvfb-run'):
            raise RuntimeError('Native Linux acceptance needs an X11 display or xvfb-run; offscreen is not native acceptance.')
        prefix = ['xvfb-run', '-a', '--server-args=-screen 0 1440x1000x24']
    result = dict(pyside=version('PySide6'), system=system, architecture=platform.machine(), python=sys.version,
                  qt_backend=backend, display='owned Xvfb' if prefix else 'guest session', checks=[])
    try:
        for rendering in modes:
            env = dict(os.environ, QT_QPA_PLATFORM=backend, PYTHONUNBUFFERED='1')
            if rendering == 'warp':
                if system != 'Windows':
                    raise ValueError('WARP acceptance requires Windows')
                env.pop('QT_OPENGL', None)
                env.pop('QT_QUICK_BACKEND', None)
                env.update(QSG_RHI_BACKEND='d3d11', QSG_RHI_PREFER_SOFTWARE_RENDERER='1',
                           QTWEBENGINE_CHROMIUM_FLAGS='--use-gl=angle --use-angle=d3d11-warp',
                           QT_LOGGING_RULES='qt.webenginecontext.debug=true', QSG_INFO='1')
            elif rendering == 'software':
                env.update(QT_QUICK_BACKEND='software', QT_OPENGL='software', QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu')
            elif rendering == 'chromium-software':
                env.update(QT_OPENGL='software', QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu')
            for name, script in [('drawing-save-stress', 'notebook_desktop_stress_probe.py'),
                                 ('page-two-memory', 'notebook_memory_probe.py'),
                                 ('menus-zoom', 'notebook_canvas_probe.py'), ('brush-pixels', 'brush_canvas_probe.py')]:
                if probes and name not in probes:
                    continue
                started = time.monotonic()
                argv = [*prefix, sys.executable, str(Path(__file__).with_name(script)), '--output', str(output / rendering / name)]
                with (output / (rendering + '-' + name + '.log')).open('w', encoding='utf-8') as log:
                    try:
                        process = subprocess.run(argv, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                                 timeout=600 if name == 'page-two-memory' else 240)
                        row = dict(name=name, rendering=rendering, exit_code=process.returncode, status='passed' if process.returncode == 0 else 'failed')
                    except subprocess.TimeoutExpired:
                        row = dict(name=name, rendering=rendering, status='failed', error='Native probe timed out')
                row['seconds'] = time.monotonic() - started
                result['checks'].append(row)
                print(json.dumps(row), flush=True)
        result['status'] = 'passed' if all(row['status'] == 'passed' for row in result['checks']) else 'failed'
    finally:
        (output / 'native-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rendering', choices=('native', 'software', 'chromium-software', 'warp', 'all'),
                        help='Defaults to normal app rendering; headless Linux uses software. Other modes diagnose software graphics paths; all compares available paths.')
    parser.add_argument('--probe', action='append', choices=('drawing-save-stress', 'page-two-memory', 'menus-zoom', 'brush-pixels'),
                        help='Select individual checks; repeat to include several. Defaults to all checks.')
    args = parser.parse_args()
    raise SystemExit(main(args.output, args.rendering, args.probe))
