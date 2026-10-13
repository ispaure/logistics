"""Widget contracts using Toga's official dummy backend, not device evidence."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from logisticsmobile.access import LocalDocuments
from logisticsmobile.app import LogisticsMobile


class MobileUITests(unittest.TestCase):
    def test_create_edit_recover_switch_import_save_and_conflict_copy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            first = app.current.id
            app.name.value = 'Notes.md'
            app.editor.value = '# Recovered\n'
            recovered = app.store.open(first)
            self.assertEqual(recovered.name, 'Notes.md')
            self.assertTrue(recovered.modified)
            app.new_document()
            app.selector.value = 'Notes.md'
            self.assertEqual(app.current.id, first)
            self.assertEqual(app.editor.value, '# Recovered\n')
            app.save_document()
            self.assertFalse(app.store.open(first).modified)
            source = root / 'external.txt'
            source.write_bytes(b'external\r\n')
            with patch('logisticsmobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), source))):
                app.loop.run_until_complete(app.import_document())
            self.assertTrue(app.import_button.enabled)
            self.assertEqual(app.editor.value, 'external\n')
            app.editor.value = 'edited\n'
            app.save_document()
            self.assertEqual(source.read_bytes(), b'external\r\n')
            conflicted = app.current.id
            app.current.snapshot.path.write_bytes(b'changed outside the app')
            app.editor.value = 'keep these edits'
            app.save_document()
            self.assertIn('changed', app.status.text)
            app.save_copy()
            self.assertNotEqual(app.current.id, conflicted)
            self.assertEqual(app.current.text, 'keep these edits')
            app.main_window.close()
            app.loop.close()


if __name__ == '__main__':
    unittest.main()
