"""Storage lock injection retains conflict policy without constructing Qt locks."""

from pathlib import Path
import os
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from features.lm.storage import Store, ConflictError
from features.lm.domain import conversation, defaults


class StorageAdapterTests(TestCase):
    def test_injected_locks_guard_publication_and_conflicts_preserve_saved_record(self):
        with TemporaryDirectory() as directory:
            locks = []

            def lock_file(path):
                lock = Mock()
                lock.tryLock.return_value = True
                locks.append((Path(path).name, lock))
                return lock

            store = Store(directory, lock_factory=lock_file)
            data = conversation(defaults())
            store.save(data)
            before = store.path(data["id"]).read_bytes()
            self.assertEqual(locks[0][0], "publication.lock")
            locks[0][1].unlock.assert_called_once()
            denied = Mock()
            denied.tryLock.return_value = False
            store.lock_factory = lambda path: denied
            with self.assertRaises(ConflictError):
                store.save(data)
            self.assertEqual(store.path(data["id"]).read_bytes(), before)

    def test_read_limit_is_enforced_when_file_size_metadata_is_stale(self):
        with TemporaryDirectory() as directory:
            lock = Mock()
            lock.tryLock.return_value = True
            store = Store(directory, lock_factory=lambda path: lock)
            data = conversation(defaults())
            data['draft'] = 'x' * 2048
            store.save(data)
            path = store.path(data['id'])
            before = path.read_bytes()
            original_stat = Path.stat
            def stale_stat(candidate, *args, **kwargs):
                info = original_stat(candidate, *args, **kwargs)
                if candidate == path:
                    fields = list(info)
                    fields[6] = 0
                    return os.stat_result(fields)
                return info
            with patch('features.lm.storage.MAX_FILE_BYTES', 512), patch.object(Path, 'stat', stale_stat):
                with self.assertRaisesRegex(ValueError, 'file limit'):
                    store.load(data['id'])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.load(data['id'])['draft'], data['draft'])
