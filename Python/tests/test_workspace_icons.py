"""Rendered workspace artwork retains its state and palette without an accent."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from services.folders.appearance import LOCK_LIGHT, LOCK_DARK
from desktop.pages.workspace_icons import folder_icon


class WorkspaceIconTests(QtTestCase):
    def test_rendered_states_have_solid_bodies_and_transparent_keyholes(self):
        widget = qt.QWidget()
        self.addCleanup(widget.close)
        for state in ('locked', 'unlocked'):
            image = folder_icon(widget, state).pixmap(72, 72).toImage()
            self.assertGreater(image.pixelColor(28, 46).alpha(), 240)
            self.assertLess(image.pixelColor(36, 46).alpha(), 20)
        closed = folder_icon(widget, 'locked').pixmap(72, 72).toImage()
        opened = folder_icon(widget, 'unlocked').pixmap(72, 72).toImage()
        self.assertNotEqual(closed, opened)

    def test_regular_and_unlocked_use_the_same_blue_in_both_themes(self):
        widget = qt.QWidget()
        self.addCleanup(widget.close)
        for base, colors in (('#fafbfc', LOCK_LIGHT), ('#2d3035', LOCK_DARK)):
            palette = widget.palette()
            palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor(base))
            palette.setColor(qt.QPalette.ColorRole.Highlight, qt.QColor('#ff00ff'))
            widget.setPalette(palette)
            for state in (None, 'unlocked'):
                image = folder_icon(widget, state).pixmap(72, 72).toImage()
                # Left folder edge is fully opaque in every state.
                self.assertEqual(image.pixelColor(7, 40).name(), colors['folder_unlocked'])
