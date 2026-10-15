"""Repeated private-copy opens preserve resource identity across launches."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile


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
                from logisticsmobile.resource_imports import ResourceImports
                self.assertEqual(ResourceImports(root).find(path)['resource'], key)
                linked = root / 'linked.md'
                linked.symlink_to(path)
                with self.assertRaises(ValueError):
                    ResourceImports(root).find(linked)
            finally:
                app.main_window.close()
                app.loop.close()
