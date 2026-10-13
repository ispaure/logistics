"""Feature-owned private data, atomic publication and optimistic revisions."""
from copy import deepcopy
from collections import Counter
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path

from commonUtils.persistence import atomic_write_bytes, atomic_write_json
from .screenshots import image_url
from .domain import base_url, identity, now, validate_conversation

MAX_FILE_BYTES = 32 * 1024 * 1024


class ConflictError(ValueError):
    pass


def folder_name(value):
    """Portable relative folder names; never allow escape from conversation storage."""
    if not isinstance(value, str):
        raise ValueError('Invalid conversation folder.')
    if value == '':
        return ''
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    for part in value.split('/'):
        if (not part or part in ('.', '..') or part.endswith((' ', '.')) or
                len(part.encode('utf-8')) > 255 or any(ord(c) < 32 or c in '<>:"\\|?*' for c in part) or
                part.split('.')[0].upper() in reserved):
            raise ValueError('Use relative folder names separated by /, without .., reserved names or special path characters.')
    return value


class Store:
    def __init__(self, root=None):
        if root is None:
            from features.preferences import preferences_path
            root = preferences_path().parent / 'LM'
        self.root = Path(root)
        self.folder = self.root / 'conversations'

    def _read(self, path):
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError('LM data exceeds the 32 MiB file limit; original preserved.')
        return json.loads(path.read_text(encoding='utf-8'))

    def lease(self, key):
        """Nonblocking OS-backed Qt lock with automatic dead-process recovery."""
        from PySide6.QtCore import QLockFile
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.folder_path(create=True)
        lock = QLockFile(str(self.folder / (identity(key) + '.lock')))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise ConflictError('This conversation is open in another Logistics window. Close it there, then reopen here.')
        return lock

    def folder_path(self, name='', *, create=False):
        name = folder_name(name)
        if create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.folder
        for part in ['', *(name.split('/') if name else [])]:
            if part:
                path /= part
            if path.is_symlink() or (path.exists() and not path.is_dir()):
                raise ValueError('Conversation folders must be real directories, not links or files.')
            if create:
                path.mkdir(exist_ok=True, mode=0o700)
        return path

    def folders(self):
        root = self.folder_path()
        result = []
        if root.exists():
            for parent, directories, _ in os.walk(root, followlinks=False):
                directories[:] = [name for name in directories
                                  if not (Path(parent) / name).is_symlink()]
                for name in list(directories):
                    relative = (Path(parent) / name).relative_to(root).as_posix()
                    try:
                        folder_name(relative)
                    except ValueError:
                        directories.remove(name)
                        continue
                    result.append(relative)
        return sorted(result, key=str.casefold)

    def create_folder(self, name):
        return self.folder_path(name, create=True)

    def _paths(self):
        for name in ['', *self.folders()]:
            for path in self.folder_path(name).glob('*.json'):
                if not path.is_symlink() and path.is_file():
                    yield path

    def path(self, key):
        identity(key)
        matches = [path for path in self._paths() if path.stem == key]
        if len(matches) > 1:
            raise ConflictError('Duplicate conversation IDs found in different folders; originals preserved. Remove the duplicate copy before reopening.')
        return matches[0] if matches else self.folder_path() / (key + '.json')

    def _load_path(self, path):
        data = validate_conversation(self._read(path))
        if data['id'] != path.stem:
            raise ValueError('Conversation file identity mismatch; original preserved.')
        # Actual placement wins, including legacy files moved manually on disk.
        parent = path.parent.relative_to(self.folder)
        data['folder'] = folder_name(parent.as_posix() if parent.parts else '')
        return data

    def load(self, key):
        return self._load_path(self.path(key))

    def list(self, query=''):
        records, warnings = [], []
        if not self.folder.exists():
            return records, warnings
        paths = list(self._paths())
        duplicates = {key for key, count in Counter(p.stem for p in paths).items() if count > 1}
        for path in paths:
            try:
                if path.stem in duplicates:
                    raise ConflictError('Duplicate conversation ID; original preserved.')
                data = self._load_path(path)
                haystack = data['title'] + '\n' + '\n'.join(m['content'] for m in data['messages'])
                if query.casefold() in haystack.casefold():
                    records.append(data)
            except (OSError, ValueError, UnicodeError) as error:
                warnings.append(f'{path.relative_to(self.folder)}: {error}')
        return sorted(records, key=lambda d: (d.get('pinned', False), d['updated']), reverse=True), warnings

    @contextmanager
    def _publication(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.folder_path(create=True)
        from PySide6.QtCore import QLockFile
        lock = QLockFile(str(self.root / 'publication.lock'))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise ConflictError('LM storage is busy in another instance. Retry saving.')
        try:
            yield
        finally:
            lock.unlock()

    def save(self, data):
        validate_conversation(data)
        name = folder_name(data.get('folder', ''))
        with self._publication():
            path = self.path(data['id'])
            current = self._load_path(path) if path.exists() else None
            if (current is None and data['revision'] != 0) or (current and current['revision'] != data['revision']):
                raise ConflictError('Conversation changed on disk. Export your current copy before reopening.')
            if current and current['folder'] != name:
                raise ConflictError('Conversation folder changed. Reopen it or use Move to change its folder.')
            if current is None:
                path = self.folder_path(name, create=True) / (data['id'] + '.json')
            saved = deepcopy(data)
            saved['folder'] = name
            saved['revision'] += 1
            saved['updated'] = now()
            atomic_write_json(path, saved, max_bytes=MAX_FILE_BYTES)
            data.update(revision=saved['revision'], updated=saved['updated'], folder=name)

    def move(self, data, name, *, lease=None):
        name = folder_name(name)
        owned_lease = self.lease(data['id']) if lease is None else None
        if lease is not None and not lease.isLocked():
            raise ConflictError('Acquire the conversation edit lease before moving it.')
        try:
            with self._publication():
                source = self.path(data['id'])
                current = self._load_path(source)
                if current['revision'] != data['revision'] or current['folder'] != data.get('folder', ''):
                    raise ConflictError('Conversation changed on disk; reopen before moving.')
                if name == current['folder']:
                    return
                destination = self.folder_path(name, create=True) / source.name
                saved = deepcopy(current)
                saved.update(folder=name, revision=current['revision'] + 1, updated=now())
                content = json.dumps(saved, ensure_ascii=False, allow_nan=False).encode('utf-8')
                if len(content) > MAX_FILE_BYTES:
                    raise ValueError('Conversation exceeds the file size limit.')
                # Publish without replacing a racing destination; keep source until publication succeeds.
                atomic_write_bytes(destination, content, overwrite=False)
                try:
                    source.unlink()
                except OSError:
                    destination.unlink()
                    raise
                data.update(folder=name, revision=saved['revision'], updated=saved['updated'])
        finally:
            if owned_lease is not None:
                owned_lease.unlock()

    def move_folder(self, name, parent, *, active=None, lease=None):
        """Move a whole subtree atomically, retaining IDs and refusing active peers."""
        from commonUtils.filesystem.rename import rename_path
        name, parent = folder_name(name), folder_name(parent)
        if not name or parent == name or parent.startswith(name + '/'):
            raise ValueError('A folder cannot be moved into itself or a descendant.')
        destination = '/'.join(part for part in (parent, name.rsplit('/', 1)[-1]) if part)
        if destination == name:
            return name
        with self._publication(), ExitStack() as locks:
            source = self.folder_path(name)
            target = self.folder_path(parent) / source.name
            if not source.is_dir() or not target.parent.is_dir():
                raise ValueError('The source or destination folder no longer exists.')
            if target.exists() or target.is_symlink():
                raise ValueError('A folder with that name already exists at the destination.')
            for path in self._paths():
                if source in path.parents:
                    if active is not None and path.stem == active['id'] and lease is not None and lease.isLocked():
                        continue
                    lock = self.lease(path.stem)
                    locks.callback(lock.unlock)
            rename_path(source, target)
            if active is not None and (active.get('folder') == name or active.get('folder', '').startswith(name + '/')):
                active['folder'] = destination + active['folder'][len(name):]
        return destination

    def delete(self, data):
        with self._publication():
            current = self.load(data['id'])
            if current['revision'] != data['revision']:
                raise ConflictError('Conversation changed on disk; reopen before deleting.')
            self.path(data['id']).unlink()

    def profiles(self):
        path = self.root / 'profiles.json'
        if not path.exists():
            return [dict(id='local', name='LM Studio (localhost default)', base_url='http://localhost:1234/v1')]
        data = self._read(path)
        return self.validate_profiles(data)

    @staticmethod
    def validate_profiles(data):
        if not isinstance(data, list) or len(data) > 100:
            raise ValueError('Invalid server profiles; original file preserved.')
        result, seen = [], set()
        for entry in data:
            if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) for k in ('id', 'name', 'base_url')):
                raise ValueError('Invalid server profile.')
            if not entry['id'] or len(entry['id']) > 100 or entry['id'] in seen or not entry['name'].strip():
                raise ValueError('Server profiles need unique IDs and names.')
            seen.add(entry['id'])
            result.append(dict(id=entry['id'], name=entry['name'].strip(), base_url=base_url(entry['base_url'])))
        return result

    def save_profiles(self, profiles, expected):
        from PySide6.QtCore import QLockFile
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = QLockFile(str(self.root / 'profiles.lock'))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise ConflictError('Server profiles are busy; retry.')
        try:
            if self.profiles() != expected:
                raise ConflictError('Server profiles changed in another instance; reopen the editor.')
            atomic_write_json(self.root / 'profiles.json', self.validate_profiles(profiles), max_bytes=128 * 1024)
        finally:
            lock.unlock()


def export_markdown(data):
    sections = [f'# {data["title"]}']
    for entry in data['messages']:
        status = '' if entry['status'] == 'complete' else f' ({entry["status"]})'
        sections.append(f'## {entry["role"].title()}{status}\n\n{entry["content"]}')
        for image in entry.get('images', []):
            sections.append(f'![Screenshot]({image_url(image)})')
    return '\n\n'.join(sections) + '\n'
