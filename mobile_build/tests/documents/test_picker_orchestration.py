"""Save As keeps drafts until both publication and editor handoff succeed."""

import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.testing.stages import TestStage
from mobile_build.tests.support.app import create_document_app


TEST_STAGE = TestStage.REGRESSION


class PickerSaveHandoffTests(unittest.TestCase):
    def setUp(self):
        self.app = create_document_app(self)
        self.app.prepare_cloud()
        self.draft = b'# Unsaved draft'
        self.run_async = self.app.loop.run_until_complete
        self.run_async(self.app.show_text_destination('copy.md', self.draft))
        self.picker = self.app.editor_picker()
        provider = self.picker.editor_provider(self.picker.save_as_storage.value)
        self.destination = provider.root / 'copy.md'

    def test_reader_failure_reports_published_file_and_retains_draft(self):
        with (patch('services.documents.provider_documents.ProviderDocuments.open',
                    side_effect=OSError('reader unavailable')),
              patch.object(self.app, 'open_crypt', new_callable=AsyncMock) as open_editor):
            self.run_async(self.picker.confirm_editor_file())

        open_editor.assert_not_awaited()
        self.assertEqual(self.destination.read_bytes(), self.draft)
        self.assertEqual(self.picker.save_as_data, self.draft)
        self.assertIn('was saved, but could not be reopened unchanged', self.picker.save_as_status.value)
        self.assertIn('Refresh before retrying', self.picker.save_as_status.value)
        self.assertTrue(self.picker.visible())
        self.assertFalse(self.app.cloud_busy)

    def test_editor_rejection_reports_saved_file_and_keeps_picker_available(self):
        with patch.object(self.app, 'open_crypt', new_callable=AsyncMock, return_value=False) as open_editor:
            self.run_async(self.picker.confirm_editor_file())

        open_editor.assert_awaited_once()
        self.assertEqual(self.destination.read_bytes(), self.draft)
        self.assertEqual(self.picker.save_as_data, self.draft)
        self.assertEqual(' '.join(self.picker.save_as_status.value.split()),
                         'The file was saved, but its editor could not be opened. The Save As draft is retained.')
        self.assertTrue(self.picker.visible())
        self.assertTrue(self.picker.picker_primary.enabled)
        self.assertFalse(self.app.cloud_busy)

    def test_late_editor_success_keeps_the_new_picker_draft(self):
        async def open_editor(**kwargs):
            self.assertFalse(self.app.cloud_busy)
            await self.app.show_text_destination('next.md', b'New draft')
            return True

        with patch.object(self.app, 'open_crypt', side_effect=open_editor):
            self.run_async(self.picker.confirm_editor_file())

        self.assertEqual(self.destination.read_bytes(), self.draft)
        self.assertEqual(self.picker.save_as_name.value, 'next.md')
        self.assertEqual(self.picker.save_as_data, b'New draft')
        self.assertTrue(self.picker.visible())
