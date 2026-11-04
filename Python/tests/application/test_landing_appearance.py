"""Rendered landing geometry and pointer feedback under the application theme."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtTest import QTest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.typography import point_size
from commonUtils.ui.appearance.theme import SLATE_DARK, SLATE_LIGHT, theme_palette, theme_stylesheet
from features.contributions import DocumentLauncherContribution
from desktop.landing import LandingPage


class LandingAppearanceTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance() or qt.QApplication([])
        palette, stylesheet = self.app.palette(), self.app.styleSheet()
        self.addCleanup(self.app.setPalette, palette)
        self.addCleanup(self.app.setStyleSheet, stylesheet)

    def page(self, colors):
        self.app.setPalette(theme_palette(colors))
        self.app.setStyleSheet(theme_stylesheet(colors))
        page = LandingPage()
        self.addCleanup(page.deleteLater)
        descriptions = (
            'Browse and organize files.',
            'Browse configured folders and services.',
            'Preview and rename files and folders.',
            'Inspect repository changes, stage files and manage commits.',
            'Work on code projects with editing, search and code analysis.',
            'Open this workspace.',
            'Chat with an existing LM server and keep conversations locally.',
            'Control rooms, brightness and color presets.',
            'Calculate flight distances, headings and aircraft performance.',
            'Open your configured websites and service shortcuts from one page.',
            'Manage versions and isolated user presets.',
        )
        page.set_tool_launchers([(str(i), 'Workspace ' + str(i), detail, 'git')
                                 for i, detail in enumerate(descriptions)])
        page.set_document_launchers({str(i): DocumentLauncherContribution(
            str(i), 'Text Editor', lambda: None, 'text', i, lambda: None,
            description='Read and edit documents in this format.') for i in range(6)})
        return page

    def test_section_headers_align_and_share_the_large_font(self):
        page = self.page(SLATE_LIGHT)
        page.resize(1250, 800)
        page.show()
        self.app.processEvents()
        page._settle_layout()
        headings = {label.text(): label for label in page.findChildren(qt.QLabel, 'sectionTitle')}
        self.assertEqual(set(headings), {'Features', 'Favourites', 'Recent', 'Read & edit'})
        for label in headings.values():
            self.assertAlmostEqual(label.font().pointSizeF(), point_size(19.5), places=1)
            self.assertTrue(label.font().bold())
        self.assertEqual(headings['Features'].mapTo(page, qt.QPoint()).y(),
                         headings['Favourites'].mapTo(page, qt.QPoint()).y())

    def test_read_edit_is_visible_below_saved_lists_with_one_card_per_row(self):
        page = self.page(SLATE_LIGHT)
        page.resize(1250, 800)
        page.show()
        self.app.processEvents()
        page._settle_layout()
        recent = page.recent_layout.itemAt(0).widget()
        self.assertTrue(page.document_section.isVisible())
        self.assertIs(page.document_section.parentWidget(), page.saved_files)
        self.assertGreater(page.document_section.y(), recent.geometry().bottom())
        self.assertEqual(page.document_grid.getItemPosition(1)[:2], (1, 0))
        self.assertEqual(page._document_columns, 1)

    def test_launch_columns_use_two_to_one_width_and_saved_lists_stack_on_the_right(self):
        page = self.page(SLATE_LIGHT)
        page.resize(1250, 800)
        page.show()
        self.app.processEvents()
        page._settle_layout()
        self.assertNotIn('hub', page.buttons)
        self.assertLessEqual(abs(page.choices.width() - 2 * page.saved_files.width()), 2)
        self.assertEqual(page.saved_files.x() - page.choices.geometry().right() - 1, 48)
        self.assertEqual(page.tool_grid.getItemPosition(1)[:2], (0, 1))
        self.assertEqual(page.tool_grid.getItemPosition(2)[:2], (1, 0))
        favourites = page.favourites_layout.itemAt(0).widget()
        recent = page.recent_layout.itemAt(0).widget()
        self.assertLess(favourites.y(), recent.y())
        page.resize(650, 800)
        self.app.processEvents()
        page._settle_layout()
        self.assertGreater(page.saved_files.y(), page.choices.geometry().bottom())
        self.assertEqual(page.tool_grid.getItemPosition(1)[:2], (1, 0))

    def test_long_saved_filenames_preserve_columns_and_reopen_the_full_entry(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        title = 'A very long favourite filename ' * 15 + '.md'
        row = dict(title=title, source={}, opener={})
        store = SimpleNamespace(entries=lambda *args, **kwargs: [row], errors=[])
        with patch('desktop.document_catalog.catalog', return_value=store), \
                patch('desktop.document_catalog.unlocked_ciphers', return_value=[]), \
                patch('desktop.document_catalog.reopen') as reopen:
            page = self.page(SLATE_LIGHT)
            page.resize(850, 550)
            page.show()
            self.app.processEvents()
            page._settle_layout()
            self.assertLessEqual(abs(page.choices.width() - 2 * page.saved_files.width()), 2)
            for layout in (page.favourites_layout, page.recent_layout):
                container = layout.itemAt(1).widget()
                button = container.findChild(qt.QPushButton)
                self.assertLessEqual(button.width(), page.saved_files.width())
                self.assertEqual(button.toolTip(), title)
                self.assertEqual(button.text(), title)
                button.click()
                reopen.assert_called_with(row, page)
            page.resize(650, 550)
            self.app.processEvents()
            page._settle_layout()
            self.assertEqual(page.saved_files.width(), page.content.width())

    def test_first_paint_preserves_positions_across_scrollbar_column_breakpoint(self):
        for colors in (SLATE_LIGHT, SLATE_DARK):
            for width, height in ((920, 800), (1250, 800), (850, 550)):
                with self.subTest(theme=colors.window, width=width, height=height):
                    page = self.page(colors)
                    page.resize(width, height)
                    widgets = [page.content, *page.content.findChildren(qt.QWidget)]
                    def geometry():
                        return [(w.mapTo(page, qt.QPoint()), w.size(), w.font().toString()) for w in widgets]
                    first = []
                    class Observer(qt.QObject):
                        def eventFilter(self, watched, event):
                            if event.type() == qt.QEvent.Type.Paint and not first:
                                first.extend(geometry())
                            return False
                    observer = Observer(page)
                    page._tool_cards[0].installEventFilter(observer)
                    page.show()
                    self.wait_until(lambda: bool(first))
                    for _ in range(20):
                        self.app.processEvents()
                    self.assertEqual(first, geometry())
                    page.hide()

    def test_hover_tints_both_card_types_without_moving_content(self):
        for colors in (SLATE_LIGHT, SLATE_DARK):
            with self.subTest(theme=colors.window):
                page = self.page(colors)
                page.resize(1100, 600)
                page.move(20, 40)
                page.show()
                page.raise_()
                page.activateWindow()
                self.app.processEvents()
                for card in (page._tool_cards[0], page._document_cards[0]):
                    page.scroll.ensureWidgetVisible(card)
                    self.app.processEvents()
                    QTest.mouseMove(page.scroll.viewport(), qt.QPoint(1, 1))
                    self.wait_until(lambda: card.grab().toImage().pixelColor(10, 10) == qt.QColor(colors.surface),
                                    message='Card did not clear its initial hover')
                    before = card.grab().toImage()
                    geometry = card.geometry()
                    label = card.findChild(qt.QLabel, 'launchTitle')
                    QTest.mouseMove(label, label.rect().center())
                    self.wait_until(lambda: card.grab().toImage().pixelColor(10, 10) == qt.QColor(colors.hover),
                                    message='Card did not highlight under the pointer')
                    hovered = card.grab().toImage()
                    self.assertNotEqual(before.pixelColor(10, 10), hovered.pixelColor(10, 10))
                    self.assertEqual(hovered.pixelColor(10, 10), qt.QColor(colors.hover))
                    self.assertEqual(card.geometry(), geometry)
                    QTest.mouseMove(page.scroll.viewport(), qt.QPoint(1, 1))
                    self.wait_until(lambda: card.grab().toImage().pixelColor(10, 10) == before.pixelColor(10, 10),
                                    message='Card did not clear its hover when the pointer left')
                page.hide()

    def test_missing_native_entry_recovers_home_card_hover(self):
        from commonUtils.ui.pyside.pointer_entry import PointerEntryRecovery
        page = self.page(SLATE_LIGHT)
        # Keep both card columns inside the offscreen backend's 800px screen;
        # recovery deliberately requires real global hit testing.
        page.resize(750, 600)
        page.move(20, 40)
        page.show()
        page.activateWindow()
        self.app.processEvents()
        helper = PointerEntryRecovery(self.app)
        self.addCleanup(helper.deleteLater)
        self.addCleanup(self.app.removeEventFilter, helper)
        for card in (page._tool_cards[0], page._document_cards[0]):
            page.scroll.ensureWidgetVisible(card)
            self.app.processEvents()
            handle = page.windowHandle()
            self.app.sendEvent(handle, qt.QEvent(qt.QEvent.Type.Leave))
            label = card.findChild(qt.QLabel, 'launchTitle')
            position = label.mapToGlobal(label.rect().center())
            self.assertTrue(helper.eligible(page))
            self.assertIs(self.app.widgetAt(position).window(), page)
            self.app.sendEvent(handle, qt.QMouseEvent(
                qt.QEvent.Type.MouseMove, qt.QPointF(page.mapFromGlobal(position)),
                qt.QPointF(position), qt.Qt.MouseButton.NoButton,
                qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier))
            self.assertTrue(card.underMouse())
            self.assertEqual(card.grab().toImage().pixelColor(10, 10), qt.QColor(SLATE_LIGHT.hover))

    def test_delayed_font_and_width_changes_never_paint_overlapping_rows(self):
        for colors in (SLATE_LIGHT, SLATE_DARK):
            with self.subTest(theme=colors.window):
                page = self.page(colors)
                host = qt.QMainWindow()
                self.addCleanup(host.deleteLater)
                stack = qt.QStackedWidget()
                stack.addWidget(page)
                host.setCentralWidget(stack)
                host.resize(1250, 800)
                host.show()
                for _ in range(10):
                    self.app.processEvents()
                frames = []
                bad_gaps = []
                def geometry():
                    return (page.content.geometry().getRect(),
                            tuple(c.geometry().getRect() for c in page._tool_cards + page._document_cards))
                class Observer(qt.QObject):
                    def eventFilter(self, watched, event):
                        if event.type() == qt.QEvent.Type.Paint:
                            frames.append(geometry())
                            for cards, columns in ((page._tool_cards, page._tool_columns),
                                                   (page._document_cards, page._document_columns)):
                                for i, card in enumerate(cards[:-columns]):
                                    below = cards[i + columns]
                                    gap = below.y() - card.y() - card.height()
                                    if gap < 16:
                                        bad_gaps.append((card.geometry().getRect(), below.geometry().getRect(), gap))
                        return False
                observer = Observer(page)
                page._tool_cards[0].installEventFilter(observer)
                for width, size in ((1250, 14), (920, 18), (650, 24), (420, 10), (1250, 10)):
                    with self.subTest(width=width, font=size):
                        frames.clear()
                        host.resize(width, 800)
                        font = qt.QFont(page.font())
                        font.setPointSizeF(point_size(size))
                        for card in page._tool_cards + page._document_cards:
                            for label in card.findChildren(qt.QLabel):
                                label.setFont(font)
                        self.wait_until(lambda: bool(frames))
                        for _ in range(12):
                            self.app.processEvents()
                        self.assertEqual(bad_gaps, [])
                        self.assertEqual(frames[0], geometry())
                        self.assertFalse(page._card_timer.isActive(), 'Layout must settle without an idle timer loop')
                host.hide()
