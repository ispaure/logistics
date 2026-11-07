"""Independent memory-only owners, bounded resources and atomic lock guards."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from toga_dummy.utils import EventLog
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from features.text_editor.resources import LocalTextCopies


class PrivateSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(close_loop, self.app.loop)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud()
        self.local = self.root / 'LocalFiles'
        self.local.mkdir(exist_ok=True)
        self.copies = LocalTextCopies(LocalFiles(self.local))

    def run_async(self, operation):
        return self.app.loop.run_until_complete(operation)

    def open(self, name, data=b'original'):
        (self.local / name).write_bytes(data)
        self.assertTrue(self.run_async(self.app.open_crypt(copies=self.copies, key=name)))
        return self.app.private_sessions.active

    def test_local_provider_recent_survives_close_and_reopens_original(self):
        from mobile.recent_documents import RecentDocuments
        owner = self.open('remember-me.md', b'# Original')
        # Each scene stores its history beside its workspace manifest.
        recent = RecentDocuments(self.app.recent_documents.path.parent)
        self.assertEqual(recent.sessions()[0].title, 'remember-me.md')
        self.assertEqual(recent.sessions()[0].source['type'], 'local')
        self.assertFalse(self.app.recent_items(excluding=[owner.session.identity]))
        self.assertTrue(self.app.private_sessions.close(owner.session.id))
        session, summary = self.app.recent_items()[0]
        self.run_async(self.app.recent_opener(session)())
        reopened = self.app.private_sessions.active
        self.assertEqual(reopened._crypt_reader_store.provider.root, self.local)
        self.assertEqual(reopened.crypt_text.value, '# Original')

    def test_open_and_resume_use_the_document_name_as_navigation_title(self):
        with patch.object(self.app, 'show_view', wraps=self.app.show_view) as present:
            first = self.open('First.md', b'# First')
            self.assertEqual(present.call_args.kwargs['title'], 'First.md')
            self.open('Second.txt', b'Second')
            self.assertEqual(present.call_args.kwargs['title'], 'Second.txt')
            self.app.private_sessions.activate(first.session.id)
            self.assertEqual(present.call_args.kwargs['title'], 'First.md')
            first.show_view(first.crypt_view, title='Reading appearance')
            self.assertEqual(present.call_args.kwargs['title'], 'Reading appearance')

    def test_fullscreen_comic_reloads_released_page_only_after_unlock(self):
        self.app.preferences.save(comic_layout='single')
        import asyncio
        import base64
        import io
        import json
        from zipfile import ZipFile
        from services.session_auth import ResumePassword
        fixture = json.loads((Path(__file__).parents[2] / 'native_tests/tests/logisticsmobile/comic_fixture.json').read_text())
        data = io.BytesIO()
        with ZipFile(data, 'w') as archive:
            for index in range(4):
                archive.writestr(f'{index}.png', base64.b64decode(fixture['page']))
        from services.documents.readers import PrivateReader
        reader = PrivateReader('resume.cbz', data.getvalue())
        reader.key = 'resume.cbz'
        with patch.object(self.copies, 'open', return_value=reader):
            owner = self.open('resume.cbz', data.getvalue())
        owner.privacy_gate = ResumePassword('session-password')

        async def exercise():
            await owner.move_private_page(2)
            if not owner.crypt_immersive:
                owner.toggle_private_reading_mode()
            page = owner.crypt_page.value
            body = self.app.body
            privacy = self.app.screen_privacy
            for _ in range(2):
                privacy.conceal()
                self.app.release_disposable_resources()
                self.assertTrue(owner.page_suspended)
                self.assertFalse(owner.crypt_content.children)
                privacy.reveal()
                privacy.lock_password.value = 'wrong'
                await privacy.unlock()
                self.assertTrue(owner.page_suspended)
                self.assertFalse(owner.crypt_content.children)
                privacy.lock_password.value = 'session-password'
                await privacy.unlock()
                # Repeated lifecycle signals must not queue duplicate reloads.
                task = owner._resume_page_task
                privacy.reveal()
                self.assertIs(owner._resume_page_task, task)
                await task
                self.assertFalse(owner.page_suspended)
                self.assertTrue(owner.crypt_content.children)
                self.assertIsNotNone(owner.provider_spread.canvas.image)
                self.assertEqual(owner.crypt_page.value, page)
                self.assertTrue(owner.crypt_immersive)
                self.assertIs(self.app.body, body)
                self.assertIs(self.app.main_window.content, self.app.native_host.root)
            await owner.move_provider_comic(1)
            self.assertNotEqual(owner.crypt_page.value, page)
            privacy.conceal()
            self.app.release_disposable_resources()
            privacy.reveal()
            with patch.object(owner, 'provider_page_content', side_effect=OSError('Source unavailable')):
                privacy.lock_password.value = 'session-password'
                await privacy.unlock()
                await owner._resume_page_task
            self.assertTrue(owner.page_suspended)
            self.assertFalse(owner.crypt_immersive)
            self.assertIn('Cannot read page', owner.crypt_title.text)
            self.assertIs(owner.crypt_view._native_reader_status, owner.crypt_title)
            await owner.read_crypt_page()
            self.assertFalse(owner.page_suspended)
            self.assertTrue(owner.crypt_content.children)
            self.assertTrue(self.app.private_sessions.close(owner.session.id))
            await asyncio.sleep(0)

        self.run_async(exercise())

    def test_nested_document_headers_show_filename_and_keep_source_path(self):
        self.copies.provider.session_only = True
        (self.local / 'nested').mkdir()
        with patch.object(self.app, 'show_view', wraps=self.app.show_view) as present:
            owner = self.open('nested/First.md', b'# First')
            self.assertEqual(present.call_args.kwargs['title'], 'First.md')
            self.assertEqual(owner.session.title, 'First.md')
            self.assertIn('First.md', owner.crypt_title.text)
            self.assertNotIn('nested/', owner.crypt_title.text)
            self.assertEqual(owner.crypt_reader.key, 'nested/First.md')
            self.assertEqual(owner.crypt_view._native_reader_title(), 'First.md')
            self.assertIn('Session-Only', owner.crypt_view._document_storage_status)
            self.app.private_sessions.activate(owner.session.id)
            self.assertEqual(present.call_args.kwargs['title'], 'First.md')

    def test_unified_recent_matches_local_source_and_keeps_live_unsaved_edits(self):
        from mobile.document_sources import reopen_file
        owner = self.open('live-draft.md', b'# Original')
        owner.crypt_text.value = '# Unsaved provider draft'
        source = owner.session.history_source
        session, summary = self.app.recent_items()[0]
        self.assertIs(session, owner.session)
        self.assertIn('Unsaved changes', summary[2])
        self.assertEqual(sum(item is session for item, _ in self.app.recent_items()), 1)
        with patch('mobile.document_sources.reopen_file', wraps=reopen_file) as reopen:
            self.run_async(self.app.recent_opener(session)())
            reopen.assert_not_called()
        self.assertIs(self.app.private_sessions.active, owner)
        self.assertEqual(owner.crypt_text.value, '# Unsaved provider draft')
        # Even a previously rendered live entry can reopen the original after close.
        action = self.app.recent_opener(session)
        self.assertTrue(self.app.private_sessions.close(session.id, discard=True))
        self.run_async(action())
        self.assertEqual(self.app.private_sessions.active.session.history_source, source)
        self.assertEqual(self.app.private_sessions.active.crypt_text.value, '# Original')

    def test_close_from_documents_immediately_refreshes_cards_and_list(self):
        def widgets(widget):
            yield widget
            content = getattr(widget, 'content', None)
            if content is not None and content not in getattr(widget, 'children', ()):
                yield from widgets(content)
            for child in getattr(widget, 'children', ()):
                yield from widgets(child)

        for cards in ('true', 'false'):
            with self.subTest(cards=cards):
                self.app.preferences.values['document_card_overview'] = cards
                owner = self.open('close-me.md')
                key = owner.session.id
                self.app.show_documents_hub()
                self.app.document_view_buttons['Open'].on_press()
                root = self.app.routes.roots['documents']
                close = next(widget for widget in widgets(root)
                             if getattr(widget, 'accessible_name', '') == 'Close close-me.md')
                close.on_press()
                self.assertNotIn(key, self.app.workspace.sessions)
                self.assertFalse(any(getattr(widget, 'accessible_name', '') == 'Close close-me.md'
                                     for widget in widgets(root)))

    def test_save_as_retains_source_privacy_until_exported_draft_closes(self):
        from services.session_auth import ResumePassword
        gate = ResumePassword('session-password')
        source = self.open('private-source.md')
        source.privacy_gate = gate
        source.crypt_text.value = 'Retained private draft'
        self.run_async(self.app.show_crypt_save_as(owner=source))
        self.assertIs(self.app.save_as_privacy_gate, gate)
        self.app.save_as_name.value = 'exported-private.md'
        self.run_async(self.app.save_text_destination())
        exported = self.app.private_sessions.active
        self.assertIsNot(exported, source)
        self.assertIs(exported.privacy_gate, gate)
        self.assertTrue(self.app.private_sessions.close(source.session.id, discard=True))
        self.assertTrue(self.app.screen_privacy.sensitive())
        self.assertTrue(self.app.private_sessions.close(exported.session.id, discard=True))
        self.assertFalse(self.app.screen_privacy.sensitive())

    def test_delayed_provider_open_keeps_the_newly_selected_view_and_draft(self):
        import asyncio
        from threading import Event
        prior = self.open('prior.md')
        prior.crypt_text.value = 'Retained prior provider draft'
        for destination in ('documents', 'settings'):
            with self.subTest(destination=destination):
                self.app.private_sessions.activate(prior.session.id)
                name = 'delayed-' + destination + '.md'
                (self.local / name).write_bytes(b'Loaded provider document')
                started, release = Event(), Event()
                original = self.copies.open
                def delayed(*args, **kwargs):
                    started.set()
                    if not release.wait(5):
                        raise RuntimeError('Provider fixture was not released')
                    return original(*args, **kwargs)
                async def exercise():
                    task = asyncio.create_task(self.app.open_crypt(copies=self.copies, key=name))
                    try:
                        for _ in range(100):
                            if started.is_set():
                                break
                            await asyncio.sleep(.01)
                        self.assertTrue(started.is_set())
                        if destination == 'documents':
                            self.app.show_documents(destination=destination)
                            self.app.editor.value = 'Ordinary draft written during opening'
                        else:
                            self.app.show_settings()
                        body, selected = self.app.body, self.app.workspace.active
                        release.set()
                        self.assertTrue(await task)
                        self.assertEqual(self.app.native_host.state.destination, destination)
                        self.assertIs(self.app.body, body)
                        self.assertEqual(self.app.workspace.active, selected)
                        self.assertEqual(prior.crypt_text.value, 'Retained prior provider draft')
                        loaded = next(owner for owner in self.app.private_sessions.controllers.values()
                                      if owner.session.title == name)
                        self.assertEqual(loaded.crypt_reader.text, 'Loaded provider document')
                        self.assertTrue(self.app.private_sessions.activate(loaded.session.id))
                        self.assertEqual(self.app.provider_sessions().active.crypt_text.value, 'Loaded provider document')
                        self.assertTrue(self.app.private_sessions.close(loaded.session.id))
                    finally:
                        release.set()
                        await task
                with patch.object(self.copies, 'open', side_effect=delayed):
                    self.run_async(exercise())
        self.assertEqual(self.app.editor.value, 'Ordinary draft written during opening')

    def test_delayed_open_survives_container_refresh_without_navigation(self):
        import asyncio
        from threading import Event
        import toga
        (self.local / 'refresh.md').write_bytes(b'Requested provider document')
        started, release = Event(), Event()
        original = self.copies.open
        def delayed(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Container fixture was not released')
            return original(*args, **kwargs)
        async def exercise():
            task = asyncio.create_task(self.app.open_crypt(copies=self.copies, key='refresh.md'))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(started.is_set())
                # UIKit may replace the body wrapper while retaining the same
                # destination, route and selected resource during containment.
                self.app.body = toga.Box()
                release.set()
                self.assertTrue(await task)
                self.assertIsNotNone(self.app.private_sessions.active)
                self.assertEqual(self.app.provider_sessions().active.crypt_text.value, 'Requested provider document')
                self.assertEqual(self.app.native_host.state.destination, 'files')
            finally:
                release.set()
                await task
        with patch.object(self.copies, 'open', side_effect=delayed):
            self.run_async(exercise())

    def test_private_names_never_enter_history_and_locked_sessions_are_hidden(self):
        from types import SimpleNamespace
        self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
        # Model the encrypted boundary before opening, when history eligibility is decided.
        self.copies.provider.private = True
        client = self.app.cloud_client
        generation = client.generation
        def check_access():
            if client.generation != generation:
                raise ValueError('Credentials locked')
        self.copies.provider.check = check_access
        owner = self.open('Sensitive-title.md', b'Sensitive body')
        owner.credential_client = self.app.cloud_client
        owner.credential_generation = self.app.cloud_client.generation
        # Model the encrypted provider boundary with a memory-only test reader.
        owner._crypt_reader_store.provider.private = True
        self.assertTrue(self.app.session_visible(owner.session))
        self.app.save_workspace()
        self.app.recent_documents.remember(owner.session)
        for path in (self.root / 'workspace.json', self.root / 'recent-documents.json'):
            if path.exists():
                raw = path.read_text()
                for secret in ('Sensitive-title', 'Sensitive body', owner.session.resource, 'provider-session'):
                    self.assertNotIn(secret, raw)
        self.app.cloud_client.generation += 1
        self.assertFalse(self.app.session_visible(owner.session))
        self.assertFalse(self.app.private_sessions.activate(owner.session.id))
        self.app.show_documents_hub()
        def texts(widget):
            children = list(getattr(widget, 'children', ()))
            content = getattr(widget, 'content', None)
            if content is not None and content not in children:
                children.append(content)
            return [getattr(widget, 'text', '')] + [text for child in children for text in texts(child)]
        self.assertFalse(any('Sensitive-title' in text for text in texts(self.app.build_documents_hub())))
        self.assertEqual(self.app.recent_documents.sessions(), [])
        # Even an incorrectly cleared transient flag cannot persist a private provider.
        owner.session.transient = False
        self.app.workspace.save()
        self.assertNotIn(owner.session.resource, self.app.workspace.path.read_text())
        owner.session.transient = True
        self.app.show_home()
        self.assertIsNone(getattr(self.app, 'home_continue', None))

    def test_two_private_drafts_duplicate_activation_and_inactive_save(self):
        a = self.open('A.md')
        a.crypt_text.value = 'A memory draft'
        b = self.open('B.md')
        b.crypt_text.value = 'B memory draft'
        self.assertTrue(self.run_async(self.app.open_crypt(copies=self.copies, key='A.md')))
        self.assertIs(self.app.private_sessions.active, a)
        self.assertEqual(self.app.provider_sessions().active.crypt_text.value, 'A memory draft')
        self.app.show_settings()
        self.run_async(self.app.show_files())
        self.assertEqual(a.crypt_text.value, 'A memory draft')
        self.assertEqual(b.crypt_text.value, 'B memory draft')
        self.app.private_sessions.activate(b.session.id)
        self.run_async(a.save_crypt())
        self.assertEqual((self.local / 'A.md').read_bytes(), b'A memory draft')
        self.assertEqual((self.local / 'B.md').read_bytes(), b'original')
        self.assertEqual(self.app.provider_sessions().active.crypt_text.value, 'B memory draft')
        self.app.save_workspace()
        raw = (self.root / 'workspace.json').read_text()
        for value in ['provider-session', 'A.md', 'B.md', 'memory draft']:
            self.assertNotIn(value, raw)
        self.assertEqual(len(self.app.private_sessions.controllers), 2)
        self.app.release_disposable_resources()
        self.assertEqual(a.crypt_text.value, 'A memory draft')
        self.assertEqual(b.crypt_text.value, 'B memory draft')

    def test_lock_checks_all_dirty_owners_before_clearing_any(self):
        a = self.open('A.txt')
        a.crypt_text.value = 'preserve me'
        b = self.open('B.txt')
        token = self.app.workspace.token(b.session.id)
        self.assertFalse(self.app.clear_private_reader())
        self.assertEqual(len(self.app.private_sessions.controllers), 2)
        self.assertEqual(a.crypt_text.value, 'preserve me')
        self.assertTrue(self.app.workspace.accepts(token))
        self.assertTrue(self.app.clear_private_reader(discard=True))
        self.assertFalse(self.app.workspace.accepts(token))
        self.assertEqual(a.crypt_text.value, '')
        self.assertEqual(b.crypt_text.value, '')
        self.assertIsNone((self.app.provider_sessions().active.crypt_reader if self.app.provider_sessions().active else None))
        a.resume_crypt()
        self.assertNotIn(a.session.id, self.app.workspace.sessions)

    def test_budget_and_save_conflict_preserve_existing_owner(self):
        a = self.open('A.txt')
        a.crypt_text.value = 'retained draft'
        (self.local / 'A.txt').write_bytes(b'external')
        self.run_async(a.save_crypt())
        self.assertIn('edits retained', a.crypt_title.text)
        self.assertEqual(a.crypt_text.value, 'retained draft')
        self.assertEqual((self.local / 'A.txt').read_bytes(), b'external')
        (self.local / 'B.txt').write_bytes(b'original')
        with patch('mobile.private_sessions.MAX_PRIVATE_BYTES', 1), \
                patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
            self.assertFalse(self.run_async(self.app.open_crypt(copies=self.copies, key='B.txt')))
        message = EventLog.performed_actions(dialog.call_args.args[0], 'create InfoDialog')[0]['message']
        self.assertIn('32 MiB', message)
        self.assertIn('Documents → Open documents', message)
        self.assertIn(a.session.id, self.app.private_sessions.controllers)
        self.assertEqual(a.crypt_text.value, 'retained draft')
        self.assertEqual(len(self.app.private_sessions.controllers), 1)

    def test_full_file_slots_show_visible_explanation_and_allow_retry_after_close(self):
        owners = [self.open(f'{index}.txt') for index in range(4)]
        owners[0].crypt_text.value = 'Keep this draft'
        (self.local / 'next.txt').write_text('Next')
        self.app.show_home()
        origin = self.app.body
        with patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog, \
                patch.object(self.copies, 'open', wraps=self.copies.open) as read:
            self.assertFalse(self.run_async(self.app.open_crypt(copies=self.copies, key='next.txt')))
            read.assert_not_called()
            dialog.assert_awaited_once()
            message = EventLog.performed_actions(dialog.call_args.args[0], 'create InfoDialog')[0]['message']
            self.assertIn('All 4', message)
            self.assertIn('Local, LocalCrypt and remote', message)
            self.assertIn('Documents → Open documents', message)
            self.assertIs(self.app.body, origin)
            self.assertIsNone(self.app._file_loading)
            # Resuming an existing document consumes no additional slot.
            self.assertTrue(self.run_async(self.app.open_crypt(copies=self.copies, key='0.txt')))
            self.assertEqual(owners[0].crypt_text.value, 'Keep this draft')
        self.assertTrue(self.app.private_sessions.close(owners[1].session.id))
        self.assertTrue(self.run_async(self.app.open_crypt(copies=self.copies, key='next.txt')))
        self.assertEqual(len(self.app.private_sessions.controllers), 4)

    def test_workspace_capacity_failure_is_visible_without_leaking_a_file_slot(self):
        owner = self.open('first.txt')
        (self.local / 'next.txt').write_text('Next')
        self.app.show_home()
        origin = self.app.body
        with patch('mobile.workspace.MAX_SESSIONS', 1), \
                patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
            self.assertFalse(self.run_async(self.app.open_crypt(copies=self.copies, key='next.txt')))
        self.assertIn('Close an open document', EventLog.performed_actions(dialog.call_args.args[0], 'create InfoDialog')[0]['message'])
        self.assertIs(self.app.body, origin)
        self.assertEqual(list(self.app.private_sessions.controllers), [owner.session.id])

    def test_provider_cancellation_and_busy_state_are_owned_by_the_document(self):
        from threading import Event
        owner = self.open('Local.md')
        transfer = Event()
        self.app.transfer_controller()._transfer_cancel = transfer
        owner._crypt_cancel = Event()
        owner.set_cloud_busy(True)
        self.assertTrue(owner.cloud_busy)
        self.assertFalse(self.app.cloud_busy)
        self.assertFalse(self.app.provider_sessions().close(owner.session.id))
        owner.cancel_cloud()
        self.assertTrue(owner._crypt_cancel.is_set())
        self.assertFalse(transfer.is_set())
        self.assertIs(self.app.transfer_controller()._transfer_cancel, transfer)
        self.assertFalse(hasattr(self.app, 'crypt_text'))
        self.assertFalse(hasattr(owner, 'undefined_host_service'))
        owner._crypt_cancel = None
        owner.set_cloud_busy(False)

    def test_rejected_or_failed_open_retires_only_the_new_owner(self):
        import asyncio
        from mobile.provider_opening import ProviderDocumentOpening
        prior = self.open('retained.txt')
        prior.crypt_text.value = 'Retained draft'
        manager = self.app.private_sessions
        original = ProviderDocumentOpening.open
        for outcome in ('rejected', 'exception', 'stale', 'cancelled'):
            with self.subTest(outcome=outcome):
                captured = []
                name = outcome + '.txt'
                (self.local / name).write_text('New document')

                async def opening(operation, **kwargs):
                    self.assertTrue(await original(operation, **kwargs))
                    owner = operation.owner
                    captured.append(owner)
                    self.assertIs(manager.active, owner)
                    if outcome == 'exception':
                        raise RuntimeError('Synthetic publication failure')
                    if outcome == 'cancelled':
                        raise asyncio.CancelledError
                    if outcome == 'stale':
                        self.app.workspace.invalidate(owner.session.id)
                        return True
                    return False

                with patch.object(ProviderDocumentOpening, 'open', opening):
                    if outcome == 'cancelled':
                        with self.assertRaises(asyncio.CancelledError):
                            self.run_async(self.app.open_crypt(copies=self.copies, key=name))
                    elif outcome == 'exception':
                        with self.assertRaisesRegex(RuntimeError, 'Synthetic publication failure'):
                            self.run_async(self.app.open_crypt(copies=self.copies, key=name))
                    else:
                        self.assertFalse(self.run_async(self.app.open_crypt(copies=self.copies, key=name)))
                self.assertEqual(list(manager.controllers), [prior.session.id])
                self.assertIs(manager.active, prior)
                self.assertEqual(prior.crypt_text.value, 'Retained draft')
                retired = captured[0]
                self.assertNotIn(retired.session.id, self.app.workspace.sessions)
                self.assertIsNone(retired.crypt_reader)
                self.assertIsNone(retired._opening_origin)
                self.assertIsNone(retired._opening_token)
                self.assertFalse(retired._independent_operation)

    def test_cancelled_remote_open_retires_transient_session_after_worker_finishes(self):
        import asyncio
        from threading import Event
        from types import SimpleNamespace
        from unittest.mock import Mock

        prior = self.open('retained.txt')
        prior.crypt_text.value = 'Retained draft'
        manager = self.app.private_sessions
        # Exercise remote admission/busy policy with a blocking fake, never a remote endpoint.
        self.copies.remote_storage = True
        reader = SimpleNamespace(source=SimpleNamespace(close=Mock()), password='synthetic-password')
        release = Event()

        async def exercise():
            started = asyncio.Event()

            def opening(*args, **kwargs):
                self.app.loop.call_soon_threadsafe(started.set)
                if not release.wait(5):
                    raise RuntimeError('Provider fixture was not released')
                return reader

            with patch.object(self.copies, 'open', side_effect=opening):
                task = asyncio.create_task(self.app.open_crypt(copies=self.copies, key='cancelled.txt'))
                try:
                    await asyncio.wait_for(started.wait(), 2)
                    pending = next(owner for owner in manager.controllers.values() if owner is not prior)
                    self.assertTrue(self.app.remote_read_busy)
                    task.cancel()
                    await asyncio.sleep(0)
                    task.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(task.done())
                    self.assertTrue(pending.operation_busy)
                    self.assertIn(pending.session.id, self.app.workspace.sessions)
                    reader.source.close.assert_not_called()
                finally:
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

            self.assertEqual(list(manager.controllers), [prior.session.id])
            self.assertNotIn(pending.session.id, self.app.workspace.sessions)
            self.assertIs(manager.active, prior)
            self.assertEqual(prior.crypt_text.value, 'Retained draft')
            reader.source.close.assert_called_once_with()
            self.assertEqual(reader.password, '')
            self.assertIsNone(pending._opening_origin)
            self.assertIsNone(pending._opening_token)
            self.assertFalse(pending.operation_busy)
            self.assertFalse(pending._independent_operation)
            self.assertFalse(self.app.remote_read_busy)
            self.assertFalse(self.app.cloud_busy)

        self.run_async(exercise())

    def test_replacement_veto_retains_dirty_text_metadata_and_source(self):
        from mobile.application_lifecycle import lifecycle
        from mobile.app import _active_hosts
        from types import SimpleNamespace as NS
        owner = self.open('draft.txt')
        manager, reader = self.app.private_sessions, owner.crypt_reader
        token = self.app.workspace.token(owner.session.id)
        identity = str(self.root.resolve()) + ':primary'
        for metadata in (False, True):
            with self.subTest(metadata=metadata):
                owner.crypt_text.value = reader.text if metadata else 'Synthetic retained draft'
                owner.crypt_metadata_fields = {'title': NS(value='Edited')} if metadata else {}
                owner.crypt_metadata_initial = {'title': 'Original'} if metadata else {}
                with patch.object(self.app, 'save_workspace') as save, \
                        self.assertRaises(OSError):
                    lifecycle(self.app).retire_for_replacement()
                save.assert_not_called()
                self.assertTrue(self.app.active_host)
                self.assertIs(_active_hosts[identity], self.app)
                self.assertIs(owner.crypt_reader, reader)
                self.assertIs(manager.controllers[owner.session.id], owner)
                self.assertTrue(self.app.workspace.accepts(token))

    def native_editor(self, owner, flush):
        from types import SimpleNamespace as NS
        view = object()
        editor = NS(view=view, closed=False, bridge='synthetic-bridge', _revision=0)
        async def snapshot():
            await flush()
            editor._revision += 1
        editor.flush = snapshot
        workflow = NS(formatted=editor, content=NS(children=[view]), closed=False,
                      source=owner.crypt_text, pending=None, preparing_formatted=None,
                      source_changed=lambda *args, **kwargs: None)
        original = owner.__dict__.get('_provider_markdown')
        owner._provider_markdown = workflow
        self.addCleanup(setattr, owner, '_provider_markdown', original)
        return editor, workflow

    def test_replacement_native_flush_is_ephemeral_owner_evidence(self):
        owner = self.open('native.txt')
        manager = self.app.private_sessions
        editor, workflow = self.native_editor(owner, AsyncMock())
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.test'):
            with self.assertRaises(OSError):
                manager.require_replacement_safe()
            receipt = self.run_async(manager.prepare_replacement())
            manager.require_replacement_safe(receipt)
            editor._revision += 1
            with self.assertRaises(OSError):
                manager.require_replacement_safe(receipt)
            async def dirty():
                owner.crypt_text.value = 'Native queued draft'
                editor._revision += 1
            editor.flush = dirty
            with self.assertRaises(OSError):
                self.run_async(manager.prepare_replacement())
            self.assertEqual(owner.crypt_text.value, 'Native queued draft')
            self.assertFalse(workflow.closed)

    def test_replacement_native_flush_failure_and_changed_earlier_provider_veto(self):
        first, second = self.open('one.txt'), self.open('two.txt')
        manager = self.app.private_sessions
        editor, _ = self.native_editor(first, AsyncMock())
        _, second_workflow = self.native_editor(second, AsyncMock())
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_android.test'):
            for change in ('bridge', 'revision', 'busy', 'token'):
                with self.subTest(change=change):
                    async def changed():
                        second_workflow.formatted._revision += 1
                        if change == 'bridge':
                            editor.bridge += '-changed'
                        elif change == 'revision':
                            editor._revision += 1
                        elif change == 'busy':
                            first.operation_busy = True
                        else:
                            self.app.workspace.invalidate(first.session.id)
                    second_workflow.formatted.flush = changed
                    with self.assertRaises(OSError):
                        self.run_async(manager.prepare_replacement())
                    first.operation_busy = False
            editor.flush = AsyncMock(side_effect=ValueError('Synthetic flush failed'))
            with self.assertRaises(OSError):
                self.run_async(manager.prepare_replacement())
        self.assertTrue(self.app.active_host)

    def test_cancelled_text_save_drains_and_reconciles_committed_reader(self):
        import asyncio
        from threading import Event
        owner = self.open('late.txt')
        owner.crypt_text.value = 'Committed synthetic draft'
        document, original = owner.provider_document(), owner.crypt_reader
        save = self.copies.save
        release, finished = Event(), Event()
        async def exercise():
            started = asyncio.Event()
            results = []
            def blocking(*args, **kwargs):
                self.app.loop.call_soon_threadsafe(started.set)
                if not release.wait(5):
                    raise RuntimeError('Fixture not released')
                try:
                    result = save(*args, **dict(kwargs, cancelled=lambda: False))
                    results.append(result)
                    return result
                finally:
                    finished.set()
            with patch.object(self.copies, 'save', side_effect=blocking):
                task = asyncio.create_task(owner.save_crypt())
                try:
                    await asyncio.wait_for(started.wait(), 2)
                    task.cancel()
                    await asyncio.sleep(0)
                    task.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(task.done())
                    self.assertTrue(owner.operation_busy)
                    self.assertFalse(owner.operation_idle.is_set())
                    self.assertIsNotNone(owner._crypt_cancel)
                    with self.assertRaises(OSError):
                        document.dispose()
                    self.assertIs(owner.crypt_reader, original)
                finally:
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    self.assertTrue(await asyncio.to_thread(finished.wait, 2))
            self.assertIs(owner.crypt_reader, results[0])
            self.assertFalse(owner.private_dirty())
            self.assertFalse(owner.operation_busy)
            self.assertTrue(owner.operation_idle.is_set())
            self.assertIsNone(owner._crypt_cancel)
        self.run_async(exercise())
        self.assertEqual((self.local / 'late.txt').read_text(), 'Committed synthetic draft')

    def test_terminal_retirement_closes_source_despite_presentation_failure_and_retries(self):
        from unittest.mock import Mock
        from types import SimpleNamespace as NS
        owner = self.open('terminal.txt')
        manager, document, reader = self.app.private_sessions, owner.provider_document(), owner.crypt_reader
        reader.source = NS(close=Mock())
        reader.pdf = NS(close=Mock())
        owner.pdf_search = NS(dispose=Mock(side_effect=[ValueError('synthetic'), None]))
        with patch.object(self.app, 'save_workspace') as save, \
                patch.object(self.app.workspace, 'close') as close, \
                patch.object(self.app.credential_document_lists, 'closed') as history:
            with self.assertRaises(OSError):
                manager.retire()
            self.assertFalse(manager.available(owner.session.id))
            self.assertTrue(document.terminal)
            reader.source.close.assert_called_once_with()
            reader.pdf.close.assert_called_once_with()
            manager.retire()
            reader.source.close.assert_called_once_with()
            reader.pdf.close.assert_called_once_with()
            save.assert_not_called()
            close.assert_not_called()
            history.assert_not_called()
        with self.assertRaises(OSError):
            document.reader = reader

    def test_credential_revocation_defers_source_close_until_borrow_retires(self):
        import asyncio
        from threading import Event
        from unittest.mock import Mock
        owner = self.open('revoked.txt')
        owner.crypt_text.value = 'Submitted'
        original = owner.crypt_reader
        original.source.close = Mock(wraps=original.source.close)
        manager = self.app.private_sessions
        revoked = [False]
        def access():
            if revoked[0]:
                raise ValueError('Synthetic grant revoked')
        owner.document_access = access
        release, finished = Event(), Event()
        async def exercise():
            started = asyncio.Event()
            def save(*args, **kwargs):
                self.app.loop.call_soon_threadsafe(started.set)
                try:
                    if not release.wait(5):
                        raise RuntimeError('Fixture not released')
                    raise ValueError('Synthetic save failed')
                finally:
                    finished.set()
            with patch.object(self.copies, 'save', side_effect=save):
                task = asyncio.create_task(owner.save_crypt())
                try:
                    await asyncio.wait_for(started.wait(), 2)
                    revoked[0] = True
                    manager.revoke_stale()
                    original.source.close.assert_not_called()
                    self.assertTrue(owner.operation_busy)
                    self.assertTrue(owner._crypt_cancel.is_set())
                    self.assertEqual(len(owner.crypt_view.children), 1)
                    self.assertIn('locked', owner.crypt_view.children[0].text)
                    task.cancel()
                    await asyncio.sleep(0)
                    task.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(task.done())
                finally:
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    self.assertTrue(await asyncio.to_thread(finished.wait, 2))
            self.assertNotIn(owner.session.id, manager.controllers)
            self.assertIsNone(owner.crypt_reader)
            original.source.close.assert_called_once_with()
        self.run_async(exercise())

    def test_receipt_rejects_owner_reader_editor_and_membership_changes(self):
        from types import SimpleNamespace as NS
        first, second = self.open('receipt-one.txt'), self.open('receipt-two.txt')
        manager = self.app.private_sessions
        editor, workflow = self.native_editor(first, AsyncMock())
        second_editor, _ = self.native_editor(second, AsyncMock())
        original_reader = first.crypt_reader
        for changed in ('reader', 'source', 'workflow', 'editor', 'session', 'manager', 'member'):
            with self.subTest(changed=changed), patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.test'):
                receipt = self.run_async(manager.prepare_replacement())
                if changed == 'reader':
                    from copy import copy
                    target, name, value = first.provider_document(), '_reader', copy(original_reader)
                elif changed == 'source':
                    target, name, value = original_reader, 'source', object()
                elif changed == 'workflow':
                    target, name, value = first, '_provider_markdown', NS(**vars(workflow))
                elif changed == 'editor':
                    target, name, value = workflow, 'formatted', NS(**vars(editor))
                elif changed == 'session':
                    target, name, value = first, 'session', NS(**vars(first.session))
                elif changed == 'manager':
                    target, name, value = first, 'manager', object()
                else:
                    target, name, value = manager, 'controllers', {first.session.id: first}
                previous = getattr(target, name)
                setattr(target, name, value)
                try:
                    with self.assertRaises(OSError):
                        manager.require_replacement_safe(receipt)
                finally:
                    setattr(target, name, previous)
                manager.require_replacement_safe(receipt)
        self.assertGreater(second_editor._revision, 0)

    def test_provider_receipt_rechecked_after_preservation_callbacks_and_veto_keeps_host(self):
        from mobile.application_lifecycle import lifecycle
        from mobile.app import _active_hosts
        owner = self.open('preserved.txt')
        manager = self.app.private_sessions
        _, _ = self.native_editor(owner, AsyncMock())
        token = self.app.workspace.token(owner.session.id)
        identity = str(self.root.resolve()) + ':primary'
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.test'):
            receipt = self.run_async(manager.prepare_replacement())
            with patch.object(self.app.store, 'flush_checkpoints', side_effect=lambda: setattr(owner.crypt_text, 'value', 'Reentrant draft')):
                with self.assertRaises(OSError):
                    lifecycle(self.app).retire_for_replacement(receipt)
        self.assertIs(_active_hosts[identity], self.app)
        self.assertTrue(self.app.active_host)
        self.assertTrue(self.app.workspace.accepts(token))
        self.assertEqual(owner.crypt_text.value, 'Reentrant draft')
        self.assertFalse(manager.terminal)

    def test_startup_veto_and_shell_abort_preserve_exact_private_owner(self):
        from mobile.application_lifecycle import lifecycle
        from mobile.app import _active_hosts
        from mobile.startup import StartupPhase
        owner = self.open('startup-draft.txt')
        owner.crypt_text.value = 'RAM only synthetic draft'
        reader, token = owner.crypt_reader, self.app.workspace.token(owner.session.id)
        class Shell:
            pass
        shell = Shell()
        shell.private_root, shell._async_startup = self.root, True
        shell.active_host = False
        with patch('mobile.startup.load_startup_models') as load:
            with self.assertRaises(OSError):
                self.run_async(LogisticsMobile._prepare_startup_phase(shell, StartupPhase.PREFERENCES))
            load.assert_not_called()
        lifecycle(shell).abort_startup()
        self.assertIs(_active_hosts[str(self.root.resolve()) + ':primary'], self.app)
        self.assertTrue(self.app.active_host)
        self.assertIs(owner.crypt_reader, reader)
        self.assertTrue(self.app.workspace.accepts(token))
        self.assertEqual(owner.crypt_text.value, 'RAM only synthetic draft')
        for path in self.root.rglob('*.json'):
            self.assertNotIn('RAM only synthetic draft', path.read_text())

    def test_terminal_failed_reader_close_retains_failed_handle_and_retries_only_it(self):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        for failing in ('pdf', 'source'):
            with self.subTest(failing=failing):
                owner = self.open('retry-' + failing + '.txt')
                document, reader = owner.provider_document(), owner.crypt_reader
                reader.pdf, reader.source = NS(close=Mock()), NS(close=Mock())
                getattr(reader, failing).close.side_effect = [OSError('Synthetic close failed'), None]
                # Retire this one document independently; do not terminalize the
                # fixture's whole manager before the next scenario.
                document.terminal = True
                with self.assertRaises(OSError):
                    document.dispose()
                self.assertIs(document.reader, reader)
                self.assertFalse(document.closed)
                self.assertEqual(len(document._reader_cleanup), 1)
                with self.assertRaises(OSError):
                    document.reader = reader
                document.dispose()
                document.dispose()
                self.assertTrue(document.closed)
                self.assertIsNone(document.reader)
                self.assertEqual(document._reader_cleanup, [])
                self.assertEqual(reader.pdf.close.call_count, 2 if failing == 'pdf' else 1)
                self.assertEqual(reader.source.close.call_count, 2 if failing == 'source' else 1)
                self.app.private_sessions.controllers.pop(owner.session.id)
                self.app.private_sessions.active = None

    def test_native_flush_must_act_on_a_live_editor_but_readonly_preview_needs_no_flush(self):
        owner = self.open('native-proof.txt')
        manager = self.app.private_sessions
        editor, workflow = self.native_editor(owner, AsyncMock())
        with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.test'):
            editor.flush = AsyncMock()  # A returned await without a revision is no proof.
            with self.assertRaises(OSError):
                self.run_async(manager.prepare_replacement())
            editor.closed = True
            with self.assertRaises(OSError):
                self.run_async(manager.prepare_replacement())
            editor.closed = False
            owner.crypt_reader.read_only = True
            workflow.content.children.clear()
            editor.flush.reset_mock()
            receipt = self.run_async(manager.prepare_replacement())
            manager.require_replacement_safe(receipt)
            editor.flush.assert_not_awaited()

    def test_progress_borrow_vetoes_clear_before_any_owner_closes(self):
        from mobile.application_lifecycle import lifecycle
        first, second = self.open('clear-first.txt'), self.open('clear-second.txt')
        manager = self.app.private_sessions
        readers = [owner.crypt_reader for owner in (first, second)]
        tokens = [self.app.workspace.token(owner.session.id) for owner in (first, second)]
        progress = second._provider_progress
        state = progress.state
        position = state.load()
        progress.worker = object()  # Actual-borrow marker; completion is owner-controlled.
        try:
            self.assertFalse(self.app.clear_private_reader(discard=True))
            self.assertFalse(lifecycle(self.app).request_exit())
            self.assertTrue(self.app.active_host)
            self.assertEqual(list(manager.controllers.values()), [first, second])
            self.assertIs(progress.state, state)
            self.assertEqual(state.load(), position)
            for owner, reader, token in zip((first, second), readers, tokens):
                self.assertIs(owner.crypt_reader, reader)
                self.assertTrue(self.app.workspace.accepts(token))
        finally:
            progress.worker = None

    def test_each_presentation_cleanup_failure_cannot_skip_terminal_source_cleanup(self):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        for failing in ('footer', 'progress', 'search'):
            with self.subTest(failing=failing):
                owner = self.open('presentation-' + failing + '.txt')
                document, reader = owner.provider_document(), owner.crypt_reader
                reader.source.close()
                reader.source, reader.pdf = NS(close=Mock()), NS(close=Mock())
                failure = Mock(side_effect=[OSError('Synthetic presentation failure'), None])
                if failing == 'footer':
                    owner.crypt_view.page_footer = NS(dispose=failure)
                elif failing == 'progress':
                    owner._provider_progress.retire = failure
                else:
                    owner.pdf_search = NS(dispose=failure)
                document.terminal = True
                with self.assertRaises(OSError):
                    document.dispose()
                reader.source.close.assert_called_once_with()
                reader.pdf.close.assert_called_once_with()
                document.dispose()
                document.dispose()
                self.assertEqual(failure.call_count, 2)
                reader.source.close.assert_called_once_with()
                reader.pdf.close.assert_called_once_with()
                self.app.private_sessions.controllers.pop(owner.session.id)
                self.app.private_sessions.active = None
