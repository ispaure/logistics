"""Pinned desktop colour-renderer libraries; media never enters this installer."""
import ctypes
from ctypes.util import find_library
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import struct
import platform
from tempfile import TemporaryDirectory

from commonUtils.persistence.locking import file_lock
from commonUtils.runtime.streams.downloads import DownloadSpec, provision

VERSION = '1.5.0'
DIGEST = '8fad50479b10e09645053457cec46bd53d054ced2242cfe68f74586735a20dc7'
URL = f'https://github.com/iina/iina/releases/download/v{VERSION}/IINA.v{VERSION}.dmg'
_handles = {}


def installation_valid(destination):
    destination = Path(destination)
    try:
        if destination.is_symlink():
            return False
        receipt = json.loads((destination / 'installation.json').read_text())
        return (receipt['archive_sha256'] == DIGEST and bool(receipt['files'])
                and 'libmpv.2.dylib' in receipt['files']
                and all(Path(name).name == name and not (destination / name).is_symlink()
                        and sha256((destination / name).read_bytes()).hexdigest() == digest
                        for name, digest in receipt['files'].items()))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def install_macos(archive, destination):
    """Read-only image mount with paired detach; retain runtime and publisher notices."""
    destination = Path(destination)
    with file_lock(destination.with_suffix('.lock'), timeout=60) as acquired:
        if not acquired:
            raise RuntimeError('Another Logistics instance is preparing colour playback.')
        if installation_valid(destination):
            return destination / 'libmpv.2.dylib'
        if destination.is_symlink():
            raise ValueError('Linked colour-renderer directories are not supported.')
        destination.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.mpv-install-', dir=destination.parent) as temporary:
            mount = Path(temporary) / 'image'
            mount.mkdir()
            subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-quiet',
                            '-mountpoint', str(mount), str(archive)], check=True, timeout=120)
            try:
                app = mount / 'IINA.app/Contents'
                files = {}
                for source in (app / 'Frameworks').glob('*.dylib'):
                    # System Swift libraries must not be loaded a second time.
                    if source.name.startswith('libswift'):
                        continue
                    data = source.read_bytes()
                    target = destination / source.name
                    if target.is_symlink():
                        raise ValueError('Linked colour-renderer libraries are not supported.')
                    target.write_bytes(data)
                    files[source.name] = sha256(data).hexdigest()
                if 'libmpv.2.dylib' not in files:
                    raise ValueError('The pinned package has no libmpv runtime.')
                from services.license_inventory import is_notice
                notices = destination / 'notices'
                for source in app.rglob('*'):
                    if source.is_file() and is_notice(source.relative_to(app).as_posix()):
                        target = notices / source.relative_to(app)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, target)
                notices.mkdir(parents=True, exist_ok=True)
                for name in ('GPL-2.0.txt', 'GPL-3.0.txt'):
                    shutil.copyfile(Path(__file__).with_name('licenses') / name, notices / name)
                (notices / 'runtime.txt').write_text(
                    'libmpv and codec dependencies from IINA ' + VERSION + '\n' + URL + '\n'
                    'Upstream source and dependency build recipes: https://github.com/iina/deps-buildscripts\n'
                    'mpv source and licensing: https://github.com/mpv-player/mpv/tree/v0.41.0\n'
                    'The publisher image supplies no loose component notice inventory. The GPL reference texts '
                    'are retained here; individual codec dependencies have their own terms.\n')
                (destination / 'installation.json').write_text(json.dumps(dict(
                    archive_sha256=DIGEST, publisher_url=URL,
                    source_url=f'https://github.com/iina/iina/tree/v{VERSION}', files=files), indent=2))
            finally:
                subprocess.run(['hdiutil', 'detach', '-quiet', str(mount)], check=True, timeout=60)
        return destination / 'libmpv.2.dylib'


def runtime(*, interactive=False):
    if sys.platform != 'darwin':
        library = find_library('mpv') or find_library('mpv-2')
        if library:
            return Path(library)
        raise RuntimeError('Install libmpv to use colour-managed playback on this platform.')
    import config
    root = config.LogisticsConfig(create_resources=False).path_logistics_software / 'video'
    destination = root / f'libmpv-iina-{VERSION}'
    if installation_valid(destination):
        return destination / 'libmpv.2.dylib'
    archive = root / f'IINA-{VERSION}.dmg'
    spec = DownloadSpec(name='Colour video runtime', version=VERSION, url=URL,
                        sha256=DIGEST, installed_sha256=DIGEST)
    if interactive:
        from commonUtils.ui.tasks.download import ensure_download
        if ensure_download(spec, archive) is None:
            raise RuntimeError('The colour video runtime download was cancelled.')
    else:
        provision(spec, archive)
    try:
        return install_macos(archive, destination)
    except subprocess.SubprocessError as error:
        raise RuntimeError('The colour video runtime could not be prepared.') from error


def library(path=None, *, interactive=False):
    """Resolve only packaged dependencies, leaving system Swift/frameworks alone."""
    path = Path(path) if path is not None else runtime(interactive=interactive)
    key = str(path.resolve())
    if key in _handles:
        return _handles[key]
    loading = set()
    def load(candidate):
        name = str(candidate.resolve())
        if name in _handles:
            return _handles[name]
        if name in loading or candidate.is_symlink():
            raise RuntimeError('Invalid colour-renderer dependency graph.')
        loading.add(name)
        try:
            if sys.platform == 'darwin':
                # Preload the package's complete dependency closure before dyld
                # can satisfy @rpath with an older Homebrew/other-player ABI.
                for dependency in macho_dependencies(candidate):
                    if dependency.startswith('@rpath/'):
                        relative = dependency.removeprefix('@rpath/')
                        if Path(relative).name != relative:
                            raise RuntimeError('Invalid colour-renderer dependency path.')
                        owned = candidate.parent / relative
                        if owned.is_file() and not relative.startswith('libswift'):
                            load(owned)
            for _ in range(128):
                try:
                    result = ctypes.CDLL(str(candidate))
                    _handles[name] = result
                    return result
                except OSError as error:
                    missing = re.search(r'Library not loaded: @rpath/([^\s]+)', str(error))
                    if not missing or Path(missing[1]).name != missing[1]:
                        raise
                    dependency = candidate.parent / missing[1]
                    if dependency.name.startswith('libswift') or not dependency.is_file():
                        raise
                    load(dependency)
            raise RuntimeError('Too many colour-renderer dependencies.')
        finally:
            loading.remove(name)
    return load(path)


def macho_dependencies(path):
    """Read load commands for the current architecture without developer tools."""
    data = Path(path).read_bytes()
    offset = 0
    magic = data[:4]
    if magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        count = struct.unpack_from('>I', data, 4)[0]
        if not 0 < count <= 16:
            raise ValueError('Invalid universal video library.')
        cpu = 0x100000c if platform.machine().lower() in {'arm64', 'aarch64'} else 0x1000007
        wide = magic[-1] == 0xbf
        for i in range(count):
            row = 8 + i * (32 if wide else 20)
            if struct.unpack_from('>I', data, row)[0] == cpu:
                offset = struct.unpack_from('>Q' if wide else '>I', data, row + 8)[0]
                break
        else:
            raise ValueError('The colour video library has no matching architecture.')
    if data[offset:offset + 4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('Invalid 64-bit video library.')
    count, size = struct.unpack_from('<II', data, offset + 16)
    end, cursor = offset + 32 + size, offset + 32
    if count > 4096 or end > len(data):
        raise ValueError('Invalid video library load commands.')
    found = []
    for _ in range(count):
        kind, length = struct.unpack_from('<II', data, cursor)
        if length < 8 or cursor + length > end:
            raise ValueError('Invalid video library load command.')
        if kind in (0xc, 0x80000018, 0x8000001f, 0x80000023):
            start = struct.unpack_from('<I', data, cursor + 8)[0]
            if not 12 <= start < length:
                raise ValueError('Invalid video library dependency.')
            found.append(data[cursor + start:cursor + length].split(b'\0', 1)[0].decode('utf-8'))
        cursor += length
    return found
