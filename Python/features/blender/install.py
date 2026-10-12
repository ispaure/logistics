"""Verified whole-bundle installation with cancellation and safe staging."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import zipfile

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import copy_stream
from commonUtils.runtime.streams.downloads import provision
from .releases import relative_path

MARKER = '.logistics-blender.json'


@contextmanager
def installation_lock(destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name('.' + destination.name + '.lock')
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Another operation owns this installation. If no Logistics operation is running, '
                         f'remove the stale lock folder: {lock}') from None
    try:
        yield
    finally:
        lock.rmdir()


def installed(release, destination):
    try:
        metadata = json.loads((destination / MARKER).read_text(encoding='utf-8'))
        return (metadata == {'version': release.version, 'platform': release.platform,
                             'sha256': release.sha256, 'executable': release.executable}
                and (destination / relative_path(release.executable)).is_file())
    except (OSError, ValueError):
        return False


def extract_zip(package, output, cancelled):
    with zipfile.ZipFile(package) as archive:
        for member in archive.infolist():
            check_cancelled(cancelled)
            path = relative_path(member.filename)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError('Unexpected symlink in Windows Blender package')
            destination = output / path
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open('wb') as target:
                    copy_stream(source, target, cancelled=cancelled)
                if mode & 0o111:
                    destination.chmod(0o755)


def extract_tar(package, output, cancelled):
    with tarfile.open(package, 'r:xz') as archive:
        for member in archive:
            check_cancelled(cancelled)
            # Blender's Linux bundle needs internal symlinks. Python's data filter
            # permits those but rejects devices and links/paths escaping staging.
            archive.extract(member, output, filter='data')


def extract_dmg(package, output, cancelled):
    check_cancelled(cancelled)
    mounted = subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-plist', str(package)],
                             check=True, capture_output=True, timeout=120)
    mounts = [entry['mount-point'] for entry in plistlib.loads(mounted.stdout).get('system-entities', [])
              if 'mount-point' in entry]
    try:
        source = next((Path(mount) / 'Blender.app' for mount in mounts
                       if (Path(mount) / 'Blender.app').is_dir()), None)
        if source is None:
            raise ValueError('Official DMG does not contain Blender.app')
        check_cancelled(cancelled)
        # ditto preserves the app bundle's symlinks, permissions and metadata.
        subprocess.run(['ditto', str(source), str(output / 'Blender.app')], check=True, timeout=300)
        check_cancelled(cancelled)
    finally:
        for mount in reversed(mounts):
            subprocess.run(['hdiutil', 'detach', mount], check=True, capture_output=True, timeout=60)


def install_release(release, destination, *, report=lambda *args: None, cancelled=lambda: False):
    destination = Path(destination)
    with installation_lock(destination):
        check_cancelled(cancelled)
        if installed(release, destination):
            return destination
        if destination.exists() or destination.is_symlink():
            raise ValueError('Installation folder already exists but is incomplete or belongs to another build. '
                             'Inspect it before removing it and reinstalling.')
        with TemporaryDirectory(prefix=f'.blender-{release.version}-', dir=destination.parent) as workspace:
            workspace = Path(workspace)
            package = workspace / 'package'
            provision(release.download_spec(), package, cancelled=cancelled,
                      progress=lambda done, total: report(done, total, f'Downloading Blender {release.version}…'))
            check_cancelled(cancelled)
            report(0, 0, 'Verified SHA-256. Extracting Blender…')
            output = workspace / 'extracted'
            output.mkdir()
            {'zip': extract_zip, 'tar.xz': extract_tar, 'dmg': extract_dmg}[release.format](package, output, cancelled)
            bundle = output / relative_path(release.bundle)
            executable = bundle / relative_path(release.executable)
            if not bundle.is_dir() or not executable.is_file() or not executable.resolve().is_relative_to(bundle.resolve()):
                raise ValueError('Package does not contain the configured Blender executable')
            if os.name != 'nt':
                executable.chmod(executable.stat().st_mode | 0o111)
            (bundle / MARKER).write_text(json.dumps({'version': release.version, 'platform': release.platform,
                                                    'sha256': release.sha256, 'executable': release.executable}),
                                         encoding='utf-8')
            check_cancelled(cancelled)
            bundle.rename(destination)
    return destination


def remove_installation(release, destination):
    with installation_lock(destination):
        if destination.is_symlink() or not installed(release, destination):
            raise ValueError('Only a complete Logistics-managed installation can be removed here')
        shutil.rmtree(destination)
