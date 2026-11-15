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

    def test_generated_html_retires_only_the_previous_dom_with_the_same_video_key(self):
        (self.vault / 'Home.md').write_text(
            '![[old.mp4]]\n\n```dataviewjs\ndv.paragraph("Loading");\n```\n', encoding='utf-8')

        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            document = library.document
            original_preview = document.note_preview
            key = 'shared-video-key'

            def reuse_key(text, path, base, **options):
                html, videos = original_preview(text, path, base, **options)
                generated_key, target = next(iter(videos.items()))
                return html.replace(generated_key, key), {key: target}

            old_started, release_old, old_done = Event(), Event(), Event()
            old_cancelled = []

            def open_media(path, target, *, cancelled):
                if target == 'old.mp4':
                    old_started.set()
                    if not release_old.wait(5):
                        raise RuntimeError('Test did not release the old video')
                    old_cancelled.append(cancelled())
                    old_done.set()
                return 'http://127.0.0.1/' + target

            with patch.object(document, 'note_preview', side_effect=reuse_key), patch(
                    'features.notes_library.mobile.dataview.execute_views',
                    new=AsyncMock(return_value='# Updated\n\n![[new.mp4]]')), patch.object(
                    library.library, 'open_embedded_video', side_effect=open_media):
                self.assertTrue(await library.open_note('Vault/Home.md'))
                page = document._page
                base, old_marker = library.base, document._load_marker
                old_videos = page.videos
                audio = old_videos.audio
                old_pause = audio.players[old_videos][0]
                scripts = []

                def evaluate(script):
                    scripts.append(script)
                    result = self.app.loop.create_future()
                    result.set_result('logistics-note:' + old_marker if 'document.readyState' in script else None)
                    return result

                with patch.object(audio, 'request_play', return_value=True), patch.object(
                        audio, 'permitted', return_value=True), patch.object(
                        library.web, 'evaluate_javascript', side_effect=evaluate):
                    url = base + '?inline-video=' + key
                    library.follow_link(library.web, url)
                    old_task = old_videos.task
                    try:
                        self.assertTrue(await asyncio.to_thread(old_started.wait, 3))
                        library.page_loaded()
                        await page.views.task
                        new_marker = document._load_marker
                        replacement = page.videos
                        self.assertIs(document._page, page)
                        self.assertEqual(library.base, base)
                        self.assertNotEqual(new_marker, old_marker)
                        self.assertEqual(set(replacement.targets), {key})
                        self.assertNotIn(old_videos, audio.players)
                        self.assertIn(replacement, audio.players)
                        with self.assertRaises(asyncio.CancelledError):
                            await old_task
                        queued_pause = next(script for script in scripts if 'video.pause()' in script)
                        self.assertIn('logistics-note:' + old_marker, queued_pause)
                        self.assertNotIn('logistics-note:' + new_marker, queued_pause)
                        script_count = len(scripts)
                        old_pause()
                        self.assertEqual(len(scripts), script_count)
                        await document.verify_page_load(base, old_marker)
                        self.assertFalse(document._loaded)
                        library.follow_link(library.web, url)
                        self.assertTrue(await replacement.task)
                        self.assertIn('logistics-note:' + new_marker, scripts[-1])
                        self.assertIn('window.logisticsPlayVideo?.("' + key + '"', scripts[-1])
                        self.assertIn('/new.mp4"', scripts[-1])
                    finally:
                        release_old.set()
                        if old_started.is_set():
                            self.assertTrue(await asyncio.to_thread(old_done.wait, 3))
                self.assertEqual(old_cancelled, [True])
                self.assertTrue(all('/old.mp4"' not in script for script in scripts))
                library.dispose()

        self.run_async(exercise())
