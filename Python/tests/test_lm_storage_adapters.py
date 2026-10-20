"""Storage lock injection retains conflict policy without constructing Qt locks."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

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
