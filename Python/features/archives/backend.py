"""Archive workspace operations. Workers use bounded streams and staged outputs."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import os
import shutil
import tarfile
import zipfile

from commonUtils.operations import check_cancelled
from commonUtils.streams import copy_stream, stream_signature
from commonUtils.zip_access import (open_archive, validate_members, create_archive,
                                    directory_entries, archive_manifest)


@dataclass(frozen=True)
class Entry:
    name: str
    size: int
    packed: int | None
    directory: bool
    modified: str
    encrypted: bool = False


@contextmanager
def reader(path, password=None):
    if zipfile.is_zipfile(path):
        with open_archive(path, password=password) as archive:
            validate_members(archive)
            yield archive, True
    else:
        with tarfile.open(path, 'r:*') as archive:
            validate_tar(archive)
            yield archive, False


def validate_tar(archive):
    seen, kinds = set(), {}
    import unicodedata
    for item in archive.getmembers():
        name = item.name.replace('\\', '/')
        path = PurePosixPath(name)
        if (not name or '\x00' in name or path.is_absolute() or '..' in path.parts
                or ':' in name or not path.parts or not (item.isfile() or item.isdir())):
            raise ValueError(f'Unsafe or unsupported TAR member: {item.name}')
        key = unicodedata.normalize('NFC', path.as_posix()).casefold()
        if key in seen:
            raise ValueError(f'Duplicate archive member: {item.name}')
        seen.add(key)
        kinds[key] = item.isdir()
    for name in kinds:
        for parent in PurePosixPath(name).parents:
            if parent.as_posix() in kinds and not kinds[parent.as_posix()]:
                raise ValueError(f'Archive file is also a directory: {parent}')


def entries(path, *, progress=lambda *args: None, cancelled=lambda: False):
    """Headers can be browsed without unlocking encrypted ZIP payloads."""
    result = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            validate_members(archive)
            for item in archive.infolist():
                check_cancelled(cancelled)
                result.append(Entry(item.filename.replace('\\', '/'), item.file_size,
                                    item.compress_size, item.is_dir(),
                                    '%04d-%02d-%02d %02d:%02d' % item.date_time[:5], bool(item.flag_bits & 1)))
    else:
        with tarfile.open(path, 'r:*') as archive:
            validate_tar(archive)
            for item in archive.getmembers():
                check_cancelled(cancelled)
                result.append(Entry(item.name.replace('\\', '/'), item.size, None, item.isdir(),
                                    datetime.fromtimestamp(item.mtime).strftime('%Y-%m-%d %H:%M')))
    return tuple(result)


def _members(archive, is_zip):
    return archive.infolist() if is_zip else archive.getmembers()


def _name(item, is_zip):
    return (item.filename if is_zip else item.name).replace('\\', '/')


def _directory(item, is_zip):
    return item.is_dir() if is_zip else item.isdir()


def _stream(archive, item, is_zip):
    return archive.open(item) if is_zip else archive.extractfile(item)


def extract(path, destination, *, selected=None, password=None,
            progress=lambda *args: None, cancelled=lambda: False):
    """Extract into a NEW folder; never overwrite existing user files.

    Validate every member, stage the complete selection, then reserve the output
    with exclusive mkdir. Cancellation or bad passwords leave no partial output.
    """
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Choose a new destination folder; existing folders are never overwritten.')
    selection = tuple(selected) if selected is not None else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.logistics-extract-', dir=destination.parent) as temp:
        stage = Path(temp) / 'contents'
        stage.mkdir()
        with reader(path, password) as (archive, is_zip):
            members = [item for item in _members(archive, is_zip)
                       if selection is None or any(_name(item, is_zip).rstrip('/') == name.rstrip('/')
                           or _name(item, is_zip).startswith(name.rstrip('/') + '/') for name in selection)]
            if not members and selection:
                raise ValueError('No selected entries found')
            total = sum(item.file_size if is_zip else item.size for item in members)
            done = 0
            for item in members:
                check_cancelled(cancelled)
                name = _name(item, is_zip)
                target = stage / name
                if not target.resolve().is_relative_to(stage.resolve()):
                    raise ValueError(f'Unsafe archive member: {name}')
                if _directory(item, is_zip):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    def advanced(size):
                        nonlocal done
                        done += size
                        progress(done, total, f'Extracting {name}')
                    with _stream(archive, item, is_zip) as source, target.open('xb') as output:
                        copy_stream(source, output, cancelled=cancelled, progress=advanced)
                    # Retain executable bits for Unix scripts, without restoring
                    # ownership, setuid bits or restrictive archive permissions.
                    mode = (item.external_attr >> 16) if is_zip and item.create_system == 3 else (item.mode if not is_zip else 0)
                    os.chmod(target, (target.stat().st_mode & 0o777) | (mode & 0o111))
                    try:
                        stamp = datetime(*item.date_time).timestamp() if is_zip else item.mtime
                        os.utime(target, (stamp, stamp))
                    except (ValueError, OSError, OverflowError):
                        pass
        check_cancelled(cancelled)
        destination.mkdir()  # exclusive reservation, even against concurrent creation
        try:
            for child in stage.iterdir():
                os.replace(child, destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination


def test_archive(path, *, password=None, progress=lambda *args: None, cancelled=lambda: False):
    if zipfile.is_zipfile(path):
        return len(archive_manifest(path, password=password, progress=progress, cancelled=cancelled))
    count, done = 0, 0
    with reader(path) as (archive, is_zip):
        members = archive.getmembers()
        total = sum(item.size for item in members)
        for item in members:
            check_cancelled(cancelled)
            if item.isfile():
                def advanced(size):
                    nonlocal done
                    done += size
                    progress(done, total, f'Reading {item.name}')
                with archive.extractfile(item) as stream:
                    stream_signature(stream, cancelled=cancelled, progress=advanced)
            count += 1
    return count


def preview(path, name, *, password=None, progress=lambda *args: None, cancelled=lambda: False):
    """Read at most 256 KiB; never execute or launch an archive member."""
    with reader(path, password) as (archive, is_zip):
        item = next(item for item in _members(archive, is_zip) if _name(item, is_zip) == name)
        check_cancelled(cancelled)
        with _stream(archive, item, is_zip) as stream:
            data = stream.read(256 * 1024 + 1)
    truncated = len(data) > 256 * 1024
    data = data[:256 * 1024]
    if b'\x00' in data:
        return 'Binary file. Extract this entry to open it in another application.'
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return 'Preview is available for UTF-8 text. Extract this entry to open it.'
    return text + ('\n\n[Preview limited to 256 KiB]' if truncated else '')


def create(sources, destination, *, format='zip', password=None, level=6,
           progress=lambda *args: None, cancelled=lambda: False):
    if format == 'zip':
        return create_archive(sources, destination, password=password,
                              compression=zipfile.ZIP_STORED if level == 0 else zipfile.ZIP_DEFLATED,
                              compresslevel=None if level == 0 else level, progress=progress, cancelled=cancelled)
    if password:
        raise ValueError('Encryption is available for ZIP only')
    modes = {'tar': 'w', 'tar.gz': 'w:gz', 'tar.xz': 'w:xz'}
    mode = modes[format]
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Output already exists: {destination}')
    sources = tuple(dict.fromkeys(Path(source).absolute() for source in sources))
    if not sources:
        raise ValueError('Select at least one source')
    plan = []
    for source in sources:
        if source.is_symlink() or not source.exists():
            raise ValueError(f'Source must exist and cannot be a symbolic link: {source}')
        if source == destination or (source.is_dir() and destination.resolve().is_relative_to(source.resolve())):
            raise ValueError('The output archive must be outside the selected sources')
        if any(other != source and other.is_dir() and source.is_relative_to(other) for other in sources):
            continue
        plan.extend(directory_entries(source, cancelled=cancelled) if source.is_dir() else [(source, source.name)])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.logistics-archive-', dir=destination.parent) as temp:
        staged = Path(temp) / 'archive'
        expected = {}
        signatures = {source: source.stat() for source, name in plan}
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        total = sum(source.stat().st_size for source, name in plan if source.is_file())
        done = 0
        with tarfile.open(staged, mode) as archive:
            for source, name in plan:
                check_cancelled(cancelled)
                if source.is_symlink() or identity(source.stat()) != identity(signatures[source]):
                    raise ValueError(f'Source changed while archiving: {source}')
                info = archive.gettarinfo(str(source), arcname=name)
                if not (info.isfile() or info.isdir()):
                    raise ValueError(f'Cannot archive a nonregular file: {source}')
                if info.isfile():
                    # Hash and add from the same descriptor, then verify staged bytes.
                    with source.open('rb') as stream:
                        expected[name] = stream_signature(stream, cancelled=cancelled)
                        stream.seek(0)
                        class CancellableStream:
                            def read(self, size):
                                nonlocal done
                                check_cancelled(cancelled)
                                data = stream.read(size)
                                done += len(data)
                                progress(done, total, f'Creating {name}')
                                return data
                        archive.addfile(info, CancellableStream())
                else:
                    archive.addfile(info)
        with reader(staged) as (archive, _):
            for item in archive.getmembers():
                if item.isfile():
                    with archive.extractfile(item) as stream:
                        if stream_signature(stream, cancelled=cancelled) != expected[item.name]:
                            raise ValueError('Archive verification failed')
        for source, before in signatures.items():
            if source.is_symlink() or identity(source.stat()) != identity(before):
                raise ValueError(f'Source changed while archiving: {source}')
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        check_cancelled(cancelled)
        os.link(staged, destination)
    return destination


def update_zip(path, *, sources=(), remove=(), password=None,
               progress=lambda *args: None, cancelled=lambda: False):
    """Rebuild a ZIP, verify decrypted hashes, then replace it atomically.

    Additions cannot silently replace an entry. Removing a directory removes its
    descendants. Mixed encrypted/plain ZIPs are rejected rather than changing
    their protection policy. A changed source archive aborts publication.
    """
    from commonUtils.zip_access import authenticate, copy_member_info, _name_key
    path = Path(path).absolute()
    if path.is_symlink():
        raise ValueError('Cannot edit an archive through a symbolic link')
    before = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    authenticate(path, password, all_members=True, for_rewrite=True, cancelled=cancelled)
    original = archive_manifest(path, password=password, progress=progress, cancelled=cancelled)
    retained = {name: digest for name, digest in original.items()
                if not any(name.replace('\\', '/').rstrip('/') == target.rstrip('/')
                           or name.replace('\\', '/').startswith(target.rstrip('/') + '/') for target in remove)}
    with TemporaryDirectory(prefix='.logistics-edit-', dir=path.parent) as temp:
        extra = Path(temp) / 'additions.zip'
        if sources:
            create_archive(sources, extra, progress=progress, cancelled=cancelled)
            additions = archive_manifest(extra, cancelled=cancelled)
        else:
            additions = {}
        names = {_name_key(name) for name in retained}
        if any(_name_key(name) in names for name in additions):
            raise ValueError('An added entry already exists. Remove it first or choose a different source name.')
        expected = retained | additions
        staged = Path(temp) / 'result.zip'
        with open_archive(staged, 'w', password=password) as output:
            for source_path, secret, included in ((path, password, retained), (extra, None, additions)):
                if not included:
                    continue
                with open_archive(source_path, password=secret) as incoming:
                    if source_path == path:
                        output.comment = incoming.comment
                    for item in incoming.infolist():
                        if item.filename not in included:
                            continue
                        check_cancelled(cancelled)
                        progress(0, 0, f'Rebuilding {item.filename}')
                        info = copy_member_info(item, output)
                        if item.is_dir():
                            output.writestr(info, b'')
                        else:
                            with incoming.open(item) as source, output.open(info, 'w', force_zip64=True) as target:
                                copy_stream(source, target, cancelled=cancelled)
        if archive_manifest(staged, password=password, progress=progress, cancelled=cancelled) != expected:
            raise ValueError('Archive verification failed; original archive was kept')
        if path.is_symlink() or identity(path.stat()) != identity(before):
            raise ValueError('The archive changed during editing; original archive was kept')
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        os.chmod(staged, before.st_mode & 0o777)
        check_cancelled(cancelled)
        os.replace(staged, path)
    return path


def preview_image(path, name, *, password=None, progress=lambda *args: None, cancelled=lambda: False):
    """Decode one bounded image frame into a thumbnail for the GUI thread."""
    from io import BytesIO
    from PIL import Image, ImageOps
    with reader(path, password) as (archive, is_zip):
        item = next(item for item in _members(archive, is_zip) if _name(item, is_zip) == name)
        size = item.file_size if is_zip else item.size
        if size > 16 * 1024 * 1024:
            return 'Image preview is limited to 16 MiB. Extract this file to open it.'
        with _stream(archive, item, is_zip) as stream:
            data = stream.read(16 * 1024 * 1024 + 1)
    check_cancelled(cancelled)
    if len(data) > 16 * 1024 * 1024:
        return 'Image preview is limited to 16 MiB. Extract this file to open it.'
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 25_000_000:
            return 'Image preview is limited to 25 megapixels. Extract this file to open it.'
        source.thumbnail((1000, 1000))
        image = ImageOps.exif_transpose(source).convert('RGBA')
        output = BytesIO()
        image.save(output, format='PNG')
    check_cancelled(cancelled)
    return output.getvalue()
