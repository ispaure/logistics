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
            # Code typography is independent of the reading font signature.
            controller.values['code_font_size_int'] += 1
            controller.changed.emit()
            controller.changed.emit()
            self.assertEqual(render.call_count, 1)
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
        for mode in ('light', 'dark', 'light'):
            theme.set_mode(mode)
            for _ in range(4):
                self.app.processEvents()
            bubble = page.transcript.bubbles[short['id']]
            self.assertLess(bubble.width(), page.transcript.viewport().width() / 2)
            self.assertEqual(bubble.browser.source, 'test')
            code = page.transcript.bubbles[answer['id']].browser.document().rootFrame().childFrames()[0]
            self.assertEqual(code.format().background().color().lightness() > 128, mode == 'light')
            self.assertEqual(page.composer_frame.palette().color(qt.QPalette.ColorRole.Window).lightness() > 128,
                             mode == 'light')
            rendered = bubble.grab().toImage()
            background = rendered.pixelColor(bubble.width() // 2, 4)
            self.assertEqual(background.lightness() > 128, mode == 'light')
        data['messages'][0]['content'] = 'A longer message with many words. ' * 50
        page.transcript.sync(data)
        for width in (1000, 600):
            page.resize(width, 700)
            for _ in range(4):
                self.app.processEvents()
            self.assertLessEqual(bubble.width(), round((page.transcript.viewport().width() - 24) * .75))
