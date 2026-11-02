"""Desktop software policy for LibVLC; independent of document provider storage."""

import ctypes
from ctypes.util import find_library
from hashlib import sha256
import os
from pathlib import Path
import platform
import sys
import sysconfig
from tempfile import NamedTemporaryFile
import zipfile

from commonUtils.runtime.streams.downloads import DownloadSpec, provision
from commonUtils.persistence.locking import file_lock
from services.license_inventory import is_notice


PACKAGES = {
    'darwin': ('mac', '3.1.3.2', 'b83faf0e4866a5d8c53e998aec4caafc38d0e8aff9390a2a02d49af4d9757715'),
    'win32': ('windows', '3.0.24', '3da3f37ee2b2b10e5c788d830a3b513658c36521ea1b0f966ed86eb69f41ef3c'),
}
_handles = []
_binding = None


def extract(archive, destination, prefix):
    """Serialize installations across Logistics instances and repair altered bytes."""
    with file_lock(destination.with_suffix('.lock'), timeout=30) as acquired:
        if not acquired:
            raise RuntimeError('Another Logistics instance is preparing video playback. Try again.')
        found = False
        with zipfile.ZipFile(archive) as package:
            for item in package.infolist():
                relative = item.filename[len(prefix):] if item.filename.startswith(prefix) else (
                    'notices/' + item.filename if is_notice(item.filename) or item.filename.lower().endswith(('.txt', '.nuspec', '.md')) else '')
                if not relative or item.is_dir():
                    continue
                target = destination / relative
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Invalid LibVLC package member.')
                data = package.read(item)
                if target.is_symlink() or not target.is_file() or sha256(target.read_bytes()).digest() != sha256(data).digest():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = None
                    try:
                        with NamedTemporaryFile(dir=target.parent, prefix='.libvlc-', delete=False) as output:
                            temporary = Path(output.name)
                            output.write(data)
                        os.replace(temporary, target)
                    finally:
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
                found = found or relative.endswith(('libvlc.dylib', 'libvlc.dll'))
        if not found:
            raise RuntimeError('The pinned LibVLC package has no runtime for this architecture.')


def runtime(*, interactive=False):
    """Resolve libraries from a checksum-pinned package, or Linux system libraries."""
    if sys.platform.startswith('linux'):
        library = find_library('vlc')
        if not library:
            raise RuntimeError('Install LibVLC and its codec/output plugins using your Linux package manager.')
        return library, None
    if sys.platform not in PACKAGES:
        raise RuntimeError('No LibVLC runtime is declared for this platform.')
    family, version, digest = PACKAGES[sys.platform]
    # Windows deployments may run x86_64 Python on ARM hardware.
    architecture = platform.machine().lower()
    arch = 'arm64' if architecture in {'arm64', 'aarch64'} else 'x64'
    if sys.platform == 'win32':
        target = sysconfig.get_platform().lower()
        arch = 'arm64' if 'arm64' in target else 'x86' if ctypes.sizeof(ctypes.c_void_p) == 4 else 'x64'
    import config
    root = config.LogisticsConfig(create_resources=False).path_logistics_software / 'video'
    archive = root / f'libvlc-{family}-{version}.nupkg'
    spec = DownloadSpec(name='LibVLC video runtime', version=version,
        url=f'https://api.nuget.org/v3-flatcontainer/videolan.libvlc.{family}/{version}/videolan.libvlc.{family}.{version}.nupkg',
        sha256=digest, installed_sha256=digest)
    if interactive:
        from commonUtils.ui.tasks.download import ensure_download
        if ensure_download(spec, archive) is None:
            raise RuntimeError('The LibVLC runtime download was cancelled.')
    else:
        provision(spec, archive)
    destination = root / f'libvlc-{family}-{version}-{arch}'
    prefix = f'build/macos/osx-{arch}/' if sys.platform == 'darwin' else f'build/{arch}/'
    extract(archive, destination, prefix)
    if sys.platform == 'darwin':
        library = destination / 'lib/libvlc.dylib'
        plugins = destination / 'lib/vlc/plugins'
        _handles.append(ctypes.CDLL(str(destination / 'lib/libvlccore.dylib')))
    else:
        library = destination / 'libvlc.dll'
        plugins = destination / 'plugins'
        _handles.append(os.add_dll_directory(str(destination)))
    ctypes.CDLL(str(library))  # Fail here rather than python-vlc's process-exit path.
    return str(library), str(plugins)


def binding(*, interactive=False):
    global _binding
    if _binding is not None:
        return _binding
    library, plugins = runtime(interactive=interactive)
    os.environ['PYTHON_VLC_LIB_PATH'] = library
    if plugins:
        os.environ['PYTHON_VLC_MODULE_PATH'] = plugins
    import vlc
    if not vlc.libvlc_get_version().startswith(b'3.'):
        raise RuntimeError('Desktop video requires the supported LibVLC 3 runtime.')
    if sys.platform in PACKAGES and Path(vlc.dll._name).resolve() != Path(library).resolve():
        raise RuntimeError('A different LibVLC runtime was already loaded. Restart Logistics.')
    _binding = vlc
    return vlc
