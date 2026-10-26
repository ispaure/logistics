"""Theme transitions and content-sized chat messages without a remote server."""
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt


class LMAppearanceTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_multiline_draft_grows_to_half_the_chat_area_then_scrolls_and_shrinks(self):
        from features.lm.ui.page import LMPage
        from features.lm.storage import Store
        page = LMPage(store=Store(self.root / 'chat'))
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.prepare_close)
        page.resize(1000, 800)
        page.show()
        page.composer.setPlainText('Short draft')
        for _ in range(5):
            self.app.processEvents()
        short_height = page.composer.height()
        short_transcript = page.transcript.height() - page.composer_dock.height()
        page.composer.setPlainText('\n'.join(f'Line {index}' for index in range(10)))
        self.wait_until(lambda: page.composer.height() > 150 and page.composer.verticalScrollBar().maximum() == 0 and
                        page.transcript.height() - page.composer_dock.height() < short_transcript)
        self.assertLess(page.transcript.height() - page.composer_dock.height(), short_transcript)
        page.composer.setPlainText('\n'.join(f'Line {index}' for index in range(100)))
        self.wait_until(lambda: page.composer.verticalScrollBar().isVisible() and
                        abs(page.composer_dock.height() - page.message_surface.height() / 2) < 32)
        tall_height = page.composer.height()
        self.assertGreater(tall_height, 150)
        page.resize(1000, 600)
        self.wait_until(lambda: page.composer.height() < tall_height and
                        abs(page.composer_dock.height() - page.message_surface.height() / 2) < 32)
        page.composer.setPlainText('Short again')
        self.wait_until(lambda: page.composer.height() == short_height and
                        not page.composer.verticalScrollBar().isVisible())
        # Wrapping a single paragraph must grow the draft too. Keep this
        # fixture below the half-height cap with the current reading font;
        # overflow at the cap is exercised by the 100-line draft above.
        page.resize(1000, 800)
        page.composer.setPlainText('wrapped words ' * 20)
        for _ in range(5):
            self.app.processEvents()
        wide_height = page.composer.height()
        page.resize(650, 800)
        self.wait_until(lambda: page.composer.height() > wide_height and
                        page.composer.verticalScrollBar().maximum() == 0)

    def test_sidebar_uses_height_beside_the_compact_chat_footer(self):
        from features.lm.ui.page import LMPage
        from features.lm.storage import Store
        page = LMPage(store=Store(self.root / 'chat'))
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.prepare_close)
        page.resize(1000, 700)
        page.show()
        for _ in range(5):
            self.app.processEvents()
        self.assertTrue(page.chat_body.isAncestorOf(page.status_bar))
        self.assertTrue(page.chat_body.isAncestorOf(page.save_error))
        list_bottom = page.list.mapTo(page, page.list.rect().bottomLeft()).y()
        footer_top = page.status_bar.mapTo(page, qt.QPoint()).y()
        self.assertGreater(list_bottom, footer_top)
        self.assertLessEqual(page.height() - list_bottom, 10)

    def test_model_picker_opens_on_label_click_and_wraps_long_model_names(self):
        from features.lm.ui.page import LMPage
        from features.lm.storage import Store
        from PySide6.QtTest import QTest
        page = LMPage(store=Store(self.root / 'chat'))
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.prepare_close)
        page.conversations.new_conversation()
        long_name = 'organization/very-long-model-name-with-a-large-quantization-and-context-description'
        page.models_loaded([long_name, 'second-model'])
        page.resize(700, 800)
        page.show()
        for _ in range(8):
            self.app.processEvents()
        picker = page.model
        self.assertFalse(picker.isEditable())
        self.assertIsNone(picker.lineEdit())
        self.assertEqual(picker.currentText(), long_name)
        self.assertEqual(picker.toolTip(), long_name)
        _, text_layout, height = picker.name_layout()
        self.assertGreater(text_layout.lineCount(), 1)
        self.assertGreaterEqual(picker.height(), height)
        # Clicking the displayed name, rather than just the arrow, opens the list.
        QTest.mouseClick(picker, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(12, picker.height() // 2))
        self.app.processEvents()
        self.assertTrue(picker.view().isVisible())
        # Qt briefly ignores the release that opened the popup.
        QTest.qWait(200)
        index = picker.model().index(picker.findText('second-model'), 0)
        QTest.mouseMove(picker.view().viewport(), picker.view().visualRect(index).center())
        QTest.qWait(50)
        QTest.mouseClick(picker.view().viewport(), qt.Qt.MouseButton.LeftButton,
                         pos=picker.view().visualRect(index).center())
        self.app.processEvents()
        self.assertEqual(picker.currentText(), 'second-model')
        page.persist()
        self.assertEqual(page.store.load(page.data['id'])['model'], 'second-model')
        self.assertEqual(page.composer.placeholderText(), 'Enter Message')

    def test_floating_composer_clears_last_message_and_keeps_scrollbar_accessible(self):
        from commonUtils.ui.appearance.theme import apply_theme
        from features.lm.ui.page import LMPage
        from features.lm.storage import Store
        from features.lm.domain import message
        theme = apply_theme(self.app, mode='light')
        self.addCleanup(lambda: theme.set_mode('system'))
        page = LMPage(store=Store(self.root / 'chat'))
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.prepare_close)
        page.conversations.new_conversation()
        page.data['messages'] = [message('assistant', 'Previous message\n\n' * 5) for _ in range(12)]
        page.render()
        page.show()
        for mode, width, lines in (('light', 1000, 2), ('dark', 1000, 12), ('light', 700, 30)):
            theme.set_mode(mode)
            page.resize(width, 800)
            page.composer.setPlainText('\n'.join(f'Draft {index}' for index in range(lines)))
            if lines == 30:
                image = qt.QImage(60, 40, qt.QImage.Format.Format_RGB32)
                image.fill(qt.QColor('red'))
                page.paste_screenshot(image)
            for _ in range(12):
                self.app.processEvents()
            bar = page.transcript.verticalScrollBar()
            bar.setValue(bar.maximum())
            for _ in range(4):
                self.app.processEvents()
            surface = page.message_surface
            last = page.transcript.bubbles[page.data['messages'][-1]['id']]
            message_bottom = last.mapTo(surface, last.rect().bottomLeft()).y()
            draft_top = page.composer_frame.mapTo(surface, qt.QPoint()).y()
            self.assertLess(message_bottom, draft_top)
            self.assertEqual(page.transcript.height(), surface.height())
            dock_right = page.composer_dock.mapTo(surface, page.composer_dock.rect().topRight()).x()
            scroll_left = bar.mapTo(surface, qt.QPoint()).x()
            self.assertLess(dock_right, scroll_left)
            self.assertLessEqual(page.send_button.width(), 32)
            self.assertLessEqual(page.composer_frame.height() - page.send_button.geometry().bottom(), 12)
            self.assertLess(page.model.geometry().right(), page.send_button.x())
            self.assertTrue(page.attach_button.isVisible())
            self.assertEqual(page.selection_button.text(), 'Paste Selection')
            draft = page.composer.toPlainText()
            draft_position = page.composer_frame.mapTo(surface, qt.QPoint())
            bar.setValue(0)
            self.app.processEvents()
            self.assertEqual(page.composer_frame.mapTo(surface, qt.QPoint()), draft_position)
            self.assertEqual(page.composer.toPlainText(), draft)

    def test_duplicate_appearance_signals_preserve_document_and_selection(self):
        from commonUtils.ui.appearance.theme import apply_theme
        from commonUtils.ui.appearance.styling import styling
        from features.lm.ui.conversation_view import MessageBrowser
        theme = apply_theme(self.app, mode='light')
        controller = styling()
        original_values = dict(controller.values)
        self.addCleanup(lambda: controller.values.update(original_values))
        self.addCleanup(lambda: theme.set_mode('system'))
        browser = MessageBrowser()
        self.addCleanup(browser.deleteLater)
        source = 'Some **selected** text.\n\n```python\nprint(1)\n```'
        browser.set_source(source)
        cursor = browser.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(12, qt.QTextCursor.MoveMode.KeepAnchor)
        browser.setTextCursor(cursor)
        selection = browser.textCursor().selectedText()
        with patch.object(browser, 'set_source', wraps=browser.set_source) as render:
            theme.set_mode('dark')
            controller.changed.emit()
            theme.changed.emit('dark')
            self.assertEqual(render.call_count, 1)
            self.assertEqual(browser.textCursor().selectedText(), selection)
            render.reset_mock()
            controller.values['browser_font_size_int'] += 1
            controller.changed.emit()
            render.assert_not_called()
            # Rendered Markdown code now follows the reading font size, while
            # the code-editor size setting remains independent of chat prose.
            controller.values['code_font_size_int'] += 1
            controller.changed.emit()
            controller.changed.emit()
            render.assert_not_called()
            render.reset_mock()
            controller.values['reading_font_size_int'] += 1
            controller.changed.emit()
            controller.changed.emit()
            self.assertEqual(render.call_count, 1)
        self.assertEqual(browser.source, source)
        self.assertEqual(browser.textCursor().selectedText(), selection)
        with patch.object(browser, 'set_source', wraps=browser.set_source) as render:
            browser.set_source(source + '\nNew streamed content')
            self.assertIn('New streamed content', browser.toPlainText())
            self.assertEqual(render.call_count, 1)

    def test_chat_surfaces_and_code_follow_theme_and_short_bubbles_fit_text(self):
        from commonUtils.ui.appearance.theme import apply_theme
        from features.lm.ui.page import LMPage
        from features.lm.storage import Store
        from features.lm.domain import conversation, message
        theme = apply_theme(self.app, mode='dark')
        self.addCleanup(lambda: theme.set_mode('system'))
        page = LMPage(store=Store(self.root / 'chat'))
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.prepare_close)
        page.resize(1000, 700)
        page.show()
        data = conversation(profile_id='fixture', model='model')
        short = message('user', 'test')
        answer = message('assistant', '```python\nprint("hello")\n```')
        data['messages'] = [short, answer]
        page.transcript.sync(data)
        for mode in ('dark', 'light', 'dark', 'light'):
            theme.set_mode(mode)
            for _ in range(4):
                self.app.processEvents()
            bubble = page.transcript.bubbles[short['id']]
            self.assertLess(bubble.width(), page.transcript.viewport().width() / 2)
            self.assertEqual(bubble.browser.source, 'test')
            code = page.transcript.bubbles[answer['id']].browser.document().rootFrame().childFrames()[0]
            self.assertEqual(code.format().background().color().lightness() > 128, mode == 'light')
            self.assertGreaterEqual(abs(code.format().background().color().lightness() -
                                        self.app.palette().color(qt.QPalette.ColorRole.Base).lightness()), 12)
            self.assertEqual(page.composer_frame.palette().color(qt.QPalette.ColorRole.Window).lightness() > 128,
                             mode == 'light')
            rendered = bubble.grab().toImage()
            background = rendered.pixelColor(bubble.width() // 2, 4)
            self.assertEqual(background, self.app.palette().color(qt.QPalette.ColorRole.Link))
            foreground = bubble.browser.palette().color(qt.QPalette.ColorRole.Text)
            self.assertGreaterEqual(abs(background.lightness() - foreground.lightness()), 70)
            self.assertTrue(bubble.copy_button.isHidden())
            self.assertFalse(page.transcript.bubbles[answer['id']].copy_button.isHidden())
            panel = page.transcript.body.grab().toImage()
            sidebar = page.list.viewport().grab().toImage()
            self.assertEqual(panel.pixelColor(2, 2), sidebar.pixelColor(2, 2))
            self.assertEqual(panel.pixelColor(2, 2), self.app.palette().color(qt.QPalette.ColorRole.Base))
            self.assertNotEqual(panel.pixelColor(2, 2), self.app.palette().color(qt.QPalette.ColorRole.Window))
        data['messages'][0]['content'] = 'A longer message with many words. ' * 50
        page.transcript.sync(data)
        for width in (1000, 600):
            page.resize(width, 700)
            for _ in range(4):
                self.app.processEvents()
            self.assertLessEqual(bubble.width(), round((page.transcript.viewport().width() - 24) * .75))
