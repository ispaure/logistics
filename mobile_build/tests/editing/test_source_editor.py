"""Single-surface Markdown editing and retained native source ownership."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mobile.app import LogisticsMobile
from commonUtils.ui.native.code_input import CodeInput
from toga.style.pack import COLUMN, ROW


class SourceEditorTests(unittest.TestCase):
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

    def open(self, name):
        document = self.app.store.create(name)
        self.app.refresh_documents()
        self.app.open_document(document.id)
        self.app.show_documents()
        return self.app.editor_view

    def test_markdown_uses_one_formatted_surface_at_phone_and_wide_widths(self):
        owner = self.open('Live.md')
        self.assertIsInstance(owner.editor, CodeInput)
        self.assertIs(owner.language_selection, owner.editor.language_selection)
        self.assertIsNotNone(owner.formatted)
        for width in (390, 800, 1200):
            owner.session.view['markdown_split'] = True  # Old versions' preference.
            owner.apply_split(width)
            self.assertEqual(owner.editor_area.children, [owner.formatted.view])
        source = '# Title\n\n| A | B |\n| --- | --- |\n| 1 | 2 |'
        owner.formatted_changed(source)
        self.assertEqual(owner.document.text, source)
        self.assertEqual(owner.editor.value, source)
        owner.edit_mode.value = 'Source'
        self.assertEqual(owner.editor_area.children, [owner.editor])
        owner.edit_mode.value = 'Formatted'
        self.assertEqual(owner.editor_area.children, [owner.formatted.view])
        self.assertEqual(owner.document.text, source)

    def test_source_language_and_line_count_do_not_modify_text(self):
        owner = self.open('sample.py')
        self.assertIsNone(owner.formatted)
        source = 'def hello():\n    return "😀"\n'
        owner.editor.value = source
        self.assertEqual(owner.editor.language, 'python')
        self.assertEqual(owner.line_count.text, '3 lines')
        owner.language_choice.value = 'JSON'
        self.assertEqual(owner.editor.language, 'json')
        self.assertEqual(owner.editor.value, source)
        owner.language_choice.value = 'Automatic'
        self.assertEqual(owner.editor.language, 'python')
        owner.dispose()
        self.assertIsNone(owner.editor.pending)
        self.assertTrue(owner.editor.closed)

    def test_language_selection_follows_rename_and_is_independent_per_document(self):
        first = self.open('first.py')
        source = 'print(1)'
        first.editor.value = source
        self.app.save_document()
        first.language_choice.value = 'Plain Text'
        self.assertEqual(first.language_selection.selected_id, 'text')
        self.assertFalse(first.document.modified)
        first.name.value = 'renamed.json'
        self.assertEqual(first.editor.language, 'text')
        self.assertEqual(first.language_selection.detected_id, 'json')
        second = self.open('second.py')
        self.assertTrue(second.language_selection.automatic)
        self.assertEqual(second.language_choice.value, 'Automatic')
        self.assertEqual(second.editor.language, 'python')
        self.app.open_document(first.document.id)
        self.assertIs(self.app.editor_view, first)
        self.assertEqual(first.language_choice.value, 'Plain Text')
        first.language_choice.value = 'Automatic'
        self.assertTrue(first.language_selection.automatic)
        self.assertEqual(first.editor.language, 'json')
        self.assertEqual(first.editor.value, source)

    def test_automatic_language_follows_shebang_edits_until_manually_selected(self):
        owner = self.open('script')
        owner.editor.value = '#!/usr/bin/env python\nprint(1)'
        self.assertEqual(owner.language_selection.language_id, 'python')
        owner.language_choice.value = 'JSON'
        owner.editor.value = '#!/bin/sh\necho hi'
        self.assertEqual(owner.editor.language, 'json')
        self.assertEqual(owner.language_selection.detected_id, 'bash')
        owner.language_choice.value = 'Automatic'
        self.assertEqual(owner.editor.language, 'bash')

    def test_typing_does_not_relayout_unchanged_status_and_line_count(self):
        for name in ('Typing.txt', 'Typing.md'):
            with self.subTest(name=name):
                owner = self.open(name)
                owner.editor.value = 'First edit'
                with patch.object(owner.status._impl, 'set_text') as status, patch.object(
                        owner.line_count._impl, 'set_text') as lines:
                    owner.editor.value = 'Continuing on the same line'
                    status.assert_not_called()
                    lines.assert_not_called()
                self.assertEqual(owner.document.text, 'Continuing on the same line')

    def test_closing_ios_preview_retires_delegates_before_loading_closed_content(self):
        owner = self.open('Closed.md')
        events = []
        def clear_dom(script, **kwargs):
            self.assertEqual(events, ['stop'])
            self.assertIn('replaceChildren(body)', script)
            self.assertNotIn('document.open(', script)
            self.assertIn('Document closed.', script)
            events.append('dom')
        native = SimpleNamespace(navigationDelegate=object(), UIDelegate=object(),
                                 stopLoading=lambda: events.append('stop'), evaluateJavaScript=clear_dom)
        class IOSWebView:
            __module__ = 'toga_iOS.widgets.webview'
        impl = IOSWebView()
        impl.native = native
        def clear(*args):
            self.assertEqual(events, ['stop', 'dom'])
            self.assertIsNone(native.navigationDelegate)
            self.assertIsNone(native.UIDelegate)
            events.append('clear')
        preview = SimpleNamespace(_impl=impl, set_content=clear)
        with patch.object(owner.formatted, 'view', preview):
            owner.dispose()
        self.assertEqual(events, ['stop', 'dom', 'clear'])

    def test_managed_preview_reuses_owner_controls_and_routes_edit_to_its_session(self):
        first = self.open('First.md')
        first.editor.value = '# First content'
        self.assertTrue(self.app.show_preview())
        retained = first.preview_box, first.preview_search, first.preview_edit, first.markdown_speech
        previous_menu = first.preview_actions
        self.assertTrue(self.app.show_preview())
        self.assertTrue(previous_menu.disposed)
        self.assertEqual((first.preview_box, first.preview_search, first.preview_edit, first.markdown_speech), retained)
        self.assertIs(first.preview_box._native_reader_toolbar, first.preview_toolbar)
        self.assertEqual(first.preview_box._native_reader_buttons(),
                         [first.preview_edit, first.preview_actions_button])
        second = self.open('Second.md')
        self.assertTrue(self.app.show_preview())
        self.assertIsNot(second.preview_box, first.preview_box)
        first.document.name = 'Renamed.md'
        self.assertEqual(first.preview_box._native_reader_title(), 'Renamed.md')
        first.preview_edit.on_press()
        self.assertIs(self.app.editor_view, first)
        self.assertEqual(self.app.workspace.active, first.session.id)
        self.assertEqual(first.session.view['markdown_mode'], 'edit')

    def test_managed_preview_edit_respects_checkpoint_veto_and_retired_token(self):
        first = self.open('First.md')
        self.assertTrue(self.app.show_preview())
        second = self.open('Second.md')
        with patch.object(self.app, 'checkpoint', return_value=False) as checkpoint:
            first.preview_edit.on_press()
        checkpoint.assert_called_once()
        self.assertIs(self.app.editor_view, second)
        self.app.workspace.invalidate(first.session.id)
        with patch.object(self.app, 'checkpoint', side_effect=AssertionError('Retired callback checkpointed')):
            first.preview_edit.on_press()
        self.assertIs(self.app.editor_view, second)
        self.assertEqual(self.app.workspace.active, second.session.id)
