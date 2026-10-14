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

    def test_two_private_drafts_duplicate_activation_and_inactive_save(self):
        a = self.open('A.md')
        a.crypt_text.value = 'A memory draft'
        b = self.open('B.md')
        b.crypt_text.value = 'B memory draft'
        self.assertTrue(self.run_async(self.app.open_crypt(copies=self.copies, key='A.md')))
        self.assertIs(self.app.private_sessions.active, a)
        self.assertEqual(self.app.crypt_text.value, 'A memory draft')
        self.app.show_settings()
        self.run_async(self.app.show_files())
        self.assertEqual(a.crypt_text.value, 'A memory draft')
        self.assertEqual(b.crypt_text.value, 'B memory draft')
        self.app.private_sessions.activate(b.session.id)
        self.run_async(a.save_crypt())
        self.assertEqual((self.local / 'A.md').read_bytes(), b'A memory draft')
        self.assertEqual((self.local / 'B.md').read_bytes(), b'original')
        self.assertEqual(self.app.crypt_text.value, 'B memory draft')
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
        self.assertIsNone(self.app.crypt_reader)
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
