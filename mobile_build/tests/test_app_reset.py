"""Destructive reset boundaries, interruption recovery and explicit confirmation."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch

from mobile.app_reset import RESET_MARKER, schedule_reset, finish_pending_reset
from mobile.app import LogisticsMobile


class AppResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / 'private'
        self.private.mkdir()
        self.public = self.root / 'public'
        self.public.mkdir()
        self.card = self.root / 'card'
        self.card.mkdir()
        for folder in (self.private, self.public, self.card):
            (folder / 'keep.txt').write_text('bytes')

    def test_erases_private_public_config_and_cache_but_never_external_links(self):
        config = self.private / 'Config'
        config.mkdir()
        (config / 'settings.ini').write_text('secret')
        (self.public / 'linked-card').symlink_to(self.card, target_is_directory=True)
        schedule_reset(self.private)
        keys = Mock()
        self.assertTrue(finish_pending_reset(self.private, [self.public, config], erase_keys=keys))
        keys.assert_called_once_with()
        self.assertFalse(list(self.private.iterdir()))
        self.assertFalse(list(self.public.iterdir()))
        self.assertEqual((self.card / 'keep.txt').read_text(), 'bytes')
        self.assertFalse(finish_pending_reset(self.private, [self.public], erase_keys=keys))

    def test_locked_keys_preserve_files_and_retry_request(self):
        schedule_reset(self.private)
        with self.assertRaises(ValueError):
            finish_pending_reset(self.private, [self.public], erase_keys=Mock(side_effect=ValueError('locked')))
        self.assertTrue((self.private / RESET_MARKER).is_file())
        self.assertTrue((self.private / 'keep.txt').is_file())
        self.assertTrue((self.public / 'keep.txt').is_file())
        self.assertTrue(finish_pending_reset(self.private, [self.public], erase_keys=Mock()))

    def test_interrupted_erasure_keeps_request_and_finishes_on_retry(self):
        schedule_reset(self.private)
        from mobile.app_reset import erase_contents
        with patch('mobile.app_reset.erase_contents', side_effect=[None, OSError('interrupted')]):
            with self.assertRaises(OSError):
                finish_pending_reset(self.private, [self.public], erase_keys=Mock())
        self.assertTrue((self.private / RESET_MARKER).is_file())
        self.assertTrue(finish_pending_reset(self.private, [self.public], erase_keys=Mock()))
        self.assertFalse(list(self.private.iterdir()))
        self.assertFalse(list(self.public.iterdir()))

    def test_invalid_marker_and_linked_root_never_erase(self):
        marker = self.private / RESET_MARKER
        marker.write_text(json.dumps({'schema': 1, 'root': str(self.card)}))
        keys = Mock()
        with self.assertRaises(ValueError):
            finish_pending_reset(self.private, [self.public], erase_keys=keys)
        keys.assert_not_called()
        marker.unlink()
        schedule_reset(self.private)
        link = self.root / 'alias'
        link.symlink_to(self.card, target_is_directory=True)
        with self.assertRaises(ValueError):
            finish_pending_reset(self.private, [link], erase_keys=keys)
        self.assertTrue((self.card / 'keep.txt').exists())
        keys.assert_not_called()


class AppResetUITests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        LogisticsMobile.storage_root = Path(self.temp.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_app_reset()

    def run_reset(self):
        self.app.loop.run_until_complete(self.app.confirm_app_reset())

    def test_requires_phrase_and_cancel_preserves_data(self):
        self.assertIn('Reset', self.app.settings_navigation.sections)
        self.assertFalse(self.app.reset_button.enabled)
        with patch('mobile.reset_ui.reset_android') as erase:
            self.run_reset()
            erase.assert_not_called()
            self.app.reset_phrase.value = 'ERASE'
            self.assertTrue(self.app.reset_button.enabled)
            with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value=False)):
                self.run_reset()
            erase.assert_not_called()
        self.assertFalse((self.app.private_root / RESET_MARKER).exists())

    def test_busy_or_second_window_blocks_reset_and_rechecks_after_confirmation(self):
        self.app.reset_phrase.value = 'ERASE'
        with patch('mobile.reset_ui.reset_android') as erase:
            self.app.transfer_busy = True
            self.run_reset()
            self.assertIn('Wait', self.app.reset_status.text)
            self.app.transfer_busy = False
            self.app.scene_manager.owners.hosts['other'] = object()
            self.run_reset()
            self.assertIn('other', self.app.reset_status.text)
            self.app.scene_manager.owners.hosts.pop('other')
            async def start_transfer(dialog):
                self.app.transfer_busy = True
                return True
            with patch.object(self.app.main_window, 'dialog', side_effect=start_transfer):
                self.run_reset()
            erase.assert_not_called()

    def test_android_invokes_own_app_clear_data_only_after_confirmation(self):
        self.app.reset_phrase.value = 'ERASE'
        text = ' '.join(str(getattr(child, 'text', '')) for child in self.app.reset_page.children)
        self.assertIn('app-owned storage folders on SD cards', text)
        with patch('mobile.reset_ui.reset_android') as erase, \
                patch.object(self.app.main_window, 'dialog', AsyncMock(return_value=True)):
            self.run_reset()
        erase.assert_called_once_with(self.app)
        self.assertFalse((self.app.private_root / RESET_MARKER).exists())

    def test_ios_schedules_durable_reset_locks_ui_and_does_not_save_on_exit(self):
        self.app.reset_phrase.value = 'ERASE'
        with patch('mobile.reset_ui.is_ios', return_value=True), \
                patch.object(self.app.main_window, 'dialog', AsyncMock(return_value=True)):
            self.run_reset()
        self.assertEqual(json.loads((self.app.private_root / RESET_MARKER).read_text()), {'schema': 1})
        self.assertTrue(self.app._reset_scheduled)
        self.assertFalse(self.app.active_host)
        self.assertFalse(self.app.reset_button.enabled)
        self.app.reset_phrase_changed()
        self.assertFalse(self.app.reset_button.enabled)
        notice = ' '.join(child.text for child in self.app.main_window.content.content.children)
        self.assertIn('not been erased yet', notice)
        self.assertIn('Home Screen is not enough', notice)
        with patch('mobile.reset_ui.schedule_reset') as schedule:
            self.run_reset()
        schedule.assert_not_called()
        with patch.object(self.app.store, 'checkpoint') as checkpoint:
            self.assertTrue(self.app.checkpoint())
            self.assertTrue(self.app.exit_app(self.app))
        checkpoint.assert_not_called()
        self.assertIsNot(self.app.main_window.content, self.app.navigation)
