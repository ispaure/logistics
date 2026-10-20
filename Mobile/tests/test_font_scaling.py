"""Per-format preferences and gesture updates preserve document content."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.preferences import Preferences
from logisticsmobile.font_scaling import FONT_KEYS, refresh


class FontScalingTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        for owner in self.app.text_views.values():
            owner.dispose()
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_legacy_size_migrates_and_categories_remain_independent_after_save(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.ini'
            path.write_text('[Mobile]\nfont_size = 23\nmarkdown_font_size = 19\n')
            prefs = Preferences(directory)
            self.assertEqual([prefs.values[key] for key in FONT_KEYS], ['19', '23', '23'])
            prefs.save(text_font_size='27')
            self.assertEqual([Preferences(directory).values[key] for key in FONT_KEYS], ['19', '27', '23'])
            for key in FONT_KEYS:
                with self.assertRaises(ValueError):
                    prefs.save(**{key: '33'})

    def test_settings_offer_one_independent_size_for_each_category(self):
        self.app.show_settings()
        for title, key, size in zip(('Markdown', 'Text', 'EPUB'), FONT_KEYS, ('20', '24', '28')):
            self.app.settings_navigation.choose(title)
            getattr(self.app, key + '_choice').value = size
        self.assertEqual([Preferences(self.app.private_root).values[key] for key in FONT_KEYS], ['20', '24', '28'])

    def test_pinch_commits_once_clamps_and_updates_other_editors_of_same_format(self):
        self.app.create_chosen_document('txt')
        first = self.app.editor_view
        first.editor.value = 'Unsaved words'
        self.app.create_chosen_document('txt')
        second = self.app.editor_view
        binding = first.editor._font_binding
        with patch.object(self.app.preferences, 'save', wraps=self.app.preferences.save) as save:
            binding.gesture('begin')
            binding.gesture('change', 1.5)
            self.assertEqual(first.editor.style.font_size, 24)
            save.assert_not_called()
            binding.gesture('end')
            save.assert_called_once_with(text_font_size='24')
        self.assertEqual(second.editor.style.font_size, 24)
        self.assertEqual(first.editor.value, 'Unsaved words')
        self.assertTrue(first.document.modified)
        self.assertEqual(self.app.preferences.values['markdown_font_size'], '16')
        binding.gesture('begin')
        binding.gesture('change', 100)
        binding.gesture('end')
        self.assertEqual(self.app.preferences.values['text_font_size'], '32')
        binding.gesture('begin')
        binding.gesture('change', .01)
        binding.gesture('cancel')
        self.assertEqual(first.editor.style.font_size, 32)

    def test_markdown_pinch_reflows_preview_and_formatted_editor_without_reload(self):
        self.app.create_chosen_document('md')
        owner = self.app.editor_view
        owner.editor.value = '# Unsaved heading\n'
        self.app.show_preview()
        formatted, preview = owner.formatted, owner.preview
        formatted.view.evaluate_javascript = AsyncMock()
        preview.evaluate_javascript = AsyncMock()
        with patch.object(formatted.view, 'set_content') as formatted_load, patch.object(preview, 'set_content') as preview_load:
            binding = preview._font_binding
            binding.gesture('begin')
            binding.gesture('change', 1.5)
            binding.gesture('end')
            self.app.loop.run_until_complete(asyncio.sleep(0))
            formatted_load.assert_not_called()
            preview_load.assert_not_called()
        self.assertEqual(formatted.font_size, 24)
        self.assertEqual(owner.editor.style.font_size, 24)
        self.assertIn("'24px'", preview.evaluate_javascript.call_args.args[0])
        self.assertEqual(owner.editor.value, '# Unsaved heading\n')
        self.assertTrue(owner.document.modified)

    def test_save_failure_restores_size_and_does_not_change_preferences(self):
        self.app.create_chosen_document('txt')
        binding = self.app.editor._font_binding
        with patch.object(self.app.preferences, 'save', side_effect=OSError('Read only')), self.assertLogs('logisticsmobile.font_scaling'):
            binding.gesture('begin')
            binding.gesture('change', 2)
            binding.gesture('end')
        self.assertEqual(self.app.editor.style.font_size, 16)
        self.assertEqual(self.app.preferences.values['text_font_size'], '16')

    def test_settings_layout_boxes_and_pickers_have_transparent_card_backgrounds(self):
        import toga
        self.app.show_settings()
        for title in ('App', 'Markdown', 'Text', 'EPUB'):
            section = self.app.settings_navigation.sections[title]
            for group in section.children:
                if getattr(group, '_settings_group', False):
                    for row in group.children:
                        if isinstance(row, (toga.Box, toga.Selection)) and row.style.height != 1:
                            self.assertEqual(row._impl._surface_roles[0], 'transparent')
        self.app.preferences.save(text_font_size='25')
        refresh(self.app)
        self.assertEqual(self.app.text_font_size_choice.value, '25')

    def test_web_load_preserves_previous_handler_and_reapplies_current_size(self):
        import toga
        from logisticsmobile.font_scaling import bind
        loaded = AsyncMock()
        web = toga.WebView(on_webview_load=loaded)
        web.evaluate_javascript = AsyncMock()
        bind(self.app, web, 'markdown', web=True)
        self.app.preferences.save(markdown_font_size='25')
        self.app.loop.run_until_complete(web.on_webview_load())
        self.app.loop.run_until_complete(asyncio.sleep(0))
        loaded.assert_awaited_once()
        self.assertIn("'25px'", web.evaluate_javascript.call_args.args[0])

    def test_ios_webkit_zoom_recognizer_may_be_absent_until_page_load(self):
        import toga
        from types import SimpleNamespace
        from logisticsmobile.font_scaling import bind
        web = toga.WebView()
        binding = bind(self.app, web, 'markdown', web=True)
        web._impl.native = SimpleNamespace(scrollView=SimpleNamespace(pinchGestureRecognizer=None))
        with patch.object(type(web._impl), '__module__', 'toga_iOS.widgets.webview'):
            binding.disable_web_zoom()
            recognizer = SimpleNamespace(enabled=True)
            web._impl.native.scrollView.pinchGestureRecognizer = recognizer
            binding.disable_web_zoom()
            self.assertFalse(recognizer.enabled)

    def test_custom_native_editors_and_private_webviews_resolve_their_backend(self):
        from types import SimpleNamespace
        from logisticsmobile.font_scaling import native_backend
        class AppleBackend:
            pass
        AppleBackend.__module__ = 'toga_iOS.widgets.webview'
        class PrivateBackend(AppleBackend):
            pass
        self.assertEqual(native_backend(SimpleNamespace(_impl=PrivateBackend())), 'toga_iOS.widgets.webview')
        self.assertEqual(native_backend(SimpleNamespace(backend_name='toga_android.widgets.multilinetextinput')),
                         'toga_android.widgets.multilinetextinput')

    def test_grouped_settings_match_the_app_palette_in_both_appearances(self):
        from logisticsmobile.palette import LIGHT, DARK
        for colors in (LIGHT, DARK):
            self.assertEqual(colors['settings_background'], colors['window'])
            self.assertEqual(colors['settings_group'], colors['surface'])
