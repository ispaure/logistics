"""Real Qt pixels, rapid turns and private snapshot retirement."""
from commonUtils.tests.qt_test_case import QtTestCase
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QApplication
from services.documents.ui.page_transition import page_slide


class PageTransitionTests(QtTestCase):
    def test_outgoing_page_moves_over_new_content_and_releases_on_resize_hide(self):
        surface = QLabel()
        surface.resize(200, 100)
        surface.setStyleSheet('background: red')
        surface.show()
        self.addCleanup(surface.close)
        QApplication.processEvents()
        slide = page_slide(surface)
        slide.begin(1)
        surface.setStyleSheet('background: blue')
        slide.finish()
        slide.animation.pause()
        slide.advance(.5)
        self.assertTrue(slide.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        image = surface.grab().toImage()
        self.assertEqual(image.pixelColor(20, 50).name(), '#ff0000')
        self.assertEqual(image.pixelColor(180, 50).name(), '#0000ff')
        slide.begin(-1)
        self.assertEqual(slide.image.toImage().pixelColor(20, 50).name(), '#0000ff')
        slide.finish()
        surface.resize(210, 100)
        self.assertTrue(slide.image.isNull())
        slide.begin(1, vertical=True)
        slide.finish()
        surface.hide()
        self.assertTrue(slide.image.isNull())
        self.assertFalse(slide.isVisible())

    def test_same_page_and_unshown_content_do_not_capture(self):
        surface = QLabel()
        self.addCleanup(surface.close)
        slide = page_slide(surface)
        slide.begin(1)
        self.assertTrue(slide.image.isNull())
        surface.show()
        slide.begin(0)
        slide.finish()
        self.assertTrue(slide.image.isNull())
