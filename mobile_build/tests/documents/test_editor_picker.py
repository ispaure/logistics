"""Owned picker state, cancellation and stale worker publication boundaries."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile


class EditorPickerTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name).resolve()
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_cloud(present=False)
        self.app.loop.run_until_complete(self.app.show_editor_open())

    def tearDown(self):
        self.app.active_host = True
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    async def wait_for_worker(self, started):
        for _ in range(200):
            if started.is_set():
                return
            await asyncio.sleep(.01)
        self.fail('Picker worker did not start')

    def test_owner_keeps_picker_state_off_the_app_and_preserves_provider_identity(self):
        app = self.app
        picker = app.editor_picker()
        self.assertNotIn('editor_browser', vars(app))
        self.assertNotIn('save_as_data', vars(app))
        self.assertIs(app.editor_browser, picker.editor_browser)
        provider = LocalFiles(Path(self.directory.name))
        app.editor_storage_roots = {'Associated provider': provider}
        self.assertIs(picker.editor_provider('Associated provider'), provider)
        app.save_as_data = b'unsaved'
        self.assertEqual(picker.save_as_data, b'unsaved')
        app.cancel_text_destination()
        self.assertIsNone(picker.save_as_data)
        self.assertIsNone(picker.save_as_source_document)

    def test_late_listing_and_error_do_not_publish_after_invalidation(self):
        app, picker = self.app, self.app.editor_picker()
        for failure in (False, True):
            for invalidation in ('cancel', 'clear', 'credentials', 'host', 'navigation'):
                with self.subTest(failure=failure, invalidation=invalidation):
                    started, release = Event(), Event()
                    original = LocalFiles.list
                    def delayed(provider, *args, **kwargs):
                        started.set()
                        if not release.wait(5):
                            raise RuntimeError('Picker fixture not released')
                        if failure:
                            raise OSError('Late list failure')
                        return original(provider, *args, **dict(kwargs, cancelled=lambda: False))
                    async def exercise():
                        await app.show_editor_open()
                        before = app.save_as_status.value
                        client = app.cloud_client
                        with patch.object(type(picker.editor_provider(picker.save_as_storage.value)), 'list', new=delayed), patch.object(
                                picker.editor_browser, 'set_entries') as publish:
                            task = asyncio.create_task(app.refresh_editor_browser())
                            try:
                                await self.wait_for_worker(started)
                                if invalidation == 'cancel':
                                    app.cancel_cloud()
                                    self.assertTrue(picker._work.cancel.is_set())
                                elif invalidation == 'clear':
                                    picker.clear()
                                    before = app.save_as_status.value
                                elif invalidation == 'credentials':
                                    app.cloud_client = object()
                                elif invalidation == 'host':
                                    app.active_host = False
                                else:
                                    app.navigation_generation += 1
                                release.set()
                                self.assertFalse(await task)
                                publish.assert_not_called()
                                self.assertEqual(app.save_as_status.value, before)
                                self.assertFalse(app.cloud_busy)
                            finally:
                                release.set()
                                await task
                                app.active_host = True
                                app.cloud_client = client
                    app.loop.run_until_complete(exercise())

    def test_cancelled_open_does_not_open_a_late_resolved_document(self):
        app = self.app
        root = app.private_root / 'LocalFiles'
        (root / 'note.md').write_text('Keep the previous editor')
        app.save_as_name.value = 'note.md'
        from commonUtils.runtime.resources.selection import ResourceSelection
        started, release = Event(), Event()
        original = ResourceSelection.resolve
        def delayed(model, *args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Picker fixture not released')
            return original(model, *args, **dict(kwargs, cancelled=lambda: False))
        async def exercise():
            with patch.object(ResourceSelection, 'resolve', new=delayed), patch.object(
                    app, 'open_crypt', new_callable=AsyncMock) as opened:
                task = asyncio.create_task(app.confirm_editor_file())
                try:
                    await self.wait_for_worker(started)
                    app.cancel_cloud()
                    release.set()
                    await task
                    opened.assert_not_awaited()
                    self.assertFalse(app.cloud_busy)
                finally:
                    release.set()
                    await task
        app.loop.run_until_complete(exercise())

    def test_cancelled_save_keeps_draft_without_publishing_or_reopening(self):
        app = self.app
        app.loop.run_until_complete(app.show_text_destination('retained.md', b'Retained draft'))
        from commonUtils.runtime.resources.mutations import save_resource_and_reopen
        started, release = Event(), Event()
        def delayed(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Save fixture not released')
            return save_resource_and_reopen(*args, **kwargs)
        async def exercise():
            with patch('commonUtils.runtime.resources.mutations.save_resource_and_reopen', side_effect=delayed), patch.object(
                    app, 'open_crypt', new_callable=AsyncMock) as opened:
                task = asyncio.create_task(app.save_text_destination())
                try:
                    await self.wait_for_worker(started)
                    app.cancel_text_destination()
                    release.set()
                    await task
                    opened.assert_not_awaited()
                    self.assertEqual(app.save_as_data, b'Retained draft')
                    self.assertFalse((app.private_root / 'LocalFiles' / 'retained.md').exists())
                    self.assertFalse(app.cloud_busy)
                finally:
                    release.set()
                    await task
        app.loop.run_until_complete(exercise())

    def test_locked_source_cannot_publish_save_as(self):
        from features.rclone.mobile.session_privacy import ResumePassword
        gate = ResumePassword('fixture-password')
        self.app.loop.run_until_complete(self.app.show_text_destination('locked.md', b'Private draft', privacy_gate=gate))
        self.app.screen_privacy.conceal()
        self.app.loop.run_until_complete(self.app.save_text_destination())
        self.assertFalse((self.app.private_root / 'LocalFiles' / 'locked.md').exists())
        self.assertEqual(self.app.save_as_data, b'Private draft')

    def test_save_as_cancel_restores_managed_origin_even_with_old_provider_active(self):
        from features.text_editor.resources import LocalTextCopies
        app = self.app
        saved = Path(self.directory.name) / 'earlier.txt'
        saved.write_text('Earlier saved file')
        app.loop.run_until_complete(app.open_crypt(copies=LocalTextCopies(LocalFiles(saved.parent)), key=saved.name, edit=True))
        previous = app.provider_sessions().active
        app.new_document(name='New draft.txt', content='Unfinished current draft')
        origin, owner = app.current, app.editor_view
        for close in ('cancel', 'back'):
            app.loop.run_until_complete(app.show_document_save_as())
            self.assertIs(app.editor_picker().origin.owner, owner)
            if close == 'cancel':
                app.cancel_text_destination()
            else:
                app.routes.back()
            self.assertIs(app.current, origin)
            self.assertIs(app.editor_view, owner)
            self.assertEqual(app.current.text, 'Unfinished current draft')
            self.assertIs(app.provider_sessions().active, previous)
            self.assertIsNone(app.editor_picker().origin)

    def test_closed_origin_never_reopens_an_unrelated_document(self):
        app = self.app
        app.new_document(name='Closed origin.txt', content='retained')
        key = app.editor_view.session.id
        app.loop.run_until_complete(app.show_document_save_as())
        self.assertTrue(app.close_session(key))
        with patch.object(app, 'show_documents_hub') as hub, patch.object(app, 'resume_crypt') as resume:
            app.cancel_text_destination(dismissed=True)
        hub.assert_called_once()
        resume.assert_not_called()
        self.assertNotIn(key, app.workspace.sessions)
