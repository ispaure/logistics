"""Logistics desktop prerequisites; shared backend machinery owns no app policy."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import time


def install_windows_webengine(path, sha256):
    """Install the reviewed guest wheel over the locked Windows placeholder."""
    from hashlib import file_digest
    from importlib.metadata import version
    import shutil
    from tempfile import TemporaryDirectory

    from logistics_build.test_environments import windows_webengine

    if sysconfig.get_platform() != 'win-arm64':
        raise ValueError('The configured WebEngine wheel requires native Windows ARM64 Python.')
    wheel = windows_webengine(path, sha256)
    if not wheel:
        raise ValueError('Set the Windows VM WebEngine wheel path and SHA-256.')
    source = Path(wheel['path'])
    if source.name.split('-')[1] != version('pyside6-webengine'):
        raise ValueError('The local WebEngine wheel version must match the locked PySide6 WebEngine version.')
    with TemporaryDirectory(prefix='logistics-webengine-') as work:
        staged = Path(work) / source.name
        shutil.copyfile(source, staged)
        with staged.open('rb') as stream:
            if file_digest(stream, 'sha256').hexdigest() != wheel['sha256']:
                raise ValueError('The local Windows ARM64 WebEngine wheel SHA-256 does not match the reviewed plan.')
        subprocess.run([sys.executable, '-m', 'uv', 'pip', 'install', '--python', sys.executable,
                        '--reinstall', '--no-deps', str(staged)], check=True, timeout=300)
    print('Installed Windows ARM64 WebEngine wheel SHA-256 ' + wheel['sha256'], flush=True)


def verify_qt(*, focused=False):
    try:
        import PySide6.QtWebEngineCore
    except ImportError as error:
        if (sys.platform == 'win32' and sysconfig.get_platform() == 'win-arm64'
                and getattr(error, 'name', None) == 'PySide6.QtWebEngineCore'):
            message = 'The pinned PySide6 wheel is missing Qt WebEngine on Windows ARM64.'
            if focused:
                print(message + ' Tests that require it can still fail.', file=sys.stderr, flush=True)
                return
            raise RuntimeError(message + ' Configure a compatible ARM64 WebEngine wheel or x86_64 '
                               'Python in Logistics Project Settings.') from error
        if sys.platform.startswith('linux'):
            import PySide6
            for library in Path(PySide6.__file__).parent.rglob('libQt6WebEngineCore.so.6'):
                result = subprocess.run(['ldd', str(library)], text=True, capture_output=True, timeout=30)
                for line in result.stdout.splitlines():
                    if 'not found' in line:
                        print('Missing Qt native dependency: ' + line.strip(), flush=True)
        raise


def main(*, focused=False):
    started = time.monotonic()
    from logistics_build.test_environments import load, verify_host
    values = load()
    if sys.platform == 'win32' and os.environ.get('LOGISTICS_WINDOWS_VM_PYTHON'):
        values['python_version'] = os.environ['LOGISTICS_WINDOWS_VM_PYTHON']
    host_environment = verify_host(values, hosted=os.environ.get('GITHUB_ACTIONS') == 'true',
                                   runner_arch=os.environ.get('RUNNER_ARCH'),
                                   interpreter_platform=sysconfig.get_platform())
    from PySide6.QtCore import qVersion
    verify_qt(focused=focused)
    from services.video_runtime import binding
    vlc = binding()
    from commonUtils.runtime.streams.downloads import provision
    from services.software import get_software
    executable = provision(*get_software('rclone'))
    version = subprocess.check_output([str(executable), 'version'], text=True, timeout=30).splitlines()[0]
    print(json.dumps(dict(test_environment=host_environment, qt=qVersion(), libvlc=vlc.libvlc_get_version().decode(), rclone=version, rclone_path=str(executable),
                          preparation_seconds=time.monotonic() - started)))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--focused', action='store_true', help='Prepare an explicitly selected subset of desktop tests')
    args = parser.parse_args()
    try:
        raise SystemExit(main(focused=args.focused))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Desktop prerequisite failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
