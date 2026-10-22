"""Independent memory-only owners, bounded resources and atomic lock guards."""
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
        self.addCleanup(self.app.loop.close)
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
        from features.rclone.mobile.session_privacy import ResumePassword
        fixture = json.loads((Path(__file__).parents[1] / 'native_tests/tests/logisticsmobile/comic_fixture.json').read_text())
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
        (self.local / 'nested').mkdir()
        with patch.object(self.app, 'show_view', wraps=self.app.show_view) as present:
            owner = self.open('nested/First.md', b'# First')
            self.assertEqual(present.call_args.kwargs['title'], 'First.md')
            self.assertEqual(owner.session.title, 'First.md')
            self.assertIn('First.md', owner.crypt_title.text)
            self.assertNotIn('nested/', owner.crypt_title.text)
            self.assertEqual(owner.crypt_reader.key, 'nested/First.md')
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
                root = self.app.routes.roots['documents']
                close = next(widget for widget in widgets(root)
                             if getattr(widget, 'accessible_name', '') == 'Close close-me.md')
                close.on_press()
                self.assertNotIn(key, self.app.workspace.sessions)
                self.assertFalse(any(getattr(widget, 'accessible_name', '') == 'Close close-me.md'
                                     for widget in widgets(root)))

    def test_save_as_retains_source_privacy_until_exported_draft_closes(self):
        from features.rclone.mobile.session_privacy import ResumePassword
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
        self.copies.encrypted = True
        owner = self.open('Sensitive-title.md', b'Sensitive body')
        owner.credential_client = self.app.cloud_client
        owner.credential_generation = self.app.cloud_client.generation
        # Model the encrypted provider boundary with a memory-only test reader.
        owner._crypt_reader_store.encrypted = True
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
            return [getattr(widget, 'text', '')] + [text for child in getattr(widget, 'children', ()) for text in texts(child)]
        self.assertFalse(any('Sensitive-title' in text for text in texts(self.app.build_documents_hub().content)))
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
