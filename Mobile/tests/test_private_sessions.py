"""Independent memory-only owners, bounded resources and atomic lock guards."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.runtime.local_files import LocalFiles
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.file_resources import LocalTextCopies


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
                            self.app.show_documents()
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
                self.assertEqual(self.app.native_host.state.destination, 'documents')
            finally:
                release.set()
                await task
        with patch.object(self.copies, 'open', side_effect=delayed):
            self.run_async(exercise())

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
        with patch('logisticsmobile.private_sessions.MAX_PRIVATE_BYTES', 1):
            self.assertFalse(self.run_async(self.app.open_crypt(copies=self.copies, key='B.txt')))
        self.assertIn(a.session.id, self.app.private_sessions.controllers)
        self.assertEqual(a.crypt_text.value, 'retained draft')
        self.assertEqual(len(self.app.private_sessions.controllers), 1)

    def test_provider_cancellation_and_busy_state_are_owned_by_the_document(self):
        from threading import Event
        owner = self.open('Local.md')
        transfer = Event()
        self.app._crypt_cancel = transfer
        owner._crypt_cancel = Event()
        owner.set_cloud_busy(True)
        self.assertTrue(owner.cloud_busy)
        self.assertFalse(self.app.cloud_busy)
        self.assertFalse(self.app.provider_sessions().close(owner.session.id))
        owner.cancel_cloud()
        self.assertTrue(owner._crypt_cancel.is_set())
        self.assertFalse(transfer.is_set())
        self.assertIs(self.app._crypt_cancel, transfer)
        self.assertFalse(hasattr(self.app, 'crypt_text'))
        self.assertFalse(hasattr(owner, 'undefined_host_service'))
        owner._crypt_cancel = None
        owner.set_cloud_busy(False)
