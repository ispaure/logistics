"""Calendar boundaries and the desktop decoration/settings contract."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from services.seasonal import snow_enabled


class SnowPolicyTests(unittest.TestCase):
    def test_season_includes_december_15_through_january_2(self):
        for day, expected in ((date(2026, 10, 20), False), (date(2026, 12, 14), False),
                              (date(2026, 12, 15), True),
                              (date(2026, 12, 31), True), (date(2027, 1, 1), True),
                              (date(2027, 1, 2), True), (date(2027, 1, 3), False),
                              (date(2027, 2, 28), False), (date(2028, 2, 29), False),
                              (date(2028, 3, 1), False), (date(2028, 7, 15), False)):
            with self.subTest(day=day):
                self.assertEqual(snow_enabled(today=day), expected)

    def test_setting_and_contrast_override_the_season(self):
        today = date(2026, 12, 20)
        self.assertFalse(snow_enabled(False, today=today))
        self.assertFalse(snow_enabled(True, True, today))


class DesktopSnowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from commonUtils.ui import pyside as qt
        cls.qt = qt
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_overlay_tracks_size_and_never_intercepts_input(self):
        from commonUtils.configuration.layered import LayeredSettings
        from desktop.snow import SnowOverlay, FIELD
        with TemporaryDirectory() as directory:
            store = LayeredSettings(Path(directory) / 'defaults.ini', Path(directory) / 'personal.ini')
            with patch('desktop.snow.settings_store', return_value=store), \
                    patch('desktop.snow.snow_enabled', side_effect=lambda enabled, contrast: enabled and not contrast):
                window = self.qt.QWidget()
                window.resize(640, 480)
                overlay = SnowOverlay(window)
                window.show()
                self.app.processEvents()
                overlay.refresh()
                self.assertTrue(overlay.isVisible())
                self.assertEqual(overlay.size(), window.size())
                self.assertTrue(overlay.testAttribute(self.qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents))
                self.assertEqual(overlay.focusPolicy(), self.qt.Qt.FocusPolicy.NoFocus)
                window.resize(800, 600)
                self.app.processEvents()
                self.assertEqual(overlay.size(), window.size())
                with patch.object(overlay, 'accessibility') as hints:
                    hints.contrastPreference.return_value = self.qt.Qt.ContrastPreference.HighContrast
                    overlay.refresh()
                    self.assertFalse(overlay.isVisible())
                    self.assertFalse(overlay.animation.isActive())
                overlay.refresh()
                self.assertTrue(overlay.isVisible())
                store.save({FIELD: 'false'})
                overlay.refresh()
                self.assertFalse(overlay.isVisible())
                self.assertFalse(overlay.animation.isActive())
                window.close()

    def test_appearance_switch_saves_selected_scope(self):
        from commonUtils.configuration.layered import LayeredSettings
        from desktop.pages.settings import CommonUtilsPanel
        from desktop.snow import FIELD
        with TemporaryDirectory() as directory:
            store = LayeredSettings(Path(directory) / 'defaults.ini', Path(directory) / 'personal.ini')
            with patch('desktop.pages.settings.settings_store', return_value=store):
                panel = CommonUtilsPanel(layered=True)
                self.assertTrue(panel.snow_choice.isChecked())
                panel.set_scope('personal')
                panel.snow_choice.setChecked(False)
                self.assertEqual(store.values()[FIELD], 'false')
                panel.set_scope('application')
                self.assertTrue(panel.snow_choice.isChecked())
                panel.set_scope('personal')
                self.assertFalse(panel.snow_choice.isChecked())
                panel.close()


if __name__ == '__main__':
    unittest.main()
