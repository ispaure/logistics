"""Transfer feedback preserves navigation and leaves local reader commands usable."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

import toga

from mobile.app import LogisticsMobile
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.reading.test_remote_readers import RemoteClient


class TransferFeedbackTests(TestCase):
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

    def test_reader_progress_uses_toolbar_and_fullscreen_hides_it(self):
        from mobile.reader_chrome import reader_buttons
        app = self.app
        app.show_documents(destination='documents')
        view = app.editor_view.document_view
        app.transfer_busy = app.transfer_notification = True
        app.transfer_percentage = 42
        app.refresh_transfer_status()
        self.assertNotIn(view.transfer_banner, view.children)
        button = reader_buttons(app, view)[0]
        self.assertEqual(button.text, '42%')
        self.assertIn('known work', button.accessible_name)
        button.on_press()
        self.assertEqual(app.routes.screens['documents'][-1][0], 'transfers')
        app.routes.back()
        view._reader_fullscreen = True
        self.assertNotIn(button, reader_buttons(app, view))
        view._reader_fullscreen = False
        app.transfer_percentage = 73
        app.refresh_transfer_status()
        self.assertIs(reader_buttons(app, view)[0], button)
        self.assertEqual(button.text, '73%')
        app.transfer_busy = False
        app.transfer_complete = True
        app.refresh_transfer_status()
        self.assertEqual(button.text, '✓')
        app.dismiss_transfer_status()
        self.assertNotIn(button, reader_buttons(app, view))

    def test_main_screen_progress_stays_above_content(self):
        app = self.app
        app.show_home()
        view = app.home_sections.content
        app.transfer_busy = True
        app.refresh_transfer_status()
        self.assertIs(view.children[0], view.transfer_banner)

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
                back = next(child for child in app.transfer_view.content.children
                            if isinstance(child, toga.Button) and child.text == 'Back')
                back.on_press()
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
        self.assertFalse(app.cloud_client.calls)

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
