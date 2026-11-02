"""Mobile drawer navigation and local connection indexing contracts."""
import asyncio
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from commonUtils.testing.stages import TestStage
from commonUtils.runtime.operations import OperationCancelled
from features.text_editor.notes import NotesLibrary, vault_root
from features.text_editor.notes_links import connections
from mobile.obsidian import open_vault
import mobile_build.tests.documents.test_obsidian as fixtures

TEST_STAGE = TestStage.REGRESSION


class NotesDrawerTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async

    def test_links_resolve_aliases_references_and_ignore_code_images_and_hidden_notes(self):
        (self.vault / 'Home.md').write_text('[[Projects/Plan.MD|Plan]] [Plan][p]\n\n[p]: Projects/Plan.MD\n'
            '\n`[[Ignored]]`\n\n```\n[[Ignored]]\n```\n\n![[Missing.png]] [[Missing]]')
        (self.vault / 'Projects/Plan.MD').write_text('[[Home]] [Root](../Home.md#heading)')
        result = connections(NotesLibrary(self.provider, 'Vault'), 'Vault/Home.md')
        self.assertEqual(result['incoming'], ['Vault/Projects/Plan.MD'])
        self.assertEqual(result['outgoing'], ['Vault/Projects/Plan.MD'])
        self.assertEqual(result['unresolved'], ['Missing'])
        self.assertGreater(result['words'], 0)
        with self.assertRaises(OperationCancelled):
            connections(NotesLibrary(self.provider, 'Vault'), 'Vault/Home.md', cancelled=lambda: True)

    def test_remote_wrappers_are_rejected_before_any_io(self):
        remote = SimpleNamespace(provider=self.provider, remote_storage=True)
        wrapped = SimpleNamespace(provider=remote)
        self.assertIsNone(vault_root(wrapped, 'Vault', self.provider.list('Vault')))
        with self.assertRaisesRegex(ValueError, 'local copy'):
            NotesLibrary(wrapped, 'Vault')
        self.assertIsNone(self.run_async(open_vault(self.app, wrapped, 'Vault')))

    def test_files_document_links_sequence_and_history_on_phone_and_tablet(self):
        async def exercise():
            for width in (320, 390, 900, 1366):
                owner = await open_vault(self.app, self.provider, 'Vault', 'files')
                owner.reflow(width)
                self.assertIsNone(owner.sidebar.side)
                owner.open_card.on_press()
                self.assertEqual(owner.sidebar.side, 'files')
                self.assertEqual(list(owner.sidebar.view.children), [owner.article])
                self.assertTrue(self.app.routes.system_back())
                self.assertIsNone(owner.sidebar.side)
                self.assertTrue(owner.valid())
                await owner.open_note('Vault/Projects/Plan.MD')
                await owner.show_links()
                self.assertEqual(owner.sidebar.side, 'links')
                self.assertIn('Backlinks (1)', [getattr(w, 'text', '') for w in owner.link_rows.children])
                self.assertIs(owner.back_action().__self__, owner.sidebar)
                self.assertTrue(self.app.routes.system_back())
                self.assertIsNone(owner.sidebar.side)
                owner.follow_link(owner.web, owner.base + '?drawer=files')
                self.assertEqual(owner.sidebar.side, 'files')
                owner.dispose()
                self.assertIsNone(owner.sidebar.overlay)
        self.run_async(exercise())

    def test_closed_library_cannot_publish_delayed_connections(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            entered, release = Event(), Event()
            def delayed(*args, **kwargs):
                entered.set()
                release.wait(5)
                return dict(incoming=['private.md'], outgoing=[], unresolved=[], words=1, characters=1)
            with patch('features.text_editor.notes_links.connections', side_effect=delayed):
                task = asyncio.create_task(owner.show_links())
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(entered.is_set())
                    owner.dispose()
                finally:
                    release.set()
                    await task
                self.assertEqual(list(owner.link_rows.children), [])
                self.assertIsNone(owner.sidebar.overlay)
        self.run_async(exercise())
