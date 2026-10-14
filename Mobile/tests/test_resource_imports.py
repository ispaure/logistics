"""Repeated private-copy opens preserve resource identity across launches."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile


class ResourceImportTests(unittest.TestCase):
    def test_duplicate_copy_open_keeps_one_document_and_its_draft(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud()
                path = app.downloads.save('same.md', b'original')
                app.refresh_downloads(path)
                app.loop.run_until_complete(app.open_download())
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
            finally:
                app.main_window.close()
                app.loop.close()
