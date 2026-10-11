"""Hunk card geometry remains compact across window and content sizes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase
from features.git.ui.preview import Preview


def patch_with_hunks(count, text='replacement'):
    patch = 'diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n'
    for index in range(count):
        line = 1 + index * 20
        patch += f'@@ -{line},2 +{line},2 @@\n context\n-old\n+{text}\n'
    return patch


class HunkLayoutTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.preview = Preview()
        self.preview.show()

    def settle(self):
        for _ in range(30):
            self.app.processEvents()
        self.assertFalse(self.preview.cards.height_timer.isActive(), 'Height calculation did not settle')

    def test_one_two_and_many_hunks_do_not_stretch_with_window_height(self):
        for count in (1, 2, 7):
            for staged in (True, False, None):
                context = None if staged is None else {'staged': staged, 'allowed': True}
                self.preview.show_diff('demo.py', patch_with_hunks(count), hunk_context=context)
                for width in (420, 800, 1400, 420):
                    self.preview.resize(width, 400)
                    self.settle()
                    cards = self.preview.cards.cards
                    heights = [card.height() for card in cards]
                    card_width = cards[0].width()
                    self.preview.resize(width, 1100)
                    self.settle()
                    # The outer scrollbar can narrow a card enough to wrap its title.
                    if cards[0].width() == card_width:
                        self.assertEqual([card.height() for card in cards], heights)
                    for card, editor in zip(cards, self.preview.cards.editors):
                        header = card.layout().itemAt(0).widget()
                        # Native Windows button metrics can wrap the title at
                        # narrow widths; that required height is not stretching.
                        needed = max(header.sizeHint().height(), header.heightForWidth(header.width()))
                        self.assertLessEqual(header.height(), needed + 2)
                        self.assertEqual(editor.verticalScrollBar().maximum(), 0)
                        self.assertLessEqual(card.geometry().right(), self.preview.cards.body.width())
                    for first, second in zip(cards, cards[1:]):
                        self.assertEqual(second.y() - first.geometry().bottom() - 1, 10)

    def test_wrapped_content_reflows_after_narrow_wide_narrow_resize(self):
        self.preview.show_diff('demo.py', patch_with_hunks(2, 'long replacement text ' * 35),
                               hunk_context={'staged': True, 'allowed': True})
        self.preview.wrap.setChecked(True)
        heights = []
        for width in (430, 1200, 430):
            self.preview.resize(width, 650)
            self.settle()
            editor = self.preview.cards.editors[0]
            heights.append(editor.height())
            self.assertEqual(editor.verticalScrollBar().maximum(), 0)
            self.assertEqual(editor.horizontalScrollBar().maximum(), 0)
        self.assertGreater(heights[0], heights[1])
        self.assertEqual(heights[0], heights[2])
        self.preview.wrap.setChecked(False)
        self.settle()
        self.assertLess(self.preview.cards.editors[0].height(), heights[0])
        self.assertGreater(self.preview.cards.editors[0].horizontalScrollBar().maximum(), 0)

    def test_many_hunks_scroll_as_a_list_and_keep_actions_accessible(self):
        self.preview.resize(430, 350)
        self.preview.show_diff('demo.py', patch_with_hunks(7),
                               hunk_context={'staged': True, 'allowed': True})
        self.settle()
        cards = self.preview.cards
        self.assertGreater(cards.verticalScrollBar().maximum(), 0)
        cards.ensureWidgetVisible(cards.cards[-1])
        self.settle()
        self.assertGreater(cards.verticalScrollBar().value(), 0)
        events = []
        self.preview.hunk_requested.connect(lambda context, index, action: events.append((index, action)))
        cards.cards[-1].findChild(qt.QToolButton).click()
        self.assertEqual(events, [(6, 'unstage')])

    def test_oversized_hunk_is_bounded_and_can_scroll(self):
        patch = '@@ -1,300 +1,300 @@\n' + ' context\n' * 300
        self.preview.resize(800, 500)
        self.preview.show_diff('large.txt', patch)
        self.settle()
        editor = self.preview.cards.editors[0]
        self.assertEqual(editor.height(), 4096)
        self.assertGreater(editor.verticalScrollBar().maximum(), 0)

    def test_font_changes_resize_content_and_replaced_cards_hide_immediately(self):
        self.preview.resize(800, 650)
        self.preview.show_diff('demo.py', patch_with_hunks(2))
        self.settle()
        editor = self.preview.cards.editors[0]
        previous_height = editor.height()
        font = qt.QFont(editor.font())
        font.setPointSizeF(font.pointSizeF() + 8)
        editor.setFont(font)
        self.settle()
        self.assertGreater(editor.height(), previous_height)
        self.assertEqual(editor.verticalScrollBar().maximum(), 0)
        previous_cards = list(self.preview.cards.cards)
        self.preview.show_diff('demo.py', patch_with_hunks(1))
        self.assertTrue(all(card.isHidden() for card in previous_cards))


class WindowsStyleHunkLayoutTests(HunkLayoutTests):
    """Keep the native-style spacing failure reproducible on every CI host."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.previous_style = cls.app.style().objectName()
        cls.previous_font = qt.QFont(cls.app.font())
        cls.app.setStyle('Windows')
        font = qt.QFont(cls.previous_font)
        font.setPointSize(13)
        cls.app.setFont(font)

    @classmethod
    def tearDownClass(cls):
        cls.app.setFont(cls.previous_font)
        cls.app.setStyle(cls.previous_style)
        super().tearDownClass()


if __name__ == '__main__':
    unittest.main()
