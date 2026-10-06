"""Resolve file/folder selections and apply explicit metadata changes to CBZs."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from .archive_io import archive_unchanged
from .library import ComicDocument


def normalize_targets(targets):
    if isinstance(targets, (str, Path)):
        targets = [targets]
    return tuple(dict.fromkeys(Path(path).absolute() for path in targets))


def selected_comics(targets):
    """Include folders recursively, without following links or editing a CBZ twice."""
    found = {}
    def add(path):
        if path.suffix.lower() == '.cbz' and not path.is_symlink() and path.is_file():
            snapshot = path.stat()
            found.setdefault((snapshot.st_dev, snapshot.st_ino), path)
    def scan_error(error):
        raise error
    for path in normalize_targets(targets):
        if path.is_symlink():
            raise ValueError(f'Symbolic links cannot be edited: {path}')
        if path.is_dir():
            for root, directories, files in os.walk(path, followlinks=False, onerror=scan_error):
                directories[:] = sorted(name for name in directories if not (Path(root) / name).is_symlink())
                for name in sorted(files):
                    add(Path(root) / name)
        elif path.is_file() and path.suffix.lower() == '.cbz':
            add(path)
        else:
            raise ValueError(f'Select existing CBZ files or folders: {path}')
    if not found:
        raise ValueError('The selection contains no CBZ files')
    return tuple(found.values())


@dataclass
class SaveResult:
    saved: list[Path] = field(default_factory=list)
    failed: dict[Path, str] = field(default_factory=dict)


class ComicSelection:
    """A fixed snapshot of the selected comics, never silently expanded on save."""

    def __init__(self, targets):
        self.targets = normalize_targets(targets)
        self.documents = [ComicDocument(path) for path in selected_comics(self.targets)]

    def field_values(self, fields):
        return [{name: document.info.get_field(name) for name in fields}
                for document in self.documents]

    def validate_changes(self, changes):
        # Validate every archive before writing the first. Ambiguous XML or
        # concurrent changes must not leave a preventable partial batch.
        for document in self.documents:
            document.prepare_metadata(changes)
            if not archive_unchanged(document.path, document.snapshot):
                raise RuntimeError(f'Comic changed since loading: {document.path}. Reload before saving.')

    def save(self, changes):
        self.validate_changes(changes)
        result = SaveResult()
        for document in self.documents:
            try:
                document.save(changes)
                result.saved.append(document.path)
            except Exception as error:
                result.failed[document.path] = str(error)
        return result
