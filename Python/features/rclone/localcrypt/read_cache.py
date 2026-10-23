"""Session-private decrypted metadata and bytes, retired as one lifetime.

Every lookup and publication validates access under the retirement lock. Workers
may finish after a provider closes, but cannot put private data back into it.
The provider owns credential revocation and physical revision validation.
"""
from collections import OrderedDict
from threading import RLock
from typing import Callable


class PrivateReadCache:
    def __init__(self, root, validate: Callable[[], None], *, max_paths=10000, max_sizes=10000,
                 max_blocks=512, max_bytes=32 * 1024 * 1024):
        self._validate = validate
        self._lock = RLock()
        self._closed = False
        self._paths = OrderedDict()
        self._directories = {'': root}
        self._sizes = OrderedDict()
        self._blocks = OrderedDict()
        self._bytes = 0
        self._max_paths = max_paths
        self._max_sizes = max_sizes
        self._max_blocks = max_blocks
        self._max_bytes = max_bytes

    @property
    def closed(self):
        with self._lock:
            return self._closed

    def _check(self):
        if self._closed:
            raise ValueError('The private reader is closed. Reopen after unlocking.')
        self._validate()

    def path(self, relative, *, directory=False):
        with self._lock:
            self._check()
            target = (self._directories if directory else self._paths).get(relative)
            if target is not None and relative in self._paths:
                self._paths.move_to_end(relative)
            return target

    def remember_path(self, relative, target, *, directory=False):
        with self._lock:
            self._check()
            self._paths[relative] = target
            self._paths.move_to_end(relative)
            if directory:
                self._directories[relative] = target
            while len(self._paths) > self._max_paths:
                retired, _ = self._paths.popitem(last=False)
                self._directories.pop(retired, None)

    def size(self, path, revision):
        with self._lock:
            self._check()
            cached = self._sizes.get(path)
            if cached is not None and cached[0] == revision:
                self._sizes.move_to_end(path)
                return cached[1]
            return None

    def remember_size(self, path, revision, size):
        with self._lock:
            self._check()
            self._sizes[path] = revision, size
            self._sizes.move_to_end(path)
            while len(self._sizes) > self._max_sizes:
                self._sizes.popitem(last=False)

    def block(self, key):
        with self._lock:
            self._check()
            if key not in self._blocks:
                return None
            self._blocks.move_to_end(key)
            return self._blocks[key]

    def remember_block(self, key, data):
        with self._lock:
            self._check()
            if key not in self._blocks:
                self._blocks[key] = data
                self._bytes += len(data)
            while self._bytes > self._max_bytes or len(self._blocks) > self._max_blocks:
                _, evicted = self._blocks.popitem(last=False)
                self._bytes -= len(evicted)

    def forget_path(self, path):
        """Release staging metadata and verification bytes, even after retirement."""
        with self._lock:
            self._paths.pop(path, None)
            self._directories.pop(path, None)
            self._sizes.pop(path, None)
            for key in tuple(self._blocks):
                if key[0] == path:
                    self._bytes -= len(self._blocks.pop(key))

    def retire(self):
        """Erase before revocation callbacks; return whether this closed the cache."""
        with self._lock:
            if self._closed:
                return False
            self._closed = True
            self._paths.clear()
            self._directories.clear()
            self._sizes.clear()
            self._blocks.clear()
            self._bytes = 0
            return True
