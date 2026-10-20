"""Native Markdown search scope, WebView lifecycle and host command integration."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from logisticsmobile.app import LogisticsMobile
from commonUtils.ui.native.markdown import MarkdownWikiView
from commonUtils.ui.native.markdown_search import search_script


class MarkdownSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.temporary.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.root = Path(self.temporary.name).resolve() / 'wiki'
        self.root.mkdir()
        (self.root / 'index.md').write_text('# Home\n\nA needle.')
        self.owner = MarkdownWikiView(self.root)

    def tearDown(self):
        self.owner.page_search.dispose()
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def test_scopes_controls_and_literal_query(self):
        async def exercise():
            owner, search = self.owner, self.owner.page_search
            self.assertNotIn(owner.mode, owner.browse.children)
            self.assertNotIn(owner.notice, owner.browse.children)
            owner.search.value = 'needle'
            owner.filter()
            self.assertIn(owner.mode, owner.browse.children)
            self.assertEqual(search.library_query, 'needle')
            owner.show_browse()
            owner.page_search.button.on_press()
            self.assertTrue(owner.reading and search.visible)
            search.query.value = '😀 [literal].*'
            search.ready = True
            with patch.object(owner.web, 'evaluate_javascript', AsyncMock(return_value=json.dumps(
                    dict(count=2, index=0, limited=False)))) as evaluate:
                await search.update(reveal=True)
                self.assertEqual(search.notice.text, 'This page · 1 of 2')
                self.assertIn('"library": "needle"', evaluate.call_args.args[0])
                self.assertIn('"page": "\\ud83d\\ude00 [literal].*"', evaluate.call_args.args[0])
                search.hide()
                await search.update()
                self.assertIn('"page": ""', evaluate.call_args.args[0])
                self.assertIn('"library": "needle"', evaluate.call_args.args[0])
            owner.search.value = ''
            owner.filter()
            self.assertNotIn(owner.mode, owner.browse.children)
            self.assertEqual(search.library_query, '')
            search.dispose()
            self.assertEqual(search.query.value, '')
            self.assertFalse(search.visible)
        self.app.loop.run_until_complete(exercise())

    def test_late_result_cannot_change_new_document_status(self):
        async def exercise():
            search = self.owner.page_search
            search.show()
            search.query.value = 'needle'
            search.ready = True
            result = self.app.loop.create_future()
            async def evaluate(script):
                return await result
            with patch.object(search.web, 'evaluate_javascript', evaluate):
                task = self.app.loop.create_task(search.update())
                await asyncio.sleep(0)
                search.loading()
                result.set_result(json.dumps(dict(count=3, index=0, limited=False)))
                await task
            self.assertEqual(search.notice.text, 'This page · loading…')
            self.assertFalse(search.next_button.enabled)
        self.app.loop.run_until_complete(exercise())

    def test_fragment_navigation_takes_priority_and_host_preview_keeps_font_binding(self):
        with patch.object(self.owner.page_search, 'loaded') as loaded:
            self.owner.pending_fragment = 'home'
            self.owner.page_loaded()
            loaded.assert_called_once_with(reveal=False)
        self.app.create_chosen_document('md')
        self.app.editor_view.editor.value = '# Preview\n\nNeedle.'
        self.app.show_preview()
        owner = self.app.editor_view
        self.assertIs(owner.preview._font_binding._load_handler, owner.preview.on_webview_load)
        self.assertTrue(any(title == 'Find in this page…' for title, action in owner.preview_actions.actions))
        owner.preview_search.show()
        self.assertIn(owner.preview_search.box, owner.preview_box.children)
        owner.preview_search.dispose()

    def test_provider_preview_search_is_cleared_on_close(self):
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        async def exercise():
            await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.root)), key='index.md')
            owner = self.app.private_sessions.active
            search = owner.crypt_preview_search
            self.assertIsNotNone(search)
            self.assertTrue(any(title == 'Find in this page…' for title, action in owner.crypt_actions_menu.actions))
            self.assertIs(owner.crypt_preview._font_binding._load_handler, owner.crypt_preview.on_webview_load)
            search.show()
            search.query.value = 'private query'
            self.assertTrue(search.visible)
            owner.clear_private_preview()
            self.assertTrue(search.closed)
            self.assertEqual(search.query.value, '')
            self.assertFalse(search.visible)
            self.assertIsNone(owner.crypt_preview_search)
        self.app.loop.run_until_complete(exercise())

    def test_queued_work_cannot_act_on_a_replacement_document(self):
        async def exercise():
            search = self.owner.page_search
            search.ready = True
            with patch.object(search.web, 'evaluate_javascript', AsyncMock()) as evaluate:
                task = search.request(step=1, reveal=True)
                search.loading()
                search.ready = True
                await task
                evaluate.assert_not_called()
        self.app.loop.run_until_complete(exercise())

    def test_queries_are_serialized_as_data(self):
        script = search_script('"; alert(1); //', "needle\n😀", step=-1)
        self.assertIn('"page": "\\\"; alert(1); //"', script)
        self.assertIn('"step": -1', script)
