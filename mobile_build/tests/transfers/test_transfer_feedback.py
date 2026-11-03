"""Transfer feedback preserves navigation and leaves local reader commands usable."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

import toga

from mobile.app import LogisticsMobile
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.support.readers import RemoteClient


class TransferFeedbackTests(TestCase):
    def test_rclone_sleep_lease_survives_cancel_until_worker_retires(self):
        import asyncio
        from threading import Event
        from commonUtils.runtime.operations import check_cancelled
        app = self.app
        started, release = Event(), Event()
        awake = Mock()
        def work(client, cancelled, progress):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Transfer fixture timed out')
            check_cancelled(cancelled)
            return 1
        async def exercise():
            with patch.object(app, 'mirror_connection_ready', AsyncMock(return_value=True)), \
                    patch('mobile.keep_awake.AwakeLease', return_value=awake):
                task = asyncio.create_task(app.run_mirror_work(work, 'pull'))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 5))
                    self.assertTrue(app.transfer_busy)
                    app.cancel_mirror_transfer()
                    awake.close.assert_not_called()
                finally:
                    release.set()
                    await task
                awake.close.assert_called_once_with()
                self.assertFalse(app.transfer_busy)
        app.loop.run_until_complete(exercise())

    def test_rclone_failure_releases_sleep_lease(self):
        awake = Mock()
        def failed(*args):
            raise OSError('Transfer failed')
        with patch.object(self.app, 'mirror_connection_ready', AsyncMock(return_value=True)), \
                patch('mobile.keep_awake.AwakeLease', return_value=awake):
            self.assertFalse(self.app.loop.run_until_complete(self.app.run_mirror_work(failed, 'pull')))
        awake.close.assert_called_once_with()
        self.assertFalse(self.app.transfer_busy)
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        LogisticsMobile.storage_root = Path(temporary.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.cloud_client = RemoteClient()
        self.app.show_cloud(present=False)

    def test_progress_uses_compact_metrics_and_discloses_secondary_counters(self):
        app = self.app
        app.transfer_busy = True
        app.transfer_epoch = 7
        app.transfer_endpoints = ('Local/Photos', 'Cloud:Photos')
        app.show_transfers()
        app.publish_mirror_progress(7, dict(phase='Transferring', files=2, total_files=4,
            done=12500000, total=25000000, active=1, listed=12, checks=8))
        controller = app.transfer_controller()
        model = app.transfer_view.model
        self.assertEqual(model['percentage'], 50)
        self.assertEqual(model['files'], 2)
        self.assertEqual(model['total_files'], 4)
        self.assertEqual(model['checks'], 8)
        first = app.transfer_view
        app.show_transfers()
        self.assertIs(app.transfer_view, first)
        self.assertEqual(controller.transfer_files.text, 'Files\n2 / 4')

    def test_transfer_settings_remain_reachable_from_setup_and_return_to_setup(self):
        app = self.app
        app.loaded_remote_names = lambda: ['Personal']
        app.cloud_busy = False
        app.show_local_push('Personal')
        setup = app.transfer_controller()._transfer_setup_surface
        app.loop.run_until_complete(setup.dispatch('settings', {}))
        self.assertEqual(app.routes.screens['files'][-1][0], 'transfer-settings')
        panel = app.body
        # Cancel is the last button of the feature's native settings form.
        form = panel.children[0] if len(panel.children) == 1 else panel
        while not any(isinstance(child, toga.Button) and child.text == 'Cancel' for child in form.children):
            form = form.children[-1]
        next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Cancel').on_press()
        self.assertEqual(app.routes.screens['files'][-1][0], 'local-push')
        self.assertFalse(setup.closed)

    def test_declined_credentials_leave_push_setup_usable(self):
        app = self.app
        app.loaded_remote_names = lambda: ['Personal']
        app.cloud_busy = False
        app.show_local_push('Personal')
        setup = app.transfer_controller()._transfer_setup_surface
        setup.pending = None
        setup.delivered_revision = setup.revision
        async def exercise():
            with patch.object(app, 'require_remote_credentials_async', new=AsyncMock(return_value=False)):
                await setup.dispatch('start-review', dict(revision=str(setup.revision)))
                self.assertFalse(await app.transfer_task)
            self.assertFalse(setup.closed)
            self.assertEqual(app.routes.screens['files'][-1][0], 'local-push')
        app.loop.run_until_complete(exercise())

    def test_readers_never_show_sync_status(self):
        from mobile.reader_chrome import reader_buttons, transfer_control
        app = self.app
        app.show_documents(destination='documents')
        view = app.editor_view.document_view
        app.transfer_busy = app.transfer_notification = True
        app.transfer_percentage = 42
        app.refresh_transfer_status()
        self.assertIsNone(view.transfer_banner)
        self.assertIsNone(transfer_control(app, view))
        self.assertEqual(reader_buttons(app, view), list(view._native_reader_buttons()))
        self.assertFalse(any(button.parent is not None for _, _, button, _ in
                             getattr(app, '_sync_status_controls', {}).values()))

    def test_main_tabs_have_one_sync_icon_and_navigation_never_reopens_details(self):
        app = self.app
        app.transfer_busy = True
        app.transfer_percentage = 42
        app._transfer_cancel = Mock()
        for destination in ('home', 'files', 'documents', 'chat', 'settings'):
            with self.subTest(destination=destination):
                app.routes.return_to(destination)
                app.refresh_transfer_status()
                _, _, button, _ = app._sync_status_controls[destination]
                self.assertIsNotNone(button.parent)
                self.assertEqual(button._impl._surface_roles, ('hover', 'text', False))
                self.assertTrue(app._sync_status_controls[destination][3])
                if destination == 'home':
                    self.assertIs(app._home_status_row.parent, app.home_content)
                else:
                    self.assertGreater(len(button.parent.children), 1)
                self.assertIn('42%', button.accessible_name)
                self.assertEqual(sum((control if inline else row).parent is not None
                                     for _, row, control, inline in app._sync_status_controls.values()), 1)
                button.on_press()
                self.assertEqual(app.routes.screens[destination][-1][0], 'transfers')
                other = 'files' if destination == 'home' else 'home'
                app.routes.return_to(other)
                app.routes.return_to(destination)
                self.assertFalse(app.routes.screens[destination])
                self.assertTrue(app.transfer_busy)
                app._transfer_cancel.set.assert_not_called()
        app.routes.return_to('home')
        button = app._sync_status_controls['home'][2]
        self.assertIs(button.parent, app._home_status_row)
        self.assertIsNone(app.home_sections.content.transfer_banner)
        app.transfer_busy = app.transfer_notification = False
        app.refresh_transfer_status()
        self.assertIsNone(app._home_status_row.parent)

    def test_chat_title_reserves_sync_space_and_restores_it_on_dismissal(self):
        app = self.app
        app.routes.return_to('chat')
        app.update_chat_header()
        width = app.chat_title.style.width
        app.transfer_busy = True
        app.transfer_percentage = 42
        app.refresh_transfer_status()
        self.assertEqual(app.chat_title.style.width, width - 56)
        app.transfer_busy = app.transfer_notification = False
        app.refresh_transfer_status()
        self.assertEqual(app.chat_title.style.width, width)

    def test_settings_refits_category_without_restyling_sync_on_resize(self):
        app = self.app
        app.routes.return_to('settings')
        navigation = app.settings_navigation
        category = next(iter(navigation.buttons.values()))
        original_width = category._settings_available_width
        app.transfer_busy = True
        app.transfer_percentage = 42
        app.refresh_transfer_status()
        button = app._sync_status_controls['settings'][2]
        self.assertEqual(category._settings_available_width, original_width - 56)
        from types import SimpleNamespace
        app.main_window.size = SimpleNamespace(width=900, height=600)
        navigation.reflow()
        self.assertEqual(button.style.height, 48)
        self.assertEqual(button._impl._surface_roles, ('hover', 'text', False))
        narrow_width = category._settings_available_width
        app.transfer_busy = app.transfer_notification = False
        app.refresh_transfer_status()
        self.assertEqual(category._settings_available_width, narrow_width + 56)

    def test_same_progress_does_not_repaint_and_indeterminate_timer_stops_in_viewer(self):
        app = self.app
        app.show_home()
        app.transfer_busy = True
        app.transfer_percentage = 42
        app.refresh_transfer_status()
        button = app._sync_status_controls['home'][2]
        with patch.object(button.renderer, 'apply') as paint:
            for _ in range(5):
                app.refresh_transfer_status()
            paint.assert_not_called()
        app.transfer_percentage = 73
        app.refresh_transfer_status()
        self.assertIn('73%', button.accessible_name)
        app.transfer_percentage = None
        app.refresh_transfer_status()
        pending = app._sync_status_tick
        self.assertIsNotNone(pending)
        app.show_documents(destination='documents')
        self.assertTrue(pending.cancelled())
        self.assertIsNone(app._sync_status_tick)
        app.transfer_busy = False
        app.transfer_notification = False

    def test_completion_timeout_clears_notice_but_cannot_dismiss_a_later_transfer(self):
        app = self.app
        scheduled = []
        original = app.loop.call_later

        def later(delay, callback, *args, **kwargs):
            if delay == 5 and callback.__name__ == 'clear_completion':
                scheduled.append(callback)
                return Mock()
            return original(delay, callback, *args, **kwargs)

        with patch.object(app.loop, 'call_later', side_effect=later):
            self.assertTrue(app.loop.run_until_complete(app.run_mirror_work(
                lambda client, cancelled, progress: ('complete', 0), 'pull')))
        self.assertTrue(app.transfer_notification)
        self.assertEqual(len(scheduled), 1)
        scheduled[0]()
        self.assertFalse(app.transfer_notification)
        app.transfer_notification = app.transfer_busy = True
        app.transfer_epoch += 1
        scheduled[0]()
        self.assertTrue(app.transfer_notification)
        app.transfer_busy = False
        scheduled[0]()
        self.assertTrue(app.transfer_notification)

    def test_details_back_returns_to_each_origin_and_does_not_cancel_transfer(self):
        app = self.app
        for destination in ('home', 'files', 'documents'):
            with self.subTest(destination=destination):
                app.routes.return_to(destination)
                origin = app.body
                app.transfer_busy = True
                app._transfer_cancel = Mock()
                app.show_transfers()
                app.show_transfers()  # A progress/completion redraw keeps the same return path.
                self.assertEqual(app.native_host.state.destination, destination)
                app.loop.run_until_complete(app.transfer_view.dispatch('background', {}))
                self.assertIs(app.body, origin)
                self.assertTrue(app.transfer_busy)
                app._transfer_cancel.set.assert_not_called()
                app.show_transfers()
                self.assertTrue(app.routes.system_back())
                self.assertIs(app.body, origin)

    def test_cloud_preview_explains_transfer_block_without_touching_client(self):
        app = self.app
        app.transfer_busy = True
        app.set_cloud_busy(True)
        with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
            self.assertFalse(app.loop.run_until_complete(app.open_remote_document(
                dict(path='note.txt', directory=False, size=1))))
        dialog.assert_awaited_once()
        self.assertIsInstance(dialog.await_args.args[0], toga.InfoDialog)
        self.assertIn('Local copy', app.cloud_status.value)
        self.assertTrue(app.transfer_busy)


    def test_local_comic_menu_uses_activity_and_dispatches_during_transfer(self):
        app = self.app
        folder = app.private_root / 'LocalFiles'
        folder.mkdir(exist_ok=True)
        _, comic = make_books(folder)
        app.loop.run_until_complete(app.open_download(path=comic))
        reader = app.readers.active
        app.transfer_busy = True
        app.set_cloud_busy(True)
        menu = reader.reader_actions
        with patch.object(app._impl, 'native', object(), create=True):
            self.assertIs(menu.native_context(), app._impl.native)
        command = next(callback for title, callback in menu.actions if title == 'Comic pages…')
        menu.invoke(command)
        self.assertTrue(app.transfer_busy)
        from mobile.routes import contains
        self.assertTrue(contains(app.body, reader.reader_tools_view))

    def test_recent_remote_reference_explains_block_before_credentials_or_loading(self):
        from mobile.document_sources import reopen_file
        app = self.app
        app.transfer_busy = True
        app.set_cloud_busy(True)
        origin = app.body
        with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
            self.assertFalse(app.loop.run_until_complete(reopen_file(app,
                dict(type='remote', remote='Files', identity='a' * 64, key='note.txt'))))
        dialog.assert_awaited_once()
        self.assertIs(app.body, origin)
        self.assertFalse(app.cloud_client.calls)

    def test_new_and_retained_uncached_remote_sessions_explain_transfer_block(self):
        import asyncio
        from features.rclone.mobile.remote_readers import RemoteReaders
        app = self.app
        copies = RemoteReaders(app.cloud_client, 'Files')
        self.assertTrue(app.loop.run_until_complete(app.open_crypt(copies=copies, key='note.txt')))
        owner = app.private_sessions.active
        app.transfer_busy = True
        app.set_cloud_busy(True)
        app.cloud_client.calls.clear()
        with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
            self.assertFalse(app.loop.run_until_complete(app.open_crypt(copies=copies, key='note.txt')))
            self.assertFalse(app.private_sessions.activate(owner.session.id))
            app.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(dialog.await_count, 2)
        self.assertFalse(app.cloud_client.calls)
        self.assertTrue(app.transfer_busy)


class AwakeLeaseTests(TestCase):
    def test_android_overlapping_requests_restore_original_view_flag(self):
        from types import SimpleNamespace as NS
        from mobile.keep_awake import AwakeLease
        class Backend:
            __module__ = 'toga_android.app'
            @property
            def native(self):
                return self
            def getWindow(self):
                return NS(getDecorView=lambda: view)
        for original in (False, True):
            with self.subTest(original=original):
                view = Mock()
                view.getKeepScreenOn.return_value = original
                app = NS(_impl=Backend())
                first, second = AwakeLease(app), AwakeLease(app)
                first.close()
                view.setKeepScreenOn.assert_called_with(True)
                second.close()
                view.setKeepScreenOn.assert_called_with(original)
                count = view.setKeepScreenOn.call_count
                second.close()
                self.assertEqual(view.setKeepScreenOn.call_count, count)
                self.assertIsNone(app._transfer_awake_state)
