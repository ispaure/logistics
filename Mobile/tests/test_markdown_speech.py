"""Rendered selection and speech lifetime across mobile Markdown routes."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import test_obsidian
from logisticsmobile.obsidian import open_vault


class Engine:
    ready, error, default_voice = True, '', 'Offline'
    voices = {'Offline': None}

    def __init__(self, loop):
        self.calls, self.closed = [], False

    def speak(self, *args):
        self.calls.append(args)

    def stop(self):
        pass

    def close(self):
        self.closed = True


class MarkdownSpeechTests(unittest.TestCase):
    setUp = test_obsidian.ObsidianTests.setUp
    tearDown = test_obsidian.ObsidianTests.tearDown
    run_async = test_obsidian.ObsidianTests.run_async

    def test_document_preview_and_provider_cleanup(self):
        from features.text_editor.resources import LocalTextCopies
        from commonUtils.runtime.local_files import LocalFiles
        self.app.show_documents()
        self.app.name.value = 'Draft.md'
        self.app.editor.value = '# Draft'
        self.app.show_preview()
        normal = self.app.editor_view.markdown_speech
        self.assertIn(normal.button, self.app.preview_box.children)

        async def exercise():
            with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                normal.show()
                panel = normal.panel
                await panel.ready_task
                (self.root / 'Private.md').write_text('# Private')
                await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.root)), key='Private.md')
                self.assertTrue(panel.closed)
                owner = self.app.private_sessions.active
                speech = owner.markdown_speech
                self.assertIn(speech.button, owner.crypt_content.children)
                speech.show()
                panel = speech.panel
                await panel.ready_task
                with patch.object(owner.crypt_preview, 'evaluate_javascript', AsyncMock(return_value=json.dumps('Private'))):
                    await panel.play()
                self.assertEqual(panel.engine.calls[0][0], 'Private')
                owner.clear_private_preview()
                self.assertTrue(panel.engine.closed)
                self.assertEqual(panel.session.ranges, [])
                self.assertNotIn(speech.button, owner.crypt_content.children)
        self.run_async(exercise())

    def test_vault_playback_pause_navigation_and_late_dom_result(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            speech = owner.speech
            with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                speech.show()
                panel = speech.panel
                await panel.ready_task
                with patch.object(owner.web, 'evaluate_javascript', AsyncMock(return_value=json.dumps('Home\nA readable note.'))):
                    await panel.play()
                self.assertEqual(panel.engine.calls[0][0], 'Home\nA readable note.')
                panel.pause()
                self.assertEqual(panel.session.state, 'paused')
                panel.pause()
                self.assertEqual(panel.session.state, 'speaking')
                await owner.open_note('Vault/Projects/Plan.MD')
                self.assertTrue(panel.closed and panel.engine.closed)
                self.assertEqual(panel.session.ranges, [])
                speech.show()
                panel = speech.panel
                await panel.ready_task
                pending = self.app.loop.create_future()
                with patch.object(owner.web, 'evaluate_javascript', AsyncMock(side_effect=lambda *a: None)) as evaluate:
                    async def delayed(*args):
                        return await pending
                    evaluate.side_effect = delayed
                    task = self.app.loop.create_task(panel.play())
                    await asyncio.sleep(0)
                    self.app.show_home()
                    pending.set_result(json.dumps('Secret late note'))
                    await task
                self.assertTrue(panel.engine.closed)
                self.assertEqual(panel.engine.calls, [])
                self.assertIsNone(speech.panel)
        self.run_async(exercise())
