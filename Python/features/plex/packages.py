"""Stage Plex packages and extracted data before replacing existing files."""

from pathlib import Path, PurePosixPath
import os
import shutil
import stat
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from commonUtils.osUtils import OS

REGISTRY_KEY = r'HKEY_CURRENT_USER\Software\Plex, Inc.\Plex Media Server'
PLIST_NAME = 'com.plexapp.plexmediaserver.plist'


def archive_name(platform):
    names = {OS.WIN: 'pms_data.7z.001', OS.MAC: 'pms_data_mac.zip', OS.LINUX: 'pms_data_linux.zip'}
    try:
        return names[platform]
    except KeyError:
        raise ValueError('Plex packaging is unsupported on this platform.') from None


def _is_link(path):
    return path.is_symlink() or path.is_junction()


def _raise_scan_error(error):
    raise error


def _tree_paths(root):
    """Yield validated entries; never silently omit an unreadable subtree."""
    if _is_link(root) or not root.is_dir():
        raise ValueError(f'Expected an ordinary directory: {root}')
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=_raise_scan_error):
        for name in sorted((*dirs, *files)):
            path = Path(directory, name)
            if _is_link(path) or not (path.is_dir() or path.is_file()):
                raise ValueError(f'Linked or special package content is unsupported: {path}')
            yield path


def _validate_tree(root):
    for _path in _tree_paths(root):
        pass


def _validate_locations(source, destination):
    for path in (source, destination):
        if any(_is_link(parent) for parent in (path, *path.parents)):
            raise ValueError(f'Linked package/data locations are unsupported: {path}')
    source, destination = source.resolve(), destination.resolve()
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('Plex data and package locations must not overlap.')


def _run(arguments, **kwargs):
    subprocess.run([str(value) for value in arguments], check=True, **kwargs)


def package_data(source: Path, destination: Path, platform, seven_zip=None, preferences=None):
    """Keep existing packages until all new archive/settings files are staged."""
    source, destination = Path(source), Path(destination)
    archive_name(platform)
    _validate_locations(source, destination)
    _validate_tree(source)
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.logistics-plex-', dir=destination) as temporary:
        staging = Path(temporary)
        if platform == OS.WIN:
            if seven_zip is None or not Path(seven_zip).is_file():
                raise FileNotFoundError('The bundled 7-Zip executable was not found.')
            _run(['reg', 'export', REGISTRY_KEY, staging / 'pms_registry.reg', '/y'])
            _run([seven_zip, 'a', '-y', '-mx1', '-v5000000000', staging / 'pms_data.7z', './*'], cwd=source)
            if not (staging / archive_name(platform)).is_file():
                raise RuntimeError('7-Zip did not produce the expected split archive.')
            _run([seven_zip, 't', staging / archive_name(platform)])
            if not (staging / 'pms_registry.reg').is_file():
                raise RuntimeError('Registry export did not produce a settings file.')
        else:
            archive = staging / archive_name(platform)
            with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=1, allowZip64=True) as output:
                output.write(source, 'Plex Media Server/')
                # Scan again while copying; permissions or entries may have changed.
                for path in _tree_paths(source):
                    output.write(path, (Path('Plex Media Server') / path.relative_to(source)).as_posix())
            with ZipFile(archive) as output:
                bad_file = output.testzip()
                if bad_file:
                    raise ValueError(f'Archive verification failed: {bad_file}')
            if platform == OS.MAC and preferences is not None:
                shutil.copy2(preferences, staging / PLIST_NAME)
        outputs = sorted(staging.iterdir())
        names = {path.name for path in outputs}
        obsolete = [path for path in destination.iterdir()
                    if path.is_file() and path.name not in names
                    and platform == OS.WIN and path.name.startswith('pms_data.7z')]
        for path in outputs:
            target = destination / path.name
            if _is_link(target) or (target.exists() and not target.is_file()):
                raise ValueError(f'Package destination is not a regular file: {target}')
        for path in outputs:
            os.replace(path, destination / path.name)
        for path in obsolete:
            path.unlink()


def _extract_zip(archive, staging):
    with ZipFile(archive) as source:
        for member in source.infolist():
            name = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if ('\\' in member.filename or ':' in member.filename or name.is_absolute()
                    or '..' in name.parts or not name.parts or name.parts[0] != 'Plex Media Server'
                    or stat.S_ISLNK(mode)):
                raise ValueError(f'Invalid Plex archive member: {member.filename}')
        # Reading every member during extraction checks its CRC before replacement.
        source.extractall(staging)
        if os.name != 'nt':
            # Restore children before restricting access to their parent folders.
            for member in sorted(source.infolist(), key=lambda value: len(PurePosixPath(value.filename).parts), reverse=True):
                mode = member.external_attr >> 16
                if member.create_system == 3 and mode:
                    path = Path(staging, *PurePosixPath(member.filename).parts)
                    path.chmod(mode & 0o777)


def restore_data(package: Path, destination: Path, platform, seven_zip=None, preferences=None):
    """Extract first, then swap data directories; retain previous data for recovery."""
    package, destination = Path(package), Path(destination)
    archive = package / archive_name(platform)
    _validate_locations(package, destination)
    if not archive.is_file() or _is_link(archive):
        raise FileNotFoundError(f'Plex archive not found: {archive}')
    if destination.exists():
        _validate_tree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.logistics-plex-restore-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        if platform == OS.WIN:
            if seven_zip is None or not Path(seven_zip).is_file():
                raise FileNotFoundError('The bundled 7-Zip executable was not found.')
            extracted = staging / 'Plex Media Server'
            extracted.mkdir()
            _run([seven_zip, 'x', '-y', archive, f'-o{extracted}'])
        else:
            _extract_zip(archive, staging)
            extracted = staging / 'Plex Media Server'
        _validate_tree(extracted)
        if preferences is not None:
            preferences = Path(preferences)
            if _is_link(preferences) or not preferences.is_file():
                raise ValueError(f'Invalid preferences file: {preferences}')
            if platform == OS.WIN:
                _run(['reg', 'import', preferences])
            elif platform == OS.MAC:
                target = Path.home() / 'Library/Preferences' / PLIST_NAME
                target.parent.mkdir(parents=True, exist_ok=True)
                if _is_link(target):
                    raise ValueError(f'Linked preferences destination: {target}')
                shutil.copy2(preferences, target)
        previous = None
        if destination.exists():
            previous = destination.with_name(f'{destination.name}.previous-{uuid4().hex[:8]}')
            os.replace(destination, previous)
        try:
            os.replace(extracted, destination)
        except OSError:
            if previous is not None:
                os.replace(previous, destination)
            raise
    return previous
