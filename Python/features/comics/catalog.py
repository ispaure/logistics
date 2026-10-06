"""Incremental, disposable library metadata suggestions; never changes archives."""

from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .library import ComicDocument

LIST_FIELDS = frozenset(('Writer', 'Penciller', 'Inker', 'Colorist', 'Letterer',
                         'CoverArtist', 'Editor', 'Translator', 'Genre', 'Tags',
                         'Characters', 'Teams', 'Locations', 'StoryArc', 'SeriesGroup'))
VALUE_FIELDS = frozenset(('Publisher', 'Imprint', 'Format', 'Series', 'AlternateSeries',
                          'MainCharacterOrTeam'))
CATALOG_FIELDS = LIST_FIELDS | VALUE_FIELDS
DATA_DIRECTORY = 'LogisticsComicsData'


def split_values(text):
    """Comma-separated XML values; text-entry mode also accepts one per line."""
    return list(dict.fromkeys(value.strip() for value in text.replace('\r', '\n').replace('\n', ',').split(',')
                             if value.strip()))


def file_signature(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_dev, stat.st_ino]


class LibraryCatalog:
    VERSION = 1

    def __init__(self, root):
        self.root = Path(root).absolute()
        self.path = self.root / DATA_DIRECTORY / 'metadata.json'

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') != self.VERSION or not isinstance(data.get('files'), dict):
                return {}
            # Cache corruption is recoverable. Ignore invalid records individually.
            return {name: entry for name, entry in data['files'].items()
                    if isinstance(entry, dict) and isinstance(entry.get('signature'), list)
                    and isinstance(entry.get('fields'), dict)
                    and all(isinstance(value, str) for value in entry['fields'].values())}
        except (OSError, ValueError, AttributeError):
            return {}

    def refresh(self, cancelled=lambda: False):
        previous = self._read()
        current = {}
        errors = []
        parsed = 0
        def walk_error(error):
            raise error
        for directory, folders, names in os.walk(self.root, followlinks=False, onerror=walk_error):
            if cancelled():
                return None
            folders[:] = sorted(name for name in folders if name != DATA_DIRECTORY
                                and not name.startswith('.logistics-comic-')
                                and not (Path(directory) / name).is_symlink())
            for name in sorted(names):
                if cancelled():
                    return None
                path = Path(directory) / name
                if path.suffix.lower() != '.cbz' or path.is_symlink():
                    continue
                key = path.relative_to(self.root).as_posix()
                try:
                    signature = file_signature(path)
                    old = previous.get(key)
                    if old and old['signature'] == signature:
                        current[key] = old
                        continue
                    document = ComicDocument(path)
                    fields = {}
                    for field in CATALOG_FIELDS:
                        try:
                            fields[field] = document.info.get_field(field)
                        except ValueError:
                            continue  # Complex extension values remain in their original XML.
                    if signature != file_signature(path):
                        raise RuntimeError('Archive changed during indexing')
                    current[key] = {'signature': signature, 'metadata_sha256': hashlib.sha256(
                        document.info.to_bytes()).hexdigest(), 'fields': fields}
                    parsed += 1
                except Exception as error:
                    errors.append(f'{path}: {error}')
        if cancelled():
            return None
        values = defaultdict(set)
        for entry in current.values():
            for field, value in entry['fields'].items():
                if field in CATALOG_FIELDS:
                    values[field].update(split_values(value) if field in LIST_FIELDS else ([value] if value else []))
        suggestions = {field: sorted(items, key=lambda text: (text.casefold(), text))
                       for field, items in values.items()}
        payload = {'version': self.VERSION, 'files': current}
        try:
            if current != previous or not self.path.exists():
                if self.path.parent.is_symlink():
                    raise OSError('Cache directory is a symbolic link')
                self.path.parent.mkdir(parents=True, exist_ok=True)
                staged = None
                try:
                    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                            prefix='.metadata-', suffix='.tmp', delete=False) as stream:
                        staged = Path(stream.name)
                        json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(staged, self.path)
                finally:
                    if staged is not None:
                        staged.unlink(missing_ok=True)
        except OSError as error:
            errors.append(f'Suggestions available for this session; cache could not be saved: {error}')
        return {'suggestions': suggestions, 'count': len(current), 'parsed': parsed, 'errors': errors}
