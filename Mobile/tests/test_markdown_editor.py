"""Markdown defaults, block preservation and per-owner bridge lifetime."""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote
import unittest
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.workspace import view_state
from features.text_editor.mobile.markdown_editor import editor_blocks, editor_html


class MarkdownEditorTests(unittest.TestCase):
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

    def test_provider_markdown_uses_one_toolbar_and_no_clean_save(self):
        from commonUtils.runtime.local_files import LocalFiles
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
        from commonUtils.runtime.local_files import LocalFiles
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
        from commonUtils.runtime.local_files import LocalFiles
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
        from commonUtils.runtime.local_files import LocalFiles
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
        from logisticsmobile.preview import markdown_preview
        preview = markdown_preview('Paragraph and `code`')
        self.assertIn('html body{font-family:-apple-system,BlinkMacSystemFont,sans-serif}', preview)
        self.assertIn('code{font-family:monospace}', preview)
        self.assertIn('<meta name="logistics-native-font" content="true">', preview)
        self.assertIn('16px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;',
                      editor_html('Paragraph', 'logistics-editor://test/'))

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
