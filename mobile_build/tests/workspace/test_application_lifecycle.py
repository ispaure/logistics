"""Exit, replacement and abandoned startup share host resource retirement."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from mobile.application_lifecycle import lifecycle


class HostLifecycleTests(unittest.TestCase):
    def host(self):
        return NS(active_host=True, store=Mock(), credential_document_lists=Mock(),
                  chat_current=object(), checkpoint_chat=Mock(return_value=True),
                  startup_task=Mock(done=Mock(return_value=False)),
                  vault_browser=Mock(embedded=None), memory_pressure=Mock(), screen_privacy=Mock(),
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
        with patch('mobile.markdown_speech.stop_markdown_speech'), \
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
        host.cloud_startup_task = None
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
        with patch('mobile.markdown_speech.stop_markdown_speech'), \
                patch('features.books.mobile.media_controls.stop_media'):
            self.assertTrue(owner.request_exit())
            self.assertTrue(owner.request_exit())
        self.assertFalse(host.active_host)
        host.checkpoint.assert_called_once_with()
        host.screen_privacy.dispose.assert_called_once_with()

    def test_replacement_retires_native_views_after_preservation_and_before_host_reuse(self):
        host = self.host()
        host.text_views = {'doc': Mock()}
        host._keyboard_dismissal, host.seasonal_snow = Mock(), Mock()
        host.adaptive, host.routes, host.native_host = Mock(), Mock(), Mock()
        order = []
        host.store.flush_checkpoints.side_effect = lambda: order.append('preserve')
        host.routes.uninstall.side_effect = lambda: order.append('routes')
        host.native_host.dispose.side_effect = lambda: order.append('navigation')
        with patch('mobile.markdown_speech.stop_markdown_speech'), \
                patch('features.books.mobile.media_controls.stop_media'):
            lifecycle(host).retire_for_replacement()
            lifecycle(host).retire_for_replacement()
        self.assertEqual(order, ['preserve', 'routes', 'navigation'])
        host.text_views['doc'].dispose.assert_called_once_with()
        host._keyboard_dismissal.dispose.assert_called_once_with()
        host.seasonal_snow.dispose.assert_called_once_with()
        host.adaptive.uninstall.assert_called_once_with()
        self.assertFalse(host.active_host)

    def test_replaced_host_ignores_late_native_window_resize(self):
        from mobile.app import LogisticsMobile
        LogisticsMobile.resize_workspace(NS(active_host=False), object())

    def test_successful_exit_retires_the_same_host_resources_as_replacement(self):
        host = self.host()
        host.cloud_busy = False
        host.cloud_startup_task = None
        host.retire_private_comic_batch = Mock()
        host.checkpoint = Mock(return_value=True)
        host.startup_document_task, host.incoming_task = Mock(), Mock()
        host._transfer_controller = Mock()
        host.text_views = {'doc': Mock()}
        host.native_host, host.routes, host.adaptive = Mock(), Mock(), Mock()
        host.scene_manager = NS(external_comics=Mock())
        panel = Mock()
        host._notebook_views, host.notebook_panel = {'doc': panel}, panel
        panel.busy, panel.document = False, None
        owner = lifecycle(host)
        self.assertTrue(owner.request_exit())
        self.assertTrue(owner.request_exit())
        host.checkpoint.assert_called_once_with()
        for task in (host.startup_document_task, host.incoming_task):
            task.cancel.assert_called_once_with()
        for resource in (panel, host._transfer_controller, host.text_views['doc'],
                         host.native_host, host.scene_manager.external_comics):
            resource.dispose.assert_called_once_with()
        host.routes.uninstall.assert_called_once_with()
        host.adaptive.uninstall.assert_called_once_with()
        host.workspace.invalidate.assert_called_once_with('doc')

    def test_checkpoint_veto_keeps_tasks_and_native_callbacks_live_for_retry(self):
        host = self.host()
        host.cloud_busy = False
        host.cloud_startup_task = None
        host.retire_private_comic_batch = Mock()
        host.checkpoint = Mock(return_value=False)
        host.native_host, host.incoming_task = Mock(), Mock()
        self.assertFalse(lifecycle(host).request_exit())
        self.assertTrue(host.active_host)
        host.native_host.dispose.assert_not_called()
        host.incoming_task.cancel.assert_not_called()
        host.workspace.invalidate.assert_not_called()

    def test_partial_startup_failure_retires_only_created_resources_without_saving(self):
        host = NS(active_host=True, _startup_in_progress=True, checkpoint=Mock(),
                  memory_pressure=Mock(), routes=Mock(), startup_task=Mock(),
                  startup_document_task=Mock(), startup_screen=NS(cover=Mock()),
                  main_window=NS(on_lose_focus=Mock(), on_gain_focus=Mock(), on_resize=Mock()))
        owner = lifecycle(host)
        self.assertTrue(owner.request_exit())
        self.assertTrue(owner.request_exit())
        self.assertTrue(owner.startup_aborted)
        self.assertFalse(host.active_host)
        host.checkpoint.assert_not_called()
        host.memory_pressure.dispose.assert_called_once_with()
        host.routes.uninstall.assert_called_once_with()
        host.startup_task.cancel.assert_called_once_with()
        host.startup_document_task.cancel.assert_called_once_with()
        host.startup_screen.cover.dispose.assert_called_once_with()
        self.assertIsNone(host.main_window.on_lose_focus)
        self.assertIsNone(host.main_window.on_gain_focus)
        self.assertIsNone(host.main_window.on_resize)

    def test_cleanup_failure_does_not_skip_other_resources_and_can_be_retried(self):
        broken, healthy = Mock(), Mock()
        broken.dispose.side_effect = RuntimeError('private-provider-detail')
        host = NS(active_host=True, memory_pressure=broken, screen_privacy=healthy,
                  native_host=Mock())
        owner = lifecycle(host)
        with self.assertLogs('mobile.application_lifecycle', level='ERROR') as logs:
            owner.abort_startup()
        self.assertNotIn('private-provider-detail', '\n'.join(logs.output))
        self.assertFalse(host.active_host)
        healthy.dispose.assert_called_once_with()
        host.native_host.dispose.assert_called_once_with()
        broken.dispose.side_effect = None
        owner.abort_startup()
        self.assertEqual(broken.dispose.call_count, 2)
        healthy.dispose.assert_called_once_with()
        host.native_host.dispose.assert_called_once_with()

    def test_replacement_does_not_dispose_process_shared_external_display(self):
        host = self.host()
        host.scene_manager = NS(external_comics=Mock())
        lifecycle(host).retire_for_replacement()
        host.scene_manager.external_comics.dispose.assert_not_called()

    def test_aborted_startup_exit_retires_late_resources_without_checkpoint_or_shared_shutdown(self):
        host = NS(active_host=True, memory_pressure=Mock(), checkpoint=Mock(),
                  scene_manager=NS(external_comics=Mock()))
        owner = lifecycle(host)
        first = host.memory_pressure
        owner.abort_startup()
        host.memory_pressure = Mock()
        self.assertTrue(owner.request_exit())
        first.dispose.assert_called_once_with()
        host.memory_pressure.dispose.assert_called_once_with()
        host.checkpoint.assert_not_called()
        host.scene_manager.external_comics.dispose.assert_not_called()

    def test_android_adapter_cannot_restore_window_callbacks_after_retirement(self):
        window = NS(on_resize=Mock(), on_gain_focus=Mock(), on_lose_focus=Mock())
        navigation = Mock()
        navigation.dispose.side_effect = lambda: setattr(window, 'on_resize', Mock())
        host = NS(active_host=True, main_window=window, native_host=navigation)
        lifecycle(host).abort_startup()
        self.assertIsNone(window.on_resize)
        self.assertIsNone(window.on_gain_focus)
        self.assertIsNone(window.on_lose_focus)

    def test_scheduled_reset_notice_can_still_reflow_its_live_window(self):
        from mobile.app import LogisticsMobile
        content = object()
        host = NS(active_host=False, _reset_scheduled=True,
                  main_window=NS(content=content, size=NS(width=640)))
        with patch('mobile.layout_events.native_resize_changed', return_value=True), \
                patch('mobile.keyboard.fit_editors'), patch('mobile.settings.forms.fit_section') as fit:
            LogisticsMobile.resize_workspace(host)
        fit.assert_called_once_with(content, 640)
