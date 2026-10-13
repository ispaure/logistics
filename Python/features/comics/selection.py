"""Resolve file/folder selections and apply explicit metadata changes to CBZs."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from .archive_io import archive_unchanged
from .library import ComicDocument
from commonUtils.archives.zip_access import ArchivePasswordError


def normalize_targets(targets):
    if isinstance(targets, (str, Path)):
        targets = [targets]
    normalized = tuple(dict.fromkeys(Path(os.path.abspath(path)) for path in targets))
    if not normalized:
        raise ValueError('Select at least one CBZ file or folder')
    return normalized


def selected_comics(targets, recursive=True):
    """Resolve CBZs once without following links; optionally scan nested folders."""
    found = {}
    def add(path):
        if path.suffix.lower() == '.cbz' and not path.is_symlink() and path.is_file():
            canonical = path.resolve()
            found.setdefault(canonical, path)
    def scan_error(error):
        raise error
    targets = normalize_targets(targets)
    for path in targets:
        if path.is_symlink():
            raise ValueError(f'Symbolic links cannot be edited: {path}')
    # Recursive roots cover children; shallow scans must retain explicit children.
    folders = [path for path in targets if path.is_dir() and not path.is_symlink()]
    roots = [path for path in targets
             if not recursive or not any(parent != path and parent in path.parents for parent in folders)]
    for path in roots:
        if path.is_symlink():
            raise ValueError(f'Symbolic links cannot be edited: {path}')
        if path.is_dir():
            for root, directories, files in os.walk(path, followlinks=False, onerror=scan_error):
                directories[:] = (sorted(name for name in directories if not (Path(root) / name).is_symlink())
                                  if recursive else [])
                for name in sorted(files):
                    add(Path(root) / name)
        elif path.is_file() and path.suffix.lower() == '.cbz':
            add(path)
        else:
            raise ValueError(f'Select existing CBZ files or folders: {path}')
    if not found:
        raise ValueError('The selection contains no CBZ files')
    return tuple(found.values())


def selected_provider_comics(source, targets):
    """Resolve private ZIP/CBZ files and folders through their provider only."""
    found, seen = {}, set()
    pending = [source.entry(path) for path in normalize_targets(targets)]
    entries = 0
    while pending:
        row = pending.pop()
        relative = source.relative(row['path'])
        if relative in seen:
            continue
        seen.add(relative)
        entries += 1
        if entries > 10000:
            raise ValueError('Select fewer folders: comic metadata selections are limited to 10,000 entries.')
        if row['directory']:
            pending.extend(source.list(relative))
        elif Path(relative).suffix.lower() in {'.cbz', '.zip'}:
            if Path(relative).suffix.lower() == '.zip':
                import zipfile
                from .pages import IMAGE_TYPES
                with source.open(relative) as stream, zipfile.ZipFile(stream) as archive:
                    if not any(not item.is_dir() and Path(item.filename).suffix.lower() in IMAGE_TYPES
                               and '__MACOSX' not in Path(item.filename).parts
                               and not Path(item.filename).name.startswith('._') for item in archive.infolist()):
                        continue
            found[relative] = source.root / relative
    if not found:
        raise ValueError('The selection contains no comic ZIP or CBZ files')
    return tuple(found[key] for key in sorted(found))


@dataclass
class SaveResult:
    saved: list[Path] = field(default_factory=list)
    failed: dict[Path, str] = field(default_factory=dict)


class ComicSelection:
    """A fixed snapshot of the selected comics, never silently expanded on save."""

    def __init__(self, targets, *, password=None, source=None):
        self.targets = normalize_targets(targets)
        if source is None:
            paths = selected_comics(self.targets)
            folders = any(target.is_dir() for target in self.targets)
        elif hasattr(source, 'entry'):
            paths = selected_provider_comics(source, self.targets)
            folders = any(source.entry(target)['directory'] for target in self.targets)
        else:
            paths, folders = self.targets, False
        bulk = len(paths) > 1 or folders
        for path in paths:
            if source is None and path.stat().st_nlink > 1:
                raise ValueError(f'Hard-linked CBZs need independent copies before editing: {path}')
        self.documents = []
        self.load_failures = {}
        for path in paths:
            try:
                self.documents.append(ComicDocument(path, password=password, source=source))
            except Exception as error:
                if isinstance(error, ArchivePasswordError) and bulk:
                    self.load_failures[path] = str(error)
                    continue
                raise ValueError(f'Cannot load {path}: {error}') from error
        if not self.documents:
            details = '\n'.join(f'{path}: {message}' for path, message in self.load_failures.items())
            raise ValueError(f'No selected comics could be unlocked:\n{details}')

    def field_values(self, fields):
        return [{name: document.info.get_field(name) for name in fields}
                for document in self.documents]

    def validate_changes(self, changes):
        # Validate every archive before writing the first. Ambiguous XML or
        # concurrent changes must not leave a preventable partial batch.
        for document in self.documents:
            document.prepare_metadata(changes)
            if not document.unchanged():
                raise RuntimeError(f'Comic changed since loading: {document.path}. Reload before saving.')

    def save(self, changes):
        self.validate_changes(changes)
        result = SaveResult(failed=dict(self.load_failures))
        for document in self.documents:
            try:
                document.save(changes)
                result.saved.append(document.path)
            except Exception as error:
                result.failed[document.path] = str(error)
        return result
