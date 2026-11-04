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

PROBES = {
    'drawing-save-stress': ('notebook_desktop_stress_probe.py', 240, True),
    'page-two-memory': ('notebook_memory_probe.py', 600, True),
    'menus-zoom': ('notebook_canvas_probe.py', 240, True),
    'view-zoom': ('notebook_view_probe.py', 240, True),
    'brush-pixels': ('brush_canvas_probe.py', 240, True),
    'templates': ('notebook_template_probe.py', 240, True),
    'mobile-ui': ('notebook_mobile_ui_probe.py', 240, True),
    'mobile-laptop': ('notebook_mobile_ui_probe.py', 240, True),
    'images-passwords': ('notebook_images_probe.py', 120, True),
    'pdf-annotation': ('pdf_annotation_probe.py', 240, True),
    'encrypted-storage': ('notebook_storage_probe.py', 240, False),
    # Acceptance already runs the killed-writer recovery probe.
    'storage-acceptance': ('notebook_acceptance_probe.py', 600, False),
    'independent-codec': ('independent_codec_probe.py', 900, False),
}
CORE_PROBES = tuple(PROBES)[:5]
RENDERING_ENVIRONMENT = ('QT_OPENGL', 'QT_QUICK_BACKEND', 'QTWEBENGINE_CHROMIUM_FLAGS',
                         'QSG_RHI_BACKEND', 'QSG_RHI_PREFER_SOFTWARE_RENDERER')


def main(output, rendering=None, probes=None, *, profile='core', go=None, latency_mode='enforce',
         max_process_tree_mib=None, max_remount_growth_mib=None):
    root = Path(__file__).resolve().parents[3]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    requested = probes if probes is not None else (CORE_PROBES if profile == 'core' else PROBES)
    if not requested or any(name not in PROBES for name in requested):
        raise ValueError('Select at least one known notebook probe')
    # Preserve dependency order even when --probe options arrive in reverse.
    selected = tuple(name for name in PROBES if name in requested)
    if 'independent-codec' in selected:
        go = go or shutil.which('go') or root / 'mobile_build/.tools/go/bin' / ('go.exe' if os.name == 'nt' else 'go')
        if not Path(go).is_file():
            raise RuntimeError('Independent codec acceptance requires --go PATH')
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
                  qt_backend=backend, display='owned Xvfb' if prefix else 'guest session',
                  profile=profile, selected_probes=selected, latency_mode=latency_mode, checks=[])
    try:
        for mode_index, rendering in enumerate(modes):
            env = dict(os.environ, QT_QPA_PLATFORM=backend, PYTHONUNBUFFERED='1',
                       PYTHONPATH=os.pathsep.join((str(root / 'Python'), str(root))))
            # A software/WARP parent must not silently turn the native leg into
            # another software run. Each leg owns these rendering choices.
            for key in RENDERING_ENVIRONMENT:
                env.pop(key, None)
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
            for name in selected:
                script, timeout, renderer_sensitive = PROBES[name]
                if mode_index and not renderer_sensitive:
                    continue
                started = time.monotonic()
                argv = [*prefix, sys.executable, str(Path(__file__).with_name(script)), '--output', str(output / rendering / name)]
                if name == 'independent-codec':
                    argv += ['--go', str(go)]
                    acceptance = output / modes[0] / 'storage-acceptance'
                    accepted = any(row['name'] == 'storage-acceptance' and row['status'] == 'passed'
                                   for row in result['checks'])
                    if accepted:
                        for archive in ('acceptance.rmdoc', 'modern.rmdoc'):
                            argv += ['--archive', str(acceptance / archive)]
                elif name == 'mobile-laptop':
                    argv += ['--laptop-only']
                elif name == 'drawing-save-stress':
                    argv += ['--latency-mode', latency_mode]
                elif name == 'page-two-memory':
                    for option, value in (('--max-process-tree-mib', max_process_tree_mib),
                                          ('--max-remount-growth-mib', max_remount_growth_mib)):
                        if value is not None:
                            argv += [option, str(value)]
                with (output / (rendering + '-' + name + '.log')).open('w', encoding='utf-8') as log:
                    try:
                        process = subprocess.run(argv, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                                 timeout=timeout)
                        row = dict(name=name, rendering=rendering, exit_code=process.returncode, status='passed' if process.returncode == 0 else 'failed')
                    except subprocess.TimeoutExpired:
                        row = dict(name=name, rendering=rendering, status='failed', error='Native probe timed out')
                    except OSError as error:
                        row = dict(name=name, rendering=rendering, status='failed', error=str(error))
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
    parser.add_argument('--profile', choices=('core', 'full'), default='core',
                        help='Core preserves the five existing renderer checks; full also schedules templates, mobile UI, PDF, encrypted storage, crash recovery and independent decoding.')
    parser.add_argument('--probe', action='append', choices=tuple(PROBES),
                        help='Select individual checks instead of the profile; repeat to include several.')
    parser.add_argument('--go', type=Path, help='Go compiler for the independent codec check.')
    parser.add_argument('--latency-mode', choices=('enforce', 'diagnostic'), default='enforce')
    parser.add_argument('--max-process-tree-mib', type=float)
    parser.add_argument('--max-remount-growth-mib', type=float)
    args = parser.parse_args()
    raise SystemExit(main(args.output, args.rendering, args.probe, profile=args.profile, go=args.go,
                         latency_mode=args.latency_mode, max_process_tree_mib=args.max_process_tree_mib,
                         max_remount_growth_mib=args.max_remount_growth_mib))
