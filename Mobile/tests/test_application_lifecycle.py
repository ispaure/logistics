"""Host replacement preserves data before retiring callbacks and resources."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.application_lifecycle import lifecycle


class HostLifecycleTests(unittest.TestCase):
    def host(self):
        return NS(active_host=True, store=Mock(), credential_document_lists=Mock(),
                  chat_current=object(), checkpoint_chat=Mock(return_value=True),
                  startup_task=Mock(done=Mock(return_value=False)),
                  vault_browser=Mock(), memory_pressure=Mock(), screen_privacy=Mock(),
                  cloud_startup_task=Mock(), cloud_client=Mock(), cancel_cloud=Mock(),
                  _editor_picker=Mock(), workspace=NS(sessions={'doc': NS(id='doc')}, invalidate=Mock()),
                  _crypt_cancel=Mock())

    def test_failed_checkpoint_keeps_old_host_and_resources_available_for_retry(self):
        host = self.host()
        host.checkpoint_chat.return_value = False
        owner = lifecycle(host)
        with self.assertRaisesRegex(OSError, 'preserve'):
            owner.retire_for_replacement()
        self.assertTrue(host.active_host)
        host.startup_task.cancel.assert_not_called()
        host.screen_privacy.dispose.assert_not_called()
        self.assertFalse(owner.replacement_prepared)
        host.checkpoint_chat.return_value = True
        owner.prepare_replacement()
        self.assertFalse(host.active_host)

    def test_async_prepare_then_retire_flushes_once_and_disposes_once(self):
        host = self.host()
        owner = lifecycle(host)
        with patch('logisticsmobile.markdown_speech.stop_markdown_speech'), \
                patch('features.books.mobile.media_controls.stop_media'):
            owner.prepare_replacement()
            host.screen_privacy.dispose.assert_not_called()
            owner.retire_for_replacement()
            owner.retire_for_replacement()
        self.assertIs(lifecycle(host), owner)
        host.store.flush_checkpoints.assert_called_once_with()
        host.credential_document_lists.flush_writes.assert_called_once_with()
        host.checkpoint_chat.assert_called_once_with()
        host.startup_task.cancel.assert_called_once_with()
        host.screen_privacy.dispose.assert_called_once_with()
        host.cloud_startup_task.cancel.assert_called_once_with()
        host.workspace.invalidate.assert_called_once_with('doc')
        host._crypt_cancel.set.assert_called_once_with()

    def test_exit_veto_does_not_dispose_and_successful_exit_is_idempotent(self):
        host = self.host()
        host.cloud_busy = False
        host.retire_private_comic_batch = Mock()
        host.private_sessions = object()
        host.clear_private_reader = Mock(return_value=False)
        host.checkpoint = Mock(return_value=True)
        host.scene_manager = NS(external_comics=Mock())
        host.seasonal_snow = Mock()
        owner = lifecycle(host)
        self.assertFalse(owner.request_exit())
        self.assertTrue(host.active_host)
        host.checkpoint.assert_not_called()
        host.screen_privacy.dispose.assert_not_called()
        host.clear_private_reader.return_value = True
        with patch('logisticsmobile.markdown_speech.stop_markdown_speech'), \
                patch('features.books.mobile.media_controls.stop_media'):
            self.assertTrue(owner.request_exit())
            self.assertTrue(owner.request_exit())
        host.checkpoint.assert_called_once_with()
        host.screen_privacy.dispose.assert_called_once_with()
