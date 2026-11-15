"""Reader publication and document opening ownership."""

import asyncio
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.testing.stages import TestStage
from mobile.obsidian import open_vault
from mobile_build.tests.support import notes as fixtures

TEST_STAGE = TestStage.REGRESSION


class NotesOpeningLifecycleTests(unittest.TestCase):
    setUp = fixtures.set_up_vault
    run_async = fixtures.run_async

    def test_native_publication_rejection_keeps_draft_and_history(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            home = 'Vault/Home.md'
            self.assertTrue(await library.open_note(home))
            self.assertTrue(await library.open_editor())
            editor = library.embedded
            editor.changed('# Unsaved draft\n')

            response = AsyncMock(side_effect=['discard', None])
            with patch.object(self.app.main_window, 'dialog', new=response), patch(
                    'features.notes_library.mobile.library_opening.set_inline_html',
                    side_effect=ValueError('Native reader refused the preview')) as publish:
                self.assertFalse(await library.open_note('Vault/Projects/Plan.MD'))
            publish.assert_called_once()
            self.assertEqual(response.await_count, 2)
            self.assertEqual(library.path, home)
            self.assertEqual(library.history, [home])
            self.assertIs(library.embedded, editor)
            self.assertIs(library.article.children[0], editor.view)
            self.assertTrue(editor.dirty)
            self.assertEqual(editor.text, '# Unsaved draft\n')
            self.assertFalse(library.page_loading.active)

        self.run_async(exercise())

    def test_stale_prepared_markdown_keeps_newer_opening_active(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            home = 'Vault/Home.md'
            stale = 'Vault/Projects/Plan.MD'
            newer = 'Vault/Replacement.md'
            (self.root / newer).write_text('# Replacement\n', encoding='utf-8')
            self.assertTrue(await library.open_note(home))

            gates = {path: (Event(), Event()) for path in (stale, newer)}
            original_preview = library.document.note_preview

            def hold_preview(text, path, base, **options):
                preview = original_preview(text, path, base, **options)
                ready, release = gates[path]
                ready.set()
                if not release.wait(5):
                    raise RuntimeError('Test did not release the prepared preview')
                return preview

            pending = []
            with patch.object(library.document, 'note_preview', side_effect=hold_preview):
                try:
                    pending.append(asyncio.create_task(library.open_note(stale)))
                    self.assertTrue(await asyncio.to_thread(gates[stale][0].wait, 3))
                    pending.append(asyncio.create_task(library.open_note(newer)))
                    self.assertTrue(await asyncio.to_thread(gates[newer][0].wait, 3))

                    gates[stale][1].set()
                    self.assertFalse(await pending[0])
                    self.assertEqual(library.path, home)
                    self.assertEqual(library.history, [home])
                    self.assertTrue(library.page_loading.active)
                    self.assertEqual(library.page_loading.filename.text, 'Replacement.md')
                finally:
                    for _, release in gates.values():
                        release.set()
                    await asyncio.gather(*pending)

            self.assertTrue(pending[1].result())
            self.assertEqual(library.path, newer)
            self.assertEqual(library.history, [home, newer])
            self.assertIs(library.article.children[0], library.web)
            self.assertFalse(library.page_loading.active)

        self.run_async(exercise())
