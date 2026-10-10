"""Incremental, disposable library metadata suggestions; never changes archives."""

from collections import defaultdict
import os
from pathlib import Path

from commonUtils.formats.jsonType import JSONFile

from .library import ComicDocument
from commonUtils.archives.zip_access import is_encrypted

LIST_FIELDS = frozenset(('Writer', 'Penciller', 'Inker', 'Colorist', 'Letterer',
                         'CoverArtist', 'Editor', 'Translator', 'Genre', 'Tags',
                         'Characters', 'Teams', 'Locations', 'StoryArc', 'SeriesGroup'))
VALUE_FIELDS = frozenset(('Publisher', 'Imprint', 'Format'))
CATALOG_FIELDS = LIST_FIELDS | VALUE_FIELDS
DATA_DIRECTORY = 'LogisticsComicsData'


def normalize_value(text):
    """Suggestions are single-line text with consistent Unicode whitespace."""
    return ' '.join(text.split())


def split_values(text):
    """Comma-separated XML values; text-entry mode also accepts one per line."""
    return list(dict.fromkeys(normalize_value(value) for value in text.replace('\r', '\n').replace('\n', ',').split(',')
                             if normalize_value(value)))


def file_signature(path):
    stat = path.stat()
    return [stat.st_mtime_ns, stat.st_size]


class LibraryCatalog:
    VERSION = 3

    def __init__(self, root):
        self.root = Path(root).absolute()
        self.path = self.root / DATA_DIRECTORY / 'metadata.json'

    @staticmethod
    def _field_values(fields):
        result = {}
        for field in CATALOG_FIELDS:
            value = fields.get(field, '')
            if field in VALUE_FIELDS:
                value = normalize_value(value)
            items = split_values(value) if field in LIST_FIELDS else ([value] if value else [])
            if items:
                result[field] = items
        return result

    def _read(self):
        try:
            data = JSONFile(self.path).read_json()
            version = data.get('version')
            if version not in (1, 2, self.VERSION) or not isinstance(data.get('files'), dict):
                return {}, True
            previous = {}
            for name, entry in data['files'].items():
                try:
                    if version == 1:
                        signature = entry['signature']
                        fields = entry['fields']
                        if not all(isinstance(value, str) for value in fields.values()):
                            continue
                        previous[name] = {'signature': [signature[1], signature[0]],
                                          'fields': self._field_values(fields)}
                    else:
                        modified, size, references = entry
                        if type(modified) is not int or type(size) is not int or not isinstance(references, dict):
                            continue
                        fields = {}
                        for field, indices in references.items():
                            if field not in CATALOG_FIELDS:
                                continue
                            pool = data['suggestions'][field]
                            if not isinstance(indices, list) or not isinstance(pool, list):
                                raise ValueError('Invalid suggestion references')
                            if any(type(index) is not int or index < 0 or index >= len(pool) for index in indices):
                                raise ValueError('Invalid suggestion index')
                            items = [pool[index] for index in indices]
                            if any(not isinstance(value, str) or not value for value in items):
                                raise ValueError('Invalid suggestion value')
                            items = list(dict.fromkeys(normalize_value(value) for value in items
                                                        if normalize_value(value)))
                            if items:
                                fields[field] = items
                        previous[name] = {'signature': [modified, size], 'fields': fields}
                except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                    continue  # Invalid records are rebuilt independently.
            return previous, version != self.VERSION or len(previous) != len(data['files'])
        except (OSError, ValueError, AttributeError):
            return {}, True

    def _encode(self, files):
        values = defaultdict(set)
        for entry in files.values():
            for field, items in entry['fields'].items():
                values[field].update(items)
        suggestions = {field: sorted(items, key=lambda text: (text.casefold(), text))
                       for field, items in values.items()}
        indices = {field: {value: index for index, value in enumerate(items)}
                   for field, items in suggestions.items()}
        # Each suggestion is stored once. Files only retain modification time,
        # size and references needed to remove obsolete values on later refreshes.
        encoded = {name: [*entry['signature'],
                          {field: [indices[field][value] for value in items]
                           for field, items in entry['fields'].items()}]
                   for name, entry in files.items()}
        return {'version': self.VERSION, 'suggestions': suggestions, 'files': encoded}

    def refresh(self, cancelled=lambda: False):
        previous, needs_write = self._read()
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
                    # Never persist decrypted metadata from protected comics.
                    if is_encrypted(path):
                        continue
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
                    current[key] = {'signature': signature, 'fields': self._field_values(fields)}
                    parsed += 1
                except Exception as error:
                    errors.append(f'{path}: {error}')
        if cancelled():
            return None
        payload = self._encode(current)
        suggestions = payload['suggestions']
        try:
            if current != previous or needs_write:
                if self.path.parent.is_symlink():
                    raise OSError('Cache directory is a symbolic link')
                JSONFile(self.path).write_json(payload, compact=True, sort_keys=True)
        except OSError as error:
            errors.append(f'Suggestions available for this session; cache could not be saved: {error}')
        return {'suggestions': suggestions, 'count': len(current), 'parsed': parsed, 'errors': errors}
