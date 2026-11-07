"""Repeated private-copy opens preserve resource identity across launches."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from threading import Barrier
from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from mobile.app import LogisticsMobile
from mobile.resource_imports import ResourceImports


def seed_download(store, name, data):
    """Represent a completed private copy created by an older app version."""
    from uuid import uuid4
    folder = store.root / uuid4().hex
    folder.mkdir()
    target = folder / name
    target.write_bytes(data)
    (folder / '.complete').write_text(name)
    return target


class ResourceImportTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.index_root = Path(directory).resolve()

    def test_independent_writers_keep_both_imports(self):
        documents = ResourceImports(self.index_root)
        notebooks = ResourceImports(self.index_root)
        document = self.index_root / 'private.md'
        notebook = self.index_root / 'private.rmdoc'
        documents.remember(document, 'managed-text', 'a' * 32)
        notebooks.remember(notebook, 'notebook', 'b' * 32)
        self.assertEqual(documents.find(notebook), dict(provider='notebook', resource='b' * 32))
        self.assertEqual(notebooks.find(document), dict(provider='managed-text', resource='a' * 32))
        self.assertNotIn('private', documents.path.read_text())

    def test_forget_is_visible_and_later_writes_do_not_resurrect_it(self):
        document = self.index_root / 'private.md'
        documents = ResourceImports(self.index_root)
        documents.remember(document, 'managed-text', 'a' * 32)
        notebooks = ResourceImports(self.index_root)
        notebook = self.index_root / 'private.rmdoc'
        notebooks.remember(notebook, 'notebook', 'b' * 32)
        reader = ResourceImports(self.index_root)
        documents.forget('notebook', 'b' * 32)
        self.assertIsNone(reader.find(notebook))
        notebooks.remember(self.index_root / 'another.rmdoc', 'notebook', 'c' * 32)
        self.assertIsNone(ResourceImports(self.index_root).find(notebook))
        self.assertEqual(notebooks.find(document)['resource'], 'a' * 32)

    def test_last_successful_remember_replaces_mapping_and_old_forget_keeps_it(self):
        path = self.index_root / 'private.md'
        earlier = ResourceImports(self.index_root)
        earlier.remember(path, 'managed-text', 'a' * 32)
        later = ResourceImports(self.index_root)
        later.remember(path, 'managed-text', 'b' * 32)
        earlier.forget('managed-text', 'a' * 32)
        self.assertEqual(earlier.find(path), dict(provider='managed-text', resource='b' * 32))
        self.assertEqual(ResourceImports(self.index_root).find(path)['resource'], 'b' * 32)

    def test_threaded_writers_preserve_disjoint_mappings(self):
        writers = [ResourceImports(self.index_root) for _ in range(4)]
        start = Barrier(len(writers))

        def remember(index, imports):
            start.wait(timeout=5)
            imports.remember(self.index_root / str(index), 'notebook', f'{index:032x}')

        with ThreadPoolExecutor(max_workers=len(writers)) as pool:
            futures = [pool.submit(remember, index, imports) for index, imports in enumerate(writers)]
            for future in futures:
                future.result()
        restored = ResourceImports(self.index_root)
        for index in range(len(writers)):
            self.assertEqual(restored.find(self.index_root / str(index)),
                             dict(provider='notebook', resource=f'{index:032x}'))

    def test_failed_publication_leaves_committed_mappings_available(self):
        path = self.index_root / 'private.md'
        imports = ResourceImports(self.index_root)
        imports.remember(path, 'managed-text', 'a' * 32)
        original = imports.path.read_bytes()
        with patch('mobile.resource_imports.atomic_write_json', side_effect=OSError('write failed')):
            with self.assertRaisesRegex(OSError, 'write failed'):
                imports.remember(path, 'managed-text', 'b' * 32)
            with self.assertRaisesRegex(OSError, 'write failed'):
                imports.forget('managed-text', 'a' * 32)
        self.assertEqual(imports.path.read_bytes(), original)
        self.assertEqual(imports.find(path)['resource'], 'a' * 32)
        imports.forget('managed-text', 'a' * 32)
        self.assertIsNone(imports.find(path))

    def test_remember_checks_current_capacity_and_validates_new_identity(self):
        imports = ResourceImports(self.index_root)
        path = self.index_root / 'private.md'
        with self.assertRaises(ValueError):
            imports.remember(path, 'managed-text', 'private.md')
        with self.assertRaises(ValueError):
            imports.remember(path, 'private.md', 'a' * 32)
        self.assertFalse(imports.path.exists())

        identity = dict(provider='managed-text', resource='a' * 32)
        items = {f'{index:064x}': identity for index in range(255)}
        items[imports.identity(path)] = identity
        original = json.dumps(dict(schema=1, items=items))
        imports.path.write_text(original)
        with self.assertRaisesRegex(ValueError, 'limit: 256'):
            imports.remember(self.index_root / 'new.md', 'managed-text', 'b' * 32)
        self.assertEqual(imports.path.read_text(), original)
        imports.remember(path, 'managed-text', 'b' * 32)
        self.assertEqual(imports.find(path)['resource'], 'b' * 32)
        self.assertEqual(len(imports.items), 256)

    def test_stale_instance_vetoes_invalid_disk_index(self):
        imports = ResourceImports(self.index_root)
        path = self.index_root / 'private.md'
        imports.remember(path, 'managed-text', 'a' * 32)
        identity = dict(provider='managed-text', resource='a' * 32)
        invalid_indexes = {
            'malformed JSON': b'{',
            'invalid ID': json.dumps(dict(schema=1, items={
                imports.identity(path): dict(identity, resource='private.md'),
            })).encode(),
            'too many items': json.dumps(dict(schema=1, items={
                f'{index:064x}': identity for index in range(257)
            })).encode(),
            'oversized': b' ' * 65537,
        }
        for label, invalid in invalid_indexes.items():
            with self.subTest(label=label):
                imports.path.write_bytes(invalid)
                for action in (
                    lambda: imports.find(path),
                    lambda: imports.remember(path, 'managed-text', 'b' * 32),
                    lambda: imports.forget('managed-text', 'a' * 32),
                ):
                    with self.assertRaises(ValueError):
                        action()
                self.assertEqual(imports.path.read_bytes(), invalid)

    def test_stale_instance_vetoes_dangling_index_symlink(self):
        imports = ResourceImports(self.index_root)
        path = self.index_root / 'private.md'
        target = self.index_root / 'missing'
        imports.path.symlink_to(target)
        with self.assertRaises(ValueError):
            imports.find(path)
        with self.assertRaises(ValueError):
            imports.remember(path, 'managed-text', 'a' * 32)
        with self.assertRaises(ValueError):
            imports.forget('managed-text', 'a' * 32)
        self.assertEqual(imports.path.readlink(), target)
        self.assertFalse(target.exists())

    def test_android_received_files_on_sd_keep_identity_and_reject_siblings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            private, collection = root / 'private', root / 'sd/Logistics/Local'
            original = private / 'Received Files/sketch.rmdoc'
            original.parent.mkdir(parents=True)
            original.write_bytes(b'fixture')
            ResourceImports(private).remember(original, 'notebook', 'a' * 32)
            collection.mkdir(parents=True)
            moved = collection.parent / 'Received Files/sketch.rmdoc'
            moved.parent.mkdir()
            original.rename(moved)
            imports = ResourceImports(private, collection_root=collection)
            self.assertEqual(imports.find(moved), dict(provider='notebook', resource='a' * 32))
            imports.remember(moved, 'notebook', 'b' * 32)
            self.assertEqual(ResourceImports(private, collection_root=collection).find(moved)['resource'], 'b' * 32)
            self.assertNotIn('sketch.rmdoc', imports.path.read_text())
            for path in (collection.parent / 'LocalCrypt/secret.rmdoc', root / 'sd/other.rmdoc'):
                with self.assertRaisesRegex(ValueError, 'Local or private Downloads'):
                    imports.find(path)
            linked = moved.parent / 'linked.rmdoc'
            linked.symlink_to(moved)
            with self.assertRaisesRegex(ValueError, 'Linked'):
                imports.find(linked)

    def test_ios_inbox_import_identity_is_retained_without_plaintext_names(self):
        from services.documents.locations import use_shared_local, _shared_local_roots
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            private, documents = root / 'private', root / 'Documents'
            private.mkdir()
            inbox = documents / 'Inbox'
            inbox.mkdir(parents=True)
            source = inbox / 'shared.pdf'
            source.write_bytes(b'fixture')
            use_shared_local(private, documents)
            self.addCleanup(_shared_local_roots.pop, private, None)
            imports = ResourceImports(private, collection_root=documents / 'Local')
            imports.remember(source, 'library', 'a' * 32)
            self.assertEqual(ResourceImports(private).find(source)['resource'], 'a' * 32)
            self.assertNotIn(source.name, imports.path.read_text())

    def test_ios_shared_local_epub_opens_and_reopens_without_duplicate_import(self):
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        from services.documents.locations import use_shared_local, _shared_local_roots
        with TemporaryDirectory() as directory, ExitStack() as fixture_cleanup:
            root = Path(directory).resolve()
            private, documents = root / 'Application Support/Logistics', root / 'Documents'
            private.mkdir(parents=True)
            local = documents / 'Local'
            local.mkdir(parents=True)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, _ = make_books(fixtures)
            path = local / 'book.epub'
            path.write_bytes(epub.read_bytes())
            LogisticsMobile.storage_root = private
            fixture_cleanup.callback(setattr, LogisticsMobile, 'storage_root', None)
            use_shared_local(private, documents)
            self.addCleanup(_shared_local_roots.pop, private, None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            fixture_cleanup.callback(close_loop, app.loop)
            fixture_cleanup.callback(app.main_window.close)
            app.show_cloud(present=False)
            app.loop.run_until_complete(app.open_download(path=path))
            owner = app.private_sessions.active
            self.assertIsNotNone(owner.crypt_reader.book)
            identity = owner.session.id
            app.loop.run_until_complete(app.open_download(path=path))
            self.assertEqual(app.private_sessions.active.session.id, identity)
            self.assertEqual(app.reader_manager().catalog.library_store.stored_files()[0], [])
            self.assertTrue(app.close_session(identity))
            self.assertTrue(app.loop.run_until_complete(app.open_download(path=path)))
            self.assertEqual(app.private_sessions.active.crypt_reader.source.provider.root, path.parent)
            self.assertEqual(app.reader_manager().catalog.library_store.stored_files()[0], [])

    def test_relocated_collection_keeps_existing_identity_and_rejects_other_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            private, shared = root / 'private', root / 'Documents/Local'
            old_local = private / 'LocalFiles'
            old_local.mkdir(parents=True)
            shared.mkdir(parents=True)
            source = old_local / 'book.epub'
            source.write_bytes(b'fixture')
            key = 'a' * 32
            ResourceImports(private).remember(source, 'library', key)
            moved = shared / source.name
            source.rename(moved)
            restored = ResourceImports(private, collection_root=shared)
            self.assertEqual(restored.find(moved), dict(provider='library', resource=key))
            self.assertNotIn('book.epub', restored.path.read_text())
            with self.assertRaisesRegex(ValueError, 'Local or private Downloads'):
                restored.find(root / 'unrelated.epub')
            linked = shared / 'linked.epub'
            linked.symlink_to(moved)
            with self.assertRaisesRegex(ValueError, 'Linked'):
                restored.find(linked)

    def test_duplicate_copy_open_keeps_one_document_and_its_draft(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud()
                path = seed_download(app.downloads, 'same.md', b'original')
                app.refresh_downloads(path)
                with patch('features.rclone.mobile.downloads.collection_path', side_effect=OSError('SD card unavailable')):
                    app.loop.run_until_complete(app.open_download())
                owner = app.private_sessions.active
                self.assertEqual(owner.crypt_text.value, 'original')
                key = owner.session.id
                owner.crypt_text.value = 'kept draft'
                app.loop.run_until_complete(app.open_download())
                self.assertEqual(app.private_sessions.active.session.id, key)
                self.assertEqual(owner.crypt_text.value, 'kept draft')
                self.assertFalse((root / 'resource-imports.json').exists())
                self.assertIsNone(ResourceImports(root).find(path))
                self.assertEqual(path.read_text(), 'original')
                app.loop.run_until_complete(owner.save_crypt())
                self.assertEqual(path.read_text(), 'kept draft')
                linked = root / 'linked.md'
                linked.symlink_to(path)
                with self.assertRaises(ValueError):
                    ResourceImports(root).find(linked)
            finally:
                app.main_window.close()
                close_loop(app.loop)
