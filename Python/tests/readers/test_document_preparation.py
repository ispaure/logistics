"""Provider Markdown preparation stays headless and bounds resource access."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from services.documents.preparation import prepare_editor


class DocumentPreparationTests(unittest.TestCase):
    def test_relative_encoded_resources_are_loaded_without_remote_or_parent_reads(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            storage = root / 'storage'
            storage.mkdir()
            (root / 'outside.png').write_bytes(b'outside')
            (storage / 'cover image.png').write_bytes(b'image fixture')
            (storage / 'note.md').write_text(
                '![local](cover%20image.png)\n![outside](../outside.png)\n'
                '![remote](https://example.invalid/image.png)\n')
            choice = ResourceChoice(LocalFiles(storage), 'note.md', lambda: None)
            try:
                session = prepare_editor(choice, markdown=True)
                self.assertEqual(session.resources, {storage / 'cover image.png': b'image fixture'})
                self.assertTrue(session.text.data.startswith(b'![local]'))
            finally:
                choice.close()
