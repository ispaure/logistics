"""Repeated private-copy opens preserve resource identity across launches."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from mobile.app import LogisticsMobile


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
    def test_ios_inbox_import_identity_is_retained_without_plaintext_names(self):
        from mobile.resource_imports import ResourceImports
        from features.rclone.mobile.storage_location import use_shared_local, _shared_local_roots
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
        from features.rclone.mobile.storage_location import use_shared_local, _shared_local_roots
        with TemporaryDirectory() as directory:
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
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            use_shared_local(private, documents)
            self.addCleanup(_shared_local_roots.pop, private, None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_cloud(present=False)
            app.loop.run_until_complete(app.open_download(path=path))
            owner = app.reader_manager().active
            self.assertIsNotNone(owner, app.cloud_status.value)
            self.assertIsNotNone(owner.book_reader, app.cloud_status.value)
            self.assertEqual(owner.book_record['kind'], 'epub')
            identity = owner.session.id
            app.loop.run_until_complete(app.open_download(path=path))
            self.assertEqual(app.reader_manager().active.session.id, identity)
            self.assertEqual(len(app.readers.catalog.library_store.items()[0]), 1)

    def test_relocated_collection_keeps_existing_identity_and_rejects_other_paths(self):
        from mobile.resource_imports import ResourceImports
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
                self.assertEqual(app.editor.value, 'original', app.cloud_status.value)
                key = app.current.id
                app.editor.value = 'kept draft'
                app.loop.run_until_complete(app.open_download())
                self.assertEqual(app.current.id, key)
                self.assertEqual(app.editor.value, 'kept draft')
                raw = (root / 'resource-imports.json').read_text()
                self.assertNotIn('same.md', raw)
                self.assertNotIn('kept draft', raw)
                from mobile.resource_imports import ResourceImports
                self.assertEqual(ResourceImports(root).find(path)['resource'], key)
                linked = root / 'linked.md'
                linked.symlink_to(path)
                with self.assertRaises(ValueError):
                    ResourceImports(root).find(linked)
            finally:
                app.main_window.close()
                app.loop.close()
