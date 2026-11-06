"""Storage settings gate switching on permission, active work and confirmation."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import toga
from unittest.mock import AsyncMock, patch

from mobile.app import LogisticsMobile
from services.documents.locations import collection_path, switch_location


def widgets(root):
    yield root
    for child in root.children:
        yield from widgets(child)
    content = getattr(root, 'content', None)
    if content is not None:
        yield from widgets(content)


def button(root, title):
    return next(widget for widget in widgets(root)
                if isinstance(widget, toga.Button)
                and getattr(widget, '_settings_source_text', widget.text) == title)


class StorageUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.card = root / 'card'
        self.card.mkdir()
        private = root / 'app'
        private.mkdir()
        LogisticsMobile.storage_root = private
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(close_loop, self.app.loop)
        self.addCleanup(self.app.main_window.close)
        sdk = patch('mobile.storage_ui.android_sdk', return_value=30)
        sdk.start()
        self.addCleanup(sdk.stop)
        with patch('mobile.storage_ui.android_drives', return_value={'App internal storage': None, 'SD card': self.card}):
            self.app.show_collection_storage()
        self.app.collection_drive.value = 'SD card'

    def test_android9_sd_card_copy_needs_no_all_files_grant(self):
        source = collection_path(self.app.private_root)
        source.mkdir(exist_ok=True)
        (source / 'book.txt').write_bytes(b'keep this')
        with patch('mobile.storage_ui.android_sdk', return_value=28), \
                patch('mobile.storage_ui.android_drives', return_value={'App internal storage': None, 'SD card': self.card}), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.show_collection_storage()
            self.app.collection_drive.value = 'SD card'
            self.app.storage_controller()._show_storage_review('copy')
            text = ' '.join(' '.join(str(getattr(child, 'text', '')).split()) for child in widgets(self.app.collection_storage_page))
            self.assertIn('No storage permission is needed', text)
            self.assertIn('uninstall', text)
            self.assertNotIn('Allow SD card / shared storage access', text)
            self.app.collection_drive.value = 'SD card'
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertEqual((self.card / 'Logistics/Local/book.txt').read_bytes(), b'keep this')
        self.assertEqual((source / 'book.txt').read_bytes(), b'keep this')
        self.assertEqual(collection_path(self.app.private_root), self.card / 'Logistics/Local')
        exit_app.assert_called_once()

    def test_android9_permission_action_refreshes_without_opening_settings(self):
        with patch('mobile.storage_ui.android_sdk', return_value=28), \
                patch.object(self.app, 'show_collection_storage') as refresh:
            self.app.allow_collection_storage()
        refresh.assert_called_once_with()

    def test_permission_is_required_without_writing_files(self):
        with patch('mobile.storage_ui.all_files_allowed', return_value=False):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertIn('enable permission', ' '.join(self.app.collection_storage_status.text.split()))
        self.assertFalse((self.card / 'Logistics').exists())

    def test_confirmation_cancel_does_not_switch(self):
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertFalse((self.card / 'Logistics').exists())

    def test_confirmation_rechecks_work_and_restores_controls_without_running_storage(self):
        for action in ('copy', 'recover', 'empty', 'wipe'):
            for changed_state in ('busy', 'checkpoint'):
                with self.subTest(action=action, changed_state=changed_state):
                    async def confirm(dialog):
                        self.assertTrue(self.app._storage_changing)
                        self.assertFalse(self.app.collection_drive.enabled)
                        self.assertFalse(self.app.collection_copy.enabled)
                        if changed_state == 'busy':
                            self.app.transfer_busy = True
                        else:
                            checkpoint.return_value = False
                        return True

                    with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                            patch.object(self.app, 'checkpoint', return_value=True) as checkpoint, \
                            patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=confirm)), \
                            patch('mobile.storage_ui.' + {'copy': 'switch_location', 'recover': 'recover_location',
                                  'empty': 'start_empty_location', 'wipe': 'wipe_destination'}[action]) as worker:
                        operation = {'copy': self.app.change_collection_storage,
                                     'recover': self.app.recover_collection_storage,
                                     'empty': self.app.start_empty_collection,
                                     'wipe': self.app.wipe_collection_storage}[action]
                        self.app.loop.run_until_complete(operation(self.app.collection_copy))
                    worker.assert_not_called()
                    self.assertFalse(self.app._storage_changing)
                    self.assertTrue(self.app.collection_drive.enabled)
                    self.assertTrue(self.app.collection_copy.enabled)
                    self.assertFalse(self.app.cloud_busy)
                    self.assertFalse((self.card / 'Logistics').exists())
                    self.app.transfer_busy = False

    def test_switch_verifies_data_and_closes_app_for_restart(self):
        source = collection_path(self.app.private_root)
        source.mkdir(exist_ok=True)
        (source / 'book.txt').write_bytes(b'keep this')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertEqual((self.card / 'Logistics/Local/book.txt').read_bytes(), b'keep this')
        self.assertFalse(self.app.cloud_busy)
        exit_app.assert_called_once()

    def test_worker_progress_is_rendered_and_failure_keeps_retry_available(self):
        import threading
        ui_thread = threading.get_ident()
        def fail(root, volume, *, progress):
            self.assertNotEqual(threading.get_ident(), ui_thread)
            progress(dict(phase='Copying Local', path='Local/book.epub', bytes=1024, total=2048, files=0))
            raise OSError('Card disconnected')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch('mobile.storage_ui.switch_location', side_effect=fail):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        page = self.app.collection_storage_page
        text = ' '.join(str(getattr(child, 'text', '')) for child in page.children)
        self.assertIn('Card disconnected', text)
        self.assertIn('Stopped before completion', text)
        self.assertTrue(page.children[-1].enabled)
        self.assertFalse(self.app._storage_changing)
        self.assertFalse(self.app.cloud_busy)
        self.assertFalse((self.card / 'Logistics').exists())

    def test_busy_operation_prevents_switch(self):
        self.app.transfer_busy = True
        self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertIn('Wait', self.app.collection_storage_status.text)
        self.assertFalse((self.card / 'Logistics').exists())

    def test_preview_identifies_target_and_never_offers_erasing_active_location(self):
        self.assertIn('No collection files found', self.app.collection_target_status.text)
        self.assertTrue(self.app.collection_erase.enabled)
        self.app.collection_drive.value = 'App internal storage'
        self.assertIn('Currently in use', self.app.collection_target_status.text)
        self.assertFalse(self.app.collection_erase.enabled)
        self.assertFalse(self.app.collection_copy.enabled)

    def test_guided_home_has_one_main_action_and_collapsed_secondary_options(self):
        from mobile.settings.forms import NOTE_FONT_SIZE, OPTION_FONT_SIZE
        page = self.app.collection_storage_page
        self.assertNotIn(self.app.collection_drive, list(widgets(page)))
        self.assertNotIn(self.app.collection_erase, list(widgets(page)))
        self.assertFalse(any(getattr(widget, 'text', '') == 'Use files from another location' for widget in widgets(page)))
        button(page, 'Other storage options +').on_press()
        self.assertIsNotNone(button(page, 'Use files from another location'))
        self.assertIsNotNone(button(page, 'Delete files from an old location'))
        button(page, 'Change location').on_press()
        page = self.app.collection_storage_page
        self.assertIn(self.app.collection_drive, list(widgets(page)))
        self.assertEqual(self.app.collection_drive.style.font_size, OPTION_FONT_SIZE)
        self.assertEqual(self.app.collection_target_status.style.font_size, NOTE_FONT_SIZE)
        self.assertFalse((self.card / 'Logistics').exists())

    def test_delete_location_uses_red_bottom_button_and_never_continue(self):
        from mobile.palette import LIGHT, DARK, EINK
        with patch('mobile.storage_ui.all_files_allowed', return_value=True):
            self.app.storage_controller()._show_storage_target('wipe')
            page = self.app.collection_storage_page
            footer = self.app.storage_controller()._collection_delete_footer
            self.assertIn(footer, list(widgets(self.app.body)))
            scroll, mounted_footer = footer.parent.children
            self.assertIs(scroll.content, page)
            self.assertIs(mounted_footer, footer)
            self.assertIs(footer.children[-1], self.app.collection_erase)
            self.assertFalse(any(getattr(widget, 'text', '') == 'Continue' for widget in widgets(page)))
            self.assertEqual(self.app.collection_erase._impl._surface_roles[:2], ('destructive_fill', 'on_destructive'))
            self.assertEqual(LIGHT['destructive_fill'], '#d32f2f')
            self.assertEqual(DARK['on_destructive'], '#ffffff')
            self.assertEqual(EINK['destructive_fill'], '#000000')
            self.assertTrue(self.app.collection_erase.enabled)
            self.app.collection_drive.value = 'App internal storage'
            self.assertFalse(self.app.collection_erase.enabled)
            self.assertIs(footer.children[-1], self.app.collection_erase)

    def test_choosing_and_reviewing_location_does_not_copy_or_switch(self):
        with patch('mobile.storage_ui.all_files_allowed', return_value=True):
            button(self.app.collection_storage_page, 'Change location').on_press()
            button(self.app.collection_storage_page, 'Continue').on_press()
        self.assertIsNotNone(button(self.app.collection_storage_page, 'Copy and switch'))
        self.assertFalse((self.card / 'Logistics').exists())
        self.assertNotEqual(collection_path(self.app.private_root), self.card / 'Logistics/Local')
        self.assertTrue(self.app.routes.back())
        self.assertIn(self.app.collection_drive, list(widgets(self.app.body)))
        self.app.collection_drive.value = 'App internal storage'
        self.assertFalse(button(self.app.body, 'Continue').enabled)
        self.app.collection_drive.value = 'SD card'
        self.assertTrue(button(self.app.body, 'Continue').enabled)

    def test_delete_content_and_footer_both_refit_on_resize(self):
        from mobile.layout_participants import participants, LayoutFrame
        with patch('mobile.storage_ui.all_files_allowed', return_value=True):
            self.app.storage_controller()._show_storage_target('wipe')
        sizes = []
        for width in (280, 1000):
            participants(self.app).reflow(LayoutFrame(width, lambda destination, **kwargs: width))
            sizes.append((self.app.collection_target_status._settings_available_width,
                          self.app.collection_erase._settings_available_width))
        self.assertLess(sizes[0][0], sizes[1][0])
        self.assertLess(sizes[0][1], sizes[1][1])
        self.assertEqual(self.app.collection_erase.style.height, 48)

    def test_modern_permission_is_contextual_and_rechecked_on_return(self):
        with patch('mobile.storage_ui.all_files_allowed', return_value=False):
            self.app.storage_controller()._show_storage_review('copy')
        self.assertNotIn(self.app.collection_copy, list(widgets(self.app.collection_storage_page)))
        self.assertIsNotNone(button(self.app.collection_storage_page, 'Open Android settings'))
        with patch('mobile.storage_ui.all_files_allowed', return_value=True):
            button(self.app.collection_storage_page, 'Check access').on_press()
        self.assertIn(self.app.collection_copy, list(widgets(self.app.collection_storage_page)))
        self.assertFalse((self.card / 'Logistics').exists())

    def test_existing_destination_offers_recovery_and_disables_start_empty(self):
        target = self.card / 'Logistics/Local/keep.txt'
        target.parent.mkdir(parents=True)
        target.write_text('keep')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True):
            self.app.storage_controller()._show_storage_review('empty')
            self.assertFalse(self.app.collection_empty.enabled)
            button(self.app.collection_storage_page, 'Use existing files instead').on_press()
        self.assertIn(self.app.collection_existing, list(widgets(self.app.collection_storage_page)))
        self.assertEqual(target.read_text(), 'keep')

    def test_refresh_preserves_target_and_hides_raw_paths_in_picker(self):
        drives = {'App internal storage': None, 'SD card · /storage/test': self.card,
                  'SD card · /storage/other': self.card.parent / 'second-card'}
        with patch('mobile.storage_ui.android_drives', return_value=drives):
            self.app.show_collection_storage()
            self.app.collection_drive.value = 'SD card'
            self.app.storage_controller()._show_storage_target('copy')
            button(self.app.collection_storage_page, 'Refresh locations').on_press()
        self.assertEqual(list(self.app.collection_drives), ['App internal storage', 'SD card', 'SD card (2)'])
        self.assertEqual(self.app.collection_drive.value, 'SD card')
        self.assertEqual(self.app.collection_drives['SD card'], self.card)

    def test_start_empty_keeps_current_files_and_closes_after_confirming(self):
        old = collection_path(self.app.private_root)
        old.mkdir(exist_ok=True)
        (old / 'keep.txt').write_text('old')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.start_empty_collection())
        self.assertEqual((old / 'keep.txt').read_text(), 'old')
        self.assertFalse(list(collection_path(self.app.private_root).iterdir()))
        exit_app.assert_called_once()

    def test_recover_internal_after_card_removal_without_cloud_browser(self):
        source = collection_path(self.app.private_root)
        source.mkdir(exist_ok=True)
        (source / 'book.txt').write_bytes(b'backup')
        switch_location(self.app.private_root, self.card)
        self.card.rename(self.card.parent / 'removed')
        self.app.collection_drive.value = 'App internal storage'
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.recover_collection_storage())
        self.assertEqual(collection_path(self.app.private_root), source)
        self.assertFalse(self.app.cloud_busy)
        exit_app.assert_called_once()

    def test_cancel_wipe_preserves_files_and_success_keeps_app_open(self):
        target = self.card / 'Logistics/Local/old.txt'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'old')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)):
            self.app.loop.run_until_complete(self.app.wipe_collection_storage())
        self.assertTrue(target.exists())
        self.assertFalse(self.app._storage_changing)
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.wipe_collection_storage())
        self.assertFalse(target.exists())
        self.assertIn('erased', self.app.collection_storage_status.text)
        self.assertFalse(self.app.cloud_busy)
        exit_app.assert_not_called()
