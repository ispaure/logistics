"""Markdown defaults, block preservation and per-owner bridge lifetime."""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote
import unittest
from mobile.app import LogisticsMobile
from mobile.workspace import view_state
from features.text_editor.mobile.markdown_editor import editor_blocks, editor_html


class MarkdownEditorTests(unittest.TestCase):
    def test_native_close_flushes_pending_input_before_deciding_whether_to_prompt(self):
        from unittest.mock import AsyncMock, patch
        self.app.create_chosen_document('md')
        owner = self.app.editor_view
        async def final_input():
            owner.editor.value = '# Final composition\n'
        async def exercise():
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.widgets.webview'), \
                 patch.object(owner.formatted, 'flush', new=AsyncMock(side_effect=final_input)), \
                 patch.object(self.app, 'document_close_dialog', return_value=True) as dialog:
                self.assertTrue(self.app.request_close_session(owner.session.id))
                await owner._markdown_close_task
                dialog.assert_called_once()
                self.assertIn(owner.session.id, self.app.workspace.sessions)
                self.assertEqual(owner.document.text, '# Final composition\n')
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.widgets.webview'), \
                 patch.object(owner.formatted, 'flush', new=AsyncMock(side_effect=ValueError('Input unavailable'))), \
                 patch.object(self.app, 'document_close_dialog') as dialog:
                self.assertTrue(self.app.request_close_session(owner.session.id))
                await owner._markdown_close_task
                dialog.assert_not_called()
                self.assertIn(owner.session.id, self.app.workspace.sessions)
                self.assertIn('Input unavailable', owner.status.text)
        self.app.loop.run_until_complete(exercise())

    def test_save_flushes_the_final_dom_patch_and_rejects_replaced_pages(self):
        import json
        from unittest.mock import AsyncMock, patch
        from features.text_editor.mobile.markdown_editor import FormattedMarkdownInput
        updates = []
        editor = FormattedMarkdownInput(updates.append)
        editor.load('# Before\r\n\r\nUntouched\r\n')
        raw = json.dumps(dict(revision=1, changes=[[0, '# After 😀\r\n']]))
        async def exercise():
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.widgets.webview'), \
                 patch.object(editor.view, 'evaluate_javascript', new=AsyncMock(return_value=raw)):
                await editor.flush()
                self.assertEqual(updates, ['# After 😀\r\n\r\nUntouched\r\n'])
            async def replaced(script):
                editor.load('# Replacement')
                return raw
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.widgets.webview'), \
                 patch.object(editor.view, 'evaluate_javascript', side_effect=replaced):
                with self.assertRaises(ValueError):
                    await editor.flush()
            self.assertEqual(len(updates), 1)
        self.app.loop.run_until_complete(exercise())
        editor.dispose()

    def test_mode_commands_work_when_keyboard_tucks_the_secondary_row(self):
        from mobile.keyboard import _tuck_control
        self.app.create_chosen_document('md')
        owner = self.app.editor_view
        _tuck_control(owner.source_tools, True)
        self.assertIsNone(owner.source_tools.parent)
        actions = dict(owner.actions.actions)
        self.app.loop.run_until_complete(actions['Source editing']())
        self.assertEqual(owner.editor_area.children, [owner.editor])
        self.app.loop.run_until_complete(actions['Formatted editing']())
        self.assertEqual(owner.editor_area.children, [owner.formatted.view])
        _tuck_control(owner.source_tools, False)

    def test_ios_retirement_clears_live_document_before_replacement_navigation(self):
        from types import SimpleNamespace
        from features.text_editor.mobile.markdown_editor import retire_webview
        events = []
        native = SimpleNamespace(stopLoading=lambda: events.append('stop'),
            evaluateJavaScript=lambda script, **kwargs: events.append(('clear', script)),
            navigationDelegate=object(), UIDelegate=object())
        backend = type('IOSWebView', (), {'__module__': 'toga_iOS.widgets.webview'})()
        backend.native = native
        view = SimpleNamespace(_impl=backend,
            set_content=lambda url, content: events.append(('navigate', url, content)))
        retire_webview(view)
        self.assertEqual(events[0], 'stop')
        self.assertEqual(events[1][0], 'clear')
        self.assertIn('document.open()', events[1][1])
        self.assertIn('Document closed.', events[1][1])
        self.assertEqual(events[2][0], 'navigate')
        self.assertIsNone(native.navigationDelegate)
        self.assertIsNone(native.UIDelegate)

    def setUp(self):
        self.temporary = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.temporary.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        for owner in self.app.text_views.values():
            owner.dispose()
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def test_default_preview_explicit_edit_and_new_markdown(self):
        document = self.app.store.create('Read.md')
        self.app.open_document(document.id)
        self.app.show_documents(resume=True)
        self.assertEqual(self.app.editor_view.session.view['markdown_mode'], 'preview')
        self.assertIs(self.app.body.children[0], self.app.preview_box)
        next(child for child in self.app.editor_view.markdown_speech.button.parent.children
             if getattr(child, 'control_icon', '') == 'edit').on_press()
        self.assertEqual(self.app.editor_view.session.view['markdown_mode'], 'edit')
        self.assertIs(self.app.body.children[0], self.app.document_view)
        self.app.show_documents()  # Ordinary activation returns to reading.
        self.assertIs(self.app.body.children[0], self.app.preview_box)
        self.app.create_chosen_document('md')
        self.assertEqual(self.app.editor_view.session.view['markdown_mode'], 'edit')
        self.assertEqual(self.app.editor_view.editor_area.children, [self.app.editor_view.formatted.view])

    def test_save_only_appears_after_a_real_markdown_change(self):
        self.app.show_documents_hub()
        document = self.app.store.create('Read.md', b'# Original\n')
        self.app.open_document(document.id)
        self.app.show_documents(edit=True)
        owner = self.app.editor_view
        self.assertNotIn(owner.save_button, owner.toolbar.children)
        self.assertNotIn('Save', [label for label, _ in owner.actions.actions])
        self.assertEqual(owner.preview_button.control_icon, 'view')
        owner.editor.value = '# Changed\n'
        self.assertIn(owner.save_button, owner.toolbar.children)
        self.assertIn('Save', [label for label, _ in owner.actions.actions])
        owner.editor.value = '# Original\n'
        self.assertNotIn(owner.save_button, owner.toolbar.children)
        owner.editor.value = '# Changed\n'
        self.app.save_document()
        self.assertNotIn(owner.save_button, owner.toolbar.children)
        self.app.show_preview()
        self.assertIs(owner.preview_edit.parent, owner.preview_toolbar)
        self.assertIs(owner.preview_box._workspace_menu_button.parent, owner.preview_toolbar)

    def test_provider_preview_conversion_runs_in_worker(self):
        import threading
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        from mobile.preview import markdown_preview
        root = Path(self.temporary.name) / 'worker-preview'
        root.mkdir()
        (root / 'Note.md').write_text('# Private worker sentinel')
        run = self.app.loop.run_until_complete
        run(self.app.open_crypt(copies=LocalTextCopies(LocalFiles(root)), key='Note.md'))
        owner = self.app.private_sessions.active
        owner.toggle_private_preview()  # Edit.
        threads = []
        def render(*args, **kwargs):
            threads.append(threading.get_ident())
            return markdown_preview(*args, **kwargs)
        with patch('mobile.preview.markdown_preview', side_effect=render):
            owner.toggle_private_preview()
        self.assertTrue(threads)
        self.assertNotIn(threading.get_ident(), threads)
        owner.clear_private_preview()
        self.assertIsNone(owner._private_preview_token)

    def test_provider_markdown_uses_one_toolbar_and_no_clean_save(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        root = Path(self.temporary.name) / 'provider-compact'
        root.mkdir()
        (root / 'Note.md').write_text('# Note\n')
        run = self.app.loop.run_until_complete
        self.assertTrue(run(self.app.open_crypt(copies=LocalTextCopies(LocalFiles(root)), key='Note.md')))
        owner = self.app.private_sessions.active
        self.assertEqual(owner.crypt_preview_button.control_icon, 'edit')
        self.assertIs(owner.crypt_preview_button.parent, owner.reader_toolbar)
        self.assertNotIn(owner.crypt_save, owner.reader_toolbar.children)
        self.assertEqual(owner.crypt_markdown_footer.style.height, 0)
        owner.toggle_private_preview()
        self.assertEqual(owner.crypt_preview_button.control_icon, 'view')
        owner.crypt_text.value = '# Edited\n'
        self.assertIn(owner.crypt_save, owner.reader_toolbar.children)
        self.assertTrue(owner.crypt_save.enabled)
        run(owner.save_crypt())
        self.assertNotIn(owner.crypt_save, owner.reader_toolbar.children)
        self.assertEqual((root / 'Note.md').read_text(), '# Edited\n')

    def test_bridge_updates_only_its_owner_and_stops_after_close(self):
        self.app.create_chosen_document('md')
        owner = self.app.editor_view
        bridge = owner.formatted
        self.app.new_document()
        current = self.app.editor_view
        text = '# Draft 😀\n\n**Bold** & 100% + plus\n'
        self.assertFalse(bridge.navigate(None, bridge.bridge + '?text=' + quote(text, safe='')))
        self.assertEqual(owner.document.text, text)
        self.assertEqual(self.app.store.open(owner.document.id).text, text)
        self.assertEqual(current.document.text, '')
        bridge.navigate(None, 'https://external.invalid/?text=wrong')
        self.assertEqual(owner.document.text, text)
        owner.edit_mode.value = 'Source'
        self.assertEqual(owner.editor_area.children, [owner.editor])
        old_bridge = bridge.bridge
        bridge.navigate(None, old_bridge + '?text=stale-hidden-page')
        self.assertEqual(owner.document.text, text)
        owner.edit_mode.value = 'Formatted'
        bridge.navigate(None, old_bridge + '?text=stale-after-reload')
        self.assertEqual(owner.document.text, text)
        self.assertTrue(self.app.close_session(owner.session.id, choice='keep'))
        bridge.navigate(None, bridge.bridge + '?text=closed')
        self.assertEqual(owner.document.text, text)

    def test_changed_blocks_are_cumulative_ordered_and_retired(self):
        import json
        from features.text_editor.mobile.markdown_editor import FormattedMarkdownInput
        changes = []
        editor = FormattedMarkdownInput(changes.append)
        source = '# Original\r\n\r\n' + ('untouched 😀\n\n' * 1000)
        editor.load(source)
        def send(revision, updates):
            editor.navigate(None, editor.bridge + '?patch=' + quote(json.dumps(
                dict(revision=revision, changes=updates)), safe=''))
        send(2, [[0, '# Changed\r\n']])  # A coalesced earlier navigation is safe.
        self.assertEqual(changes[-1], '# Changed\r\n' + ''.join(editor._blocks[1:]))
        send(1, [[0, 'stale']])
        send(3, [[999999, 'invalid']])
        self.assertEqual(len(changes), 1)
        send(4, [])  # Undo restores the exact original source.
        self.assertEqual(changes[-1], source)
        editor.dispose()
        send(5, [[0, 'closed']])
        self.assertEqual(len(changes), 2)
        self.assertEqual(editor._blocks, ())

    def test_each_markdown_session_owns_its_preview(self):
        first = self.app.store.create('First.md', b'# First')
        self.app.open_document(first.id)
        self.app.show_documents()
        a = self.app.editor_view
        second = self.app.store.create('Second.md', b'# Second')
        self.app.open_document(second.id)
        self.app.show_documents()
        b = self.app.editor_view
        self.assertIsNot(a.preview, b.preview)
        self.assertIsNot(a.preview_box, b.preview_box)
        self.assertIs(self.app.adaptive.session_view(a.session.id), a.preview_box)
        self.assertIs(self.app.adaptive.session_view(b.session.id), b.preview_box)
        self.assertTrue(self.app.close_session(a.session.id))
        self.assertIs(self.app.editor_view, b)
        self.assertEqual(b.document.text, '# Second')

    def test_provider_markdown_displays_sibling_images_in_preview_and_formatted_edit(self):
        from io import BytesIO
        from PIL import Image
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        self.app.show_cloud()
        local = Path(self.temporary.name) / 'images'
        local.mkdir()
        data = BytesIO()
        Image.new('RGB', (12, 12), 'blue').save(data, 'WEBP')
        (local / 'photo.webp').write_bytes(data.getvalue())
        (local / 'Note.md').write_text('![Picture](photo.webp)')
        copies = LocalTextCopies(LocalFiles(local))
        with patch('toga.WebView.set_content', autospec=True) as content:
            self.assertTrue(self.app.loop.run_until_complete(self.app.open_crypt(copies=copies, key='Note.md')))
            owner = self.app.private_sessions.active
            self.assertTrue(any('<img src="data:image/webp;base64,' in call.args[2]
                                for call in content.call_args_list))
            content.reset_mock()
            owner.toggle_private_preview()
            self.assertTrue(any('data:image/webp;base64,' in call.args[2]
                                for call in content.call_args_list))
            self.assertEqual(owner.crypt_text.value, '![Picture](photo.webp)')
            self.assertFalse(owner.private_dirty())

    def test_provider_preview_edit_source_resume_and_explicit_editor_open(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        self.app.show_cloud()
        local = Path(self.temporary.name) / 'provider'
        local.mkdir()
        (local / 'Note.md').write_text('# Note\n')
        copies = LocalTextCopies(LocalFiles(local))
        run = self.app.loop.run_until_complete
        self.assertTrue(run(self.app.open_crypt(copies=copies, key='Note.md')))
        owner = self.app.private_sessions.active
        self.assertEqual(owner.crypt_content.children, [owner.crypt_preview])
        self.assertIn(owner.markdown_speech.button, owner.reader_toolbar.children)
        owner.toggle_private_preview()
        self.assertEqual(owner.crypt_content.children, [owner.crypt_formatted.view])
        bridge = owner.crypt_formatted
        bridge.navigate(None, bridge.bridge + '?text=' + quote('# Edited\n'))
        self.assertEqual(owner.crypt_text.value, '# Edited\n')
        self.app.private_sessions.suspend()
        self.assertTrue(bridge.closed)
        owner.resume_crypt()
        self.assertEqual(owner.crypt_content.children, [owner.crypt_formatted.view])
        owner.crypt_edit_mode.value = 'Source'
        self.assertEqual(owner.crypt_content.children, [owner.crypt_text])
        owner.toggle_private_preview()
        self.assertEqual(owner.crypt_content.children, [owner.crypt_preview])
        self.assertIn(owner.markdown_speech.button, owner.reader_toolbar.children)
        self.assertTrue(run(self.app.open_crypt(copies=copies, key='Note.md', edit=True)))
        self.assertEqual(owner.crypt_content.children, [owner.crypt_text])
        owner.crypt_edit_mode.value = 'Formatted'
        self.assertEqual(owner.crypt_content.children, [owner.crypt_formatted.view])
        self.assertTrue(self.app.private_sessions.close(owner.session.id, discard=True))
        self.assertTrue(run(self.app.open_crypt(copies=copies, key='Note.md', edit=True)))
        owner = self.app.private_sessions.active
        self.assertEqual(owner.crypt_content.children, [owner.crypt_formatted.view])
        self.assertNotIn(owner.crypt_text, owner.crypt_content.children)
        self.assertNotIn(owner.crypt_preview if hasattr(owner, 'crypt_preview') else None, owner.crypt_content.children)
        self.app.private_sessions.close(owner.session.id, discard=True)

    def test_memory_trim_preserves_active_markdown_surface_across_sleep(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        root = Path(self.temporary.name) / 'sleep'
        root.mkdir()
        (root / 'Read.md').write_text('# Keep reading\n')
        copies = LocalTextCopies(LocalFiles(root))
        self.assertTrue(self.app.loop.run_until_complete(self.app.open_crypt(copies=copies, key='Read.md')))
        owner = self.app.private_sessions.active
        for mode in ('preview', 'formatted', 'source'):
            with self.subTest(mode=mode):
                if mode == 'formatted':
                    owner.toggle_private_preview()
                elif mode == 'source':
                    owner.crypt_edit_mode.value = 'Source'
                surface = owner.crypt_content.children[0]
                self.app.screen_privacy.conceal()
                self.app.release_disposable_resources()
                self.app.release_disposable_resources()
                self.app.screen_privacy.reveal()
                self.assertEqual(owner.crypt_content.children, [surface])
                self.assertEqual(owner.crypt_markdown_mode, 'preview' if mode == 'preview' else 'edit')
                self.assertEqual(owner.crypt_text.value, '# Keep reading\n')
                if mode == 'preview':
                    self.assertEqual(owner.crypt_preview_button.control_icon, 'edit')
                    self.assertNotIn(owner.crypt_edit_mode, owner.crypt_markdown_footer.children)
                elif mode == 'formatted':
                    self.assertFalse(owner.crypt_formatted.closed)
        # Normal navigation must still retire hidden WebViews.
        owner.crypt_edit_mode.value = 'Formatted'
        formatted = owner.crypt_formatted
        self.app.show_settings()
        self.assertTrue(formatted.closed)
        self.assertIsNone(owner.crypt_formatted)
        owner.resume_crypt()
        self.assertEqual(owner.crypt_content.children, [owner.crypt_formatted.view])

    def test_markdown_web_surfaces_keep_fallback_and_opt_into_native_font_bridge(self):
        from mobile.preview import markdown_preview
        preview = markdown_preview('Paragraph and `code`')
        self.assertIn('html body{font-family:-apple-system,BlinkMacSystemFont,sans-serif}', preview)
        self.assertIn('code{font-family:monospace}', preview)
        self.assertIn('<meta name="logistics-native-font" content="true">', preview)
        content = editor_html('Paragraph', 'logistics-editor://test/')
        self.assertIn('font-size:16px', content)
        self.assertIn('font-family: -apple-system,BlinkMacSystemFont,sans-serif;', content)

    def test_code_and_unicode_line_separators_keep_correct_source_ranges(self):
        source = '# Heading\r\n\r\nText with \u2028 separator\r\n\r\n```html\r\n<tag>$5 [0]</tag>\r\n```\r\n'
        blocks = editor_blocks(source)
        self.assertEqual(''.join(block['source'] for block in blocks), source)
        code = next(block for block in blocks if block['source'].startswith('```'))
        self.assertTrue(code['editable'])
        self.assertIn('&lt;tag&gt;', code['html'])
        paragraph = next(block for block in blocks if block['source'].startswith('Text'))
        self.assertIn('separator', paragraph['html'])

    def test_exact_block_source_including_frontmatter_references_and_blank_lines(self):
        source = '---\ntitle: Keep\n---\n\n# Heading\n\n\nA [link][ref].\n\n[ref]: https://example.invalid\n\n[[Wiki|Title]]\n'
        blocks = editor_blocks(source)
        self.assertEqual(''.join(block['source'] for block in blocks), source)
        self.assertFalse(blocks[0]['editable'])
        self.assertTrue(next(block for block in blocks if block['source'].startswith('# '))['editable'])
        self.assertFalse(next(block for block in blocks if '[link]' in block['source'])['editable'])
        self.assertIn('data-markdown=', editor_html('![Alt](image.png)', 'logistics-editor://test/'))
        html = editor_html('</script><script>alert(1)</script> location.href = BRIDGE', 'logistics-editor://test/')
        self.assertNotIn('</script><script>alert', html)
        self.assertEqual(html.count('</script>'), 1)
        self.assertIn('default-src', html)
        self.assertEqual(view_state({'markdown_editor': 'source'}), {'markdown_editor': 'source'})
        with self.assertRaises(ValueError):
            view_state({'markdown_editor': 'invalid'})
        with self.assertRaises(ValueError):
            editor_blocks('x' * (1024 * 1024 + 1))
