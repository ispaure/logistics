"""Rendered selection and speech lifetime across mobile Markdown routes."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import mobile_build.tests.documents.test_obsidian as test_obsidian
from mobile.obsidian import open_vault


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

    def test_source_failure_is_visible_and_word_highlights_are_cleared(self):
        import toga
        from mobile.markdown_speech import MarkdownSpeech, SOURCE_SCRIPT

        async def exercise():
            web = toga.WebView()
            speech = MarkdownSpeech(self.app, web, toga.Box())
            with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                speech.show()
                panel = speech.panel
                await panel.ready_task
                with patch.object(web, 'evaluate_javascript', side_effect=RuntimeError('DOM unavailable')):
                    await panel.play()
                self.assertEqual(panel.session.state, 'stopped')
                self.assertIn('Could not read this passage', panel.status.text)
                self.assertFalse(panel.engine.calls)

                pending = self.app.loop.create_future()
                async def delayed_source():
                    return await pending
                with patch.object(panel, 'source', delayed_source):
                    task = self.app.loop.create_task(panel.play())
                    await asyncio.sleep(0)
                    panel.session.stop()
                    from types import SimpleNamespace
                    pending.set_result((SimpleNamespace(text='Canceled text'), 0, None))
                    await task
                self.assertEqual(panel.session.state, 'stopped')
                self.assertFalse(panel.engine.calls)

                def evaluate(script):
                    result = self.app.loop.create_future()
                    result.set_result(json.dumps('😀 One two.') if script == SOURCE_SCRIPT else None)
                    return result

                with patch.object(web, 'evaluate_javascript', side_effect=evaluate) as run:
                    await panel.play()
                    token = panel.session.token
                    panel.engine.progress(token, 3, 6)
                    self.assertIn('})(3,6)', run.call_args.args[0])
                    panel.session.pause()
                    count = run.call_count
                    panel.engine.progress(token, 7, 10)
                    self.assertEqual(run.call_count, count)
                    panel.session.stop()
                    self.assertIn('})(-1,-1)', run.call_args.args[0])
                    speech.close()
                    self.assertEqual(run.call_args.args[0], 'delete window.logisticsSpeech')
        self.run_async(exercise())

    def javascript_result(self, text):
        # Toga evaluates immediately and returns an awaitable result, rather
        # than a coroutine that must be awaited to start execution.
        result = self.app.loop.create_future()
        result.set_result(json.dumps(text))
        return result

    def test_document_preview_and_provider_cleanup(self):
        from features.text_editor.resources import LocalTextCopies
        from commonUtils.runtime.resources.local import LocalFiles
        self.app.show_documents()
        self.app.name.value = 'Draft.md'
        self.app.editor.value = '# Draft'
        self.app.show_preview()
        normal = self.app.editor_view.markdown_speech
        self.assertEqual(normal.document_title(), 'Draft.md')
        self.assertIn(normal.button.parent, self.app.preview_box.children)
        self.assertEqual(normal.button.control_icon, 'speaker')

        async def exercise():
            with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                normal.button.on_press()
                panel = normal.panel
                await panel.ready_task
                (self.root / 'Private.md').write_text('# Private')
                await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.root)), key='Private.md')
                self.assertTrue(panel.closed)
                owner = self.app.private_sessions.active
                self.assertNotIn(owner.crypt_edit_mode, owner.crypt_markdown_footer.children)
                owner.toggle_private_preview()
                self.assertNotIn(owner.crypt_edit_mode, owner.crypt_markdown_footer.children)
                self.assertIn('Source editing', dict(owner._provider_markdown.actions_menu.actions))
                owner.toggle_private_preview()
                self.assertNotIn(owner.crypt_edit_mode, owner.crypt_markdown_footer.children)
                speech = owner.markdown_speech
                self.assertEqual(speech.document_title(), '')
                self.assertIn(speech.button, owner.reader_toolbar.children)
                speech.button.on_press()
                panel = speech.panel
                await panel.ready_task
                with patch.object(owner.crypt_preview, 'evaluate_javascript', return_value=self.javascript_result('Private')):
                    await panel.play()
                self.assertEqual(panel.engine.calls[0][0], 'Private')
                owner.clear_private_preview()
                self.assertTrue(panel.engine.closed)
                self.assertEqual(panel.session.ranges, [])
                self.assertNotIn(speech.button, owner.reader_toolbar.children)
        self.run_async(exercise())

    def test_vault_playback_pause_navigation_and_late_dom_result(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            speech = owner.speech
            with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                self.assertNotIn(speech.button, owner.toolbar.children)
                dict(owner.reader_actions.actions)['Read aloud…']()
                panel = speech.panel
                await panel.ready_task
                with patch.object(owner.web, 'evaluate_javascript', return_value=self.javascript_result('Home\nA readable note.')):
                    await panel.play()
                self.assertEqual(panel.engine.calls[0][0], 'Home\nA readable note.')
                self.assertEqual(panel.play_button.control_icon, 'pause')
                controls = panel.play_button.parent.children
                self.assertEqual(sum(getattr(button, 'control_icon', '') in ('play', 'pause') for button in controls), 1)
                await panel.toggle_playback()
                self.assertEqual(panel.session.state, 'paused')
                self.assertEqual(panel.play_button.control_icon, 'play')
                await panel.toggle_playback()
                self.assertEqual(panel.session.state, 'speaking')
                self.assertEqual(panel.play_button.control_icon, 'pause')
                self.assertEqual(panel.engine.calls[-1][0], 'Home\nA readable note.')
                panel.session.stop()
                self.assertEqual(panel.play_button.control_icon, 'play')
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
