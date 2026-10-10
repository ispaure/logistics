"""Plan a dedicated book mirror, stage copies, then remove obsolete exports."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from commonUtils.filesystem.directories import Directory
from . import metadata


Signature = tuple[int, int, int, int]


def signature(path: Path) -> Signature:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def checksum(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def path_key(path: Path) -> str:
    # Readers may use case-insensitive filesystems even when the library does not.
    return metadata.normalize_path(path).casefold()


def require_regular_path(path: Path) -> None:
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError(f'Export paths cannot traverse links: {parent}')


@dataclass(frozen=True)
class ExportFile:
    source: Path
    destination: Path
    source_signature: Signature
    destination_signature: Signature | None
    checksum: str
    needs_copy: bool


@dataclass(frozen=True)
class ExportPlan:
    destination: Path
    destination_anchor: Path
    destination_identity: tuple[int, int]
    files: tuple[ExportFile, ...]
    obsolete: tuple[tuple[Path, Signature], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ExportResult:
    copied: int
    updated: int
    deleted: int


def build_export_plan(source: Path, destination: Path, extensions) -> ExportPlan:
    """Read and validate the whole mirror before creating or deleting any file."""
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if source.is_symlink() or destination.is_symlink() or source.is_junction() or destination.is_junction():
        raise ValueError('Library and export roots cannot be links')
    source, destination = source.resolve(), destination.resolve()
    require_regular_path(source)
    require_regular_path(destination)
    if not source.is_dir() or not (source / 'metadata.db').is_file():
        raise ValueError(f'Not a Calibre library: {source}')
    if destination.exists() and not destination.is_dir():
        raise ValueError(f'Export destination is not a directory: {destination}')
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and export destination cannot overlap')
    if isinstance(extensions, str):
        extensions = [extensions]
    extensions = {extension.lower().lstrip('.') for extension in extensions}
    if not extensions or any(not extension or not extension.isalnum() for extension in extensions):
        raise ValueError('Choose at least one valid book extension')

    existing = _existing_exports(destination)
    anchor = destination
    while not anchor.exists():
        anchor = anchor.parent
    destination_identity = signature(anchor)[:2]
    expected, warnings = {}, []
    for path, relative_path in _book_exports(source, extensions, warnings):
        require_regular_path(path)
        if not path.is_file():
            raise ValueError(f'Not a regular book file: {path}')
        target = destination / relative_path
        require_regular_path(target)
        if target.exists() and not target.is_file():
            raise ValueError(f'Export filename is occupied by a directory: {target}')
        key = path_key(target)
        if key in expected:
            raise ValueError(f'Export filename collision: {expected[key].source} and {path}')
        target = existing.get(key, target)
        before = signature(path)
        digest = checksum(path)
        if signature(path) != before:
            raise RuntimeError(f'Book changed during export planning: {path}')
        target_signature = signature(target) if target.exists() else None
        needs_copy = target_signature is None or before[2] != target_signature[2] or checksum(target) != digest
        expected[key] = ExportFile(path, target, before, target_signature, digest, needs_copy)
    obsolete = tuple((path, signature(path)) for key, path in existing.items() if key not in expected)
    return ExportPlan(destination, anchor, destination_identity,
                      tuple(expected.values()), obsolete, tuple(warnings))


def _existing_exports(destination: Path) -> dict[str, Path]:
    """Read the dedicated mirror without following linked entries."""
    existing = {}
    if destination.exists():
        for root, directories, names in os.walk(destination, onerror=_raise_walk_error):
            for name in (*directories, *names):
                require_regular_path(Path(root) / name)
            for name in names:
                path = Path(root) / name
                if not path.is_file():
                    raise ValueError(f'Unsupported export entry: {path}')
                key = path_key(path)
                if key in existing:
                    raise ValueError(f'Ambiguous export filenames: {existing[key]} and {path}')
                existing[key] = path

    return existing


def _book_exports(source: Path, extensions: set[str], warnings: list[str]):
    """Yield book files and relative export names in deterministic order."""
    for author in sorted(source.iterdir()):
        if not author.is_dir():
            continue
        require_regular_path(author)
        for book in sorted(author.iterdir()):
            if not book.is_dir():
                continue
            require_regular_path(book)
            files = sorted(path for path in book.iterdir() if path.suffix[1:].lower() in extensions)
            if not files:
                warnings.append(f'No supported format found for {author.name} / {book.name}')
                continue
            require_regular_path(book / 'metadata.opf')
            book_name = metadata.get_metadata_book_name(Directory(book))
            if not book_name:
                book_name = metadata.sanitize_file_name(metadata.get_clean_book_name(Directory(book)))
                warnings.append(f'Using folder name for {author.name} / {book.name}')
            if not book_name:
                raise ValueError(f'No usable export name for {book}')
            for path in files:
                yield path, Path(author.name) / f'{book_name}.{path.suffix[1:].lower()}'


def _raise_walk_error(error):
    raise error


def _validate_plan(plan: ExportPlan) -> None:
    _validate_destination(plan)
    require_regular_path(plan.destination)
    for entry in plan.files:
        require_regular_path(entry.source)
        require_regular_path(entry.destination)
        if signature(entry.source) != entry.source_signature:
            raise RuntimeError(f'Book changed since export planning: {entry.source}')
        current = signature(entry.destination) if entry.destination.exists() else None
        if current != entry.destination_signature:
            raise RuntimeError(f'Export changed since planning: {entry.destination}')
    for path, previous in plan.obsolete:
        require_regular_path(path)
        if signature(path) != previous:
            raise RuntimeError(f'Obsolete export changed since planning: {path}')


def _validate_destination(plan: ExportPlan) -> None:
    """Stop if the destination directory/device was removed or replaced."""
    require_regular_path(plan.destination_anchor)
    if signature(plan.destination_anchor)[:2] != plan.destination_identity:
        raise RuntimeError(f'Export destination was replaced: {plan.destination_anchor}')


def execute_export_plan(plan: ExportPlan) -> ExportResult:
    """Stage all copies before replacing files; prune only after copies succeed."""
    _validate_plan(plan)
    staged = []
    try:
        for entry in plan.files:
            if not entry.needs_copy:
                continue
            _validate_destination(plan)
            require_regular_path(entry.destination)
            entry.destination.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(prefix='.logistics-calibre-', dir=entry.destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
            staged.append((entry, temporary))
            shutil.copy2(entry.source, temporary)
            if checksum(temporary) != entry.checksum or signature(entry.source) != entry.source_signature:
                raise RuntimeError(f'Book changed or copy failed: {entry.source}')
        _validate_plan(plan)
        for entry, temporary in staged:
            _validate_destination(plan)
            require_regular_path(entry.destination)
            current = signature(entry.destination) if entry.destination.exists() else None
            if current != entry.destination_signature:
                raise RuntimeError(f'Export changed during replacement: {entry.destination}')
            os.replace(temporary, entry.destination)
        for path, previous in plan.obsolete:
            _validate_destination(plan)
            require_regular_path(path)
            if signature(path) != previous:
                raise RuntimeError(f'Obsolete export changed during copying: {path}')
            path.unlink()
        if plan.destination.exists():
            for root, directories, _files in os.walk(plan.destination, topdown=False, onerror=_raise_walk_error):
                for name in directories:
                    _validate_destination(plan)
                    path = Path(root) / name
                    require_regular_path(path)
                    if not any(path.iterdir()):
                        path.rmdir()
    finally:
        try:
            _validate_destination(plan)
        except (OSError, RuntimeError, ValueError):
            pass  # A lost device's temporary files can be cleaned on a later export.
        else:
            for _entry, temporary in staged:
                temporary.unlink(missing_ok=True)
    copied = sum(entry.destination_signature is None for entry, _temporary in staged)
    return ExportResult(copied, len(staged) - copied, len(plan.obsolete))
