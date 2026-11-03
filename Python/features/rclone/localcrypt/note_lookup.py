"""Shared bounded ciphertext-name lookup for desktop and mobile LocalCrypt.

Providers supply encoding, batched decoding, credential and physical-path guards.
No document bytes or persistent plaintext index are needed for link resolution.
"""
from contextlib import closing
import os
import re
import stat
from pathlib import Path, PurePosixPath
from commonUtils.runtime.operations import check_cancelled
from .path_batches import map_path_entries


class CryptNoteLookup:
    """Provider mixin; adapters implement four credential-scoped hooks.

    `_note_encode` maps one file name, `_note_decode` maps batches of file or
    directory paths, `_note_check` validates access, and `_note_guard` validates
    physical folders without repeating platform storage-selection checks.
    """
    def _decode_note_entries(self, entries, cancelled):
        def check():
            check_cancelled(cancelled)
            self._note_check()
        return map_path_entries(entries,
            lambda batch: self._note_decode([dict(path=path, directory=directory) for path, directory in batch]),
            check=check, batch_size=512, max_bytes=64 * 1024)

    def _check_note_directory(self, folder, before):
        self._note_guard(folder)
        after = folder.stat(follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_mode) != (after.st_dev, after.st_ino, after.st_mode):
            raise ValueError('Notes changed during discovery. Try again.')

    def note_file_paths(self, root='', *, cancelled=lambda: False):
        """Enumerate Markdown names in batches across sibling directories.

        Only this call retains decoded basenames. Hidden directories are pruned
        before descent; no document bytes or per-file metadata bridge is needed.
        """
        return self._note_file_inventory(root, cancelled=cancelled)

    def note_file_entries(self, root='', *, cancelled=lambda: False):
        """Names and provider filesystem sizes, sharing the bounded discovery."""
        return self._note_file_inventory(root, cancelled=cancelled, metadata=True)

    def _note_file_inventory(self, root='', *, cancelled=lambda: False, metadata=False):
        root = self.relative(root)
        with self.operation(cancelled):
            top = self._locate(root)
            root_before = top.stat(follow_symlinks=False)
            pending, names, paths, count = [(root, top, root_before)], {}, [], 0
            while pending:
                children = []
                for parent, folder, folder_before in pending:
                    check_cancelled(cancelled)
                    self._note_check()
                    self._check_note_directory(folder, folder_before)
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            check_cancelled(cancelled)
                            child = Path(entry.path)
                            if entry.is_symlink() or (hasattr(Path, 'is_junction') and child.is_junction()):
                                raise ValueError('Linked storage is not supported.')
                            try:
                                info = entry.stat(follow_symlinks=False)
                            except FileNotFoundError:
                                continue
                            directory = stat.S_ISDIR(info.st_mode)
                            if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                                raise ValueError('Choose an independent regular file or folder.')
                            if re.fullmatch(r'.+\.[0-9a-f]{8}\.partial', child.name):
                                continue
                            count += 1
                            if count > 10000:
                                raise ValueError('Data view page discovery exceeds 10,000 entries.')
                            children.append((parent, child, info, directory))
                    self._check_note_directory(folder, folder_before)
                missing = list(dict.fromkeys((child.name, directory) for _, child, _, directory in children
                                             if (child.name, directory) not in names))
                decoded = self._decode_note_entries(missing, cancelled)
                for key, plain in zip(missing, decoded):
                    plain = self.relative(plain)
                    if not plain or '/' in plain:
                        raise ValueError('Invalid encrypted folder entry.')
                    names[key] = plain
                pending = []
                for parent, child, before, directory in children:
                    check_cancelled(cancelled)
                    plain = names[child.name, directory]
                    if plain.startswith('.'):
                        continue
                    try:
                        after = child.stat(follow_symlinks=False)
                    except FileNotFoundError as error:
                        raise ValueError('Notes changed during discovery. Try again.') from error
                    if ((before.st_dev, before.st_ino, before.st_mode) != (after.st_dev, after.st_ino, after.st_mode)
                            or (not directory and after.st_nlink != 1)):
                        raise ValueError('Notes changed during discovery. Try again.')
                    path = '/'.join(part for part in (parent, plain) if part)
                    if directory:
                        pending.append((path, child, before))
                    elif PurePosixPath(plain).suffix.lower() in {'.md', '.markdown'}:
                        paths.append(dict(path=path, size=after.st_size) if metadata else path)
            self._guard(top)
            self._check_note_directory(top, root_before)
            self._note_check()
            check_cancelled(cancelled)
            return paths

    def _ciphertext_note_paths(self, name, root, encoded, top, cancelled):
        """Use descriptor-relative traversal; decrypt only matching full paths.

        Return None to retain the visible-tree limit semantics for unusually
        deep or hidden-heavy trees. The caller then uses its bounded fallback.
        """
        def failed(error):
            raise error  # Never accept an incomplete scan as a unique match.

        candidates, count = [], 0
        with closing(os.fwalk(top, follow_symlinks=False, onerror=failed)) as walk:
            for folder, directories, files, descriptor in walk:
                self._note_check()
                if os.path.relpath(folder, top).count(os.sep) >= 128:
                    return None
                for index, child in enumerate((*directories, *files)):
                    if index % 32 == 0:
                        check_cancelled(cancelled)
                    try:
                        info = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if stat.S_ISLNK(info.st_mode):
                        return None  # The visible-tree fallback decides whether this is hidden configuration.
                    directory = stat.S_ISDIR(info.st_mode)
                    if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                        return None
                    if re.fullmatch(r'.+\.[0-9a-f]{8}\.partial', child):
                        continue
                    count += 1
                    if count > 10000:
                        return None
                    if not directory and child == encoded:
                        physical = os.path.relpath(os.path.join(folder, child), self.root)
                        candidates.append((Path(physical).as_posix(), info))
        matches = []
        for offset in range(0, len(candidates), 256):
            check_cancelled(cancelled)
            batch = candidates[offset:offset + 256]
            self._note_check()
            decoded = self._decode_note_entries([(path, False) for path, _ in batch], cancelled)
            self._note_check()
            if len(decoded) != len(batch):
                raise ValueError('Incomplete encrypted note lookup.')
            for plain, (ciphertext, before) in zip(decoded, batch):
                check_cancelled(cancelled)
                plain = self.relative(plain)
                relative = PurePosixPath(plain).relative_to(root or '.')
                if any(part.startswith('.') for part in relative.parts):
                    continue
                if plain != name and not plain.endswith('/' + name):
                    continue
                target = self._note_guard(Path(self.root) / ciphertext)
                current = target.stat(follow_symlinks=False)
                revision = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                        or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != revision):
                    raise ValueError('Notes changed during lookup. Try again.')
                matches.append(plain)
        self._guard(top)
        self._note_check()
        check_cancelled(cancelled)
        return matches

    def find_note_paths(self, name, root='', *, cancelled=lambda: False):
        """Match ciphertext basenames, decoding only candidates on POSIX hosts.

        Other hosts and oversized/deep raw trees use a visible-tree scan with
        batched directory decoding. Neither path retains a plaintext index.
        """
        name, root = self.relative(name), self.relative(root)
        basename = PurePosixPath(name).name
        with self.operation(cancelled):
            encoded = self._note_encode(basename)
            if not encoded or '/' in encoded:
                raise ValueError('Invalid encrypted filename.')
            top = self._locate(root)
            if hasattr(os, 'fwalk'):
                matches = self._ciphertext_note_paths(name, root, encoded, top, cancelled)
                if matches is not None:
                    return matches
            root_before = top.stat(follow_symlinks=False)
            pending = [(root, top, root_before)]
            matches, count = [], 0
            while pending:
                directories = []
                for parent, folder, folder_before in pending:
                    check_cancelled(cancelled)
                    # Collection selection is checked for the whole traversal,
                    # before and after. Keep per-folder ancestor/link guards
                    # without rereading the same storage settings thousands of
                    # times. Grant checks also fence each decode and publication.
                    self._check_note_directory(folder, folder_before)
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            check_cancelled(cancelled)
                            child = Path(entry.path)
                            if entry.is_symlink() or (hasattr(Path, 'is_junction') and child.is_junction()):
                                raise ValueError('Linked storage is not supported.')
                            try:
                                info = entry.stat(follow_symlinks=False)
                            except FileNotFoundError:
                                continue
                            directory = stat.S_ISDIR(info.st_mode)
                            if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                                raise ValueError('Choose an independent regular file or folder.')
                            if re.fullmatch(r'.+\.[0-9a-f]{8}\.partial', child.name):
                                continue
                            count += 1
                            if count > 10000:
                                raise ValueError('Note lookup exceeds the 10,000-entry limit. Use an explicit note path.')
                            if directory:
                                directories.append((parent, child, info))
                            elif entry.name == encoded:
                                plain = '/'.join(part for part in (parent, basename) if part)
                                if plain == name or plain.endswith('/' + name):
                                    self._guard(child)
                                    matches.append(plain)
                    self._check_note_directory(folder, folder_before)
                pending = []
                for offset in range(0, len(directories), 256):
                    check_cancelled(cancelled)
                    batch = directories[offset:offset + 256]
                    self._note_check()
                    names = self._decode_note_entries([(child.name, True) for _, child, _ in batch], cancelled)
                    self._note_check()
                    if len(names) != len(batch):
                        raise ValueError('Incomplete encrypted folder lookup.')
                    for decoded, (parent, child, before) in zip(names, batch):
                        check_cancelled(cancelled)
                        decoded = self.relative(decoded)
                        if not decoded or '/' in decoded:
                            raise ValueError('Invalid encrypted folder entry.')
                        if decoded.startswith('.'):
                            continue
                        try:
                            after = child.stat(follow_symlinks=False)
                        except FileNotFoundError as error:
                            raise ValueError('Notes changed during lookup. Try again.') from error
                        if (before.st_dev, before.st_ino, before.st_mode) != (after.st_dev, after.st_ino, after.st_mode):
                            raise ValueError('Notes changed during lookup. Try again.')
                        pending.append(('/'.join(part for part in (parent, decoded) if part), child, before))
            self._guard(top)
            self._check_note_directory(top, root_before)
            self._note_check()
            check_cancelled(cancelled)
            return matches

