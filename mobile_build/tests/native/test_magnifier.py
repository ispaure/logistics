"""Shared live magnifier settings survive new readers and process preferences."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.ui.native.image_canvas import ImageCanvas
from features.pdf.mobile.canvas import PDFCanvas
from mobile import magnifier
from mobile.preferences import Preferences


class Host:
    active_host = False
    def __init__(self, preferences):self.preferences = preferences


class MagnifierTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.preferences = Preferences(Path(self.directory.name))
        self.host = Host(self.preferences)

    def test_comic_and_pdf_share_changes_and_restore_after_restart(self):
        comic = magnifier.bind(self.host, ImageCanvas())
        pdf = magnifier.bind(self.host, PDFCanvas())
        self.assertEqual((comic.magnifier_zoom, pdf.magnifier_zoom), (190,190))
        comic.change_magnifier_zoom(1)
        self.assertEqual(pdf.magnifier_zoom,200)
        reloaded = Preferences(Path(self.directory.name))
        self.assertEqual(reloaded.values['magnifier_zoom'],'200')
        next_reader = magnifier.bind(Host(reloaded), PDFCanvas())
        next_reader.change_magnifier_zoom(-1)
        self.assertEqual(comic.magnifier_zoom,190)
        self.assertEqual(pdf.magnifier_zoom,190)
        self.assertEqual(self.preferences.values['magnifier_zoom'],'190')
        for _ in range(20):pdf.change_magnifier_zoom(1)
        self.assertEqual(comic.magnifier_zoom,300)
        for _ in range(20):comic.change_magnifier_zoom(-1)
        self.assertEqual(pdf.magnifier_zoom,150)

    def test_settings_and_other_window_update_without_overwriting_other_preferences(self):
        pdf = magnifier.bind(self.host, PDFCanvas())
        setting = magnifier.setting(self.host)
        label, slider = setting.children
        self.assertEqual((slider.min, slider.max, slider.tick_count), (150, 300, 16))
        self.assertTrue(label.text.endswith('190%'))
        second = Preferences(Path(self.directory.name))
        comic = magnifier.bind(Host(second), ImageCanvas())
        second.save(reading_margin='24')
        slider.value = 230
        self.assertEqual((pdf.magnifier_zoom,comic.magnifier_zoom),(230,230))
        self.assertEqual(second.values['reading_margin'],'24')
        self.assertEqual(second.values['magnifier_zoom'],'230')
        self.assertEqual(Preferences(Path(self.directory.name)).values['reading_margin'],'24')
        comic.change_magnifier_zoom(-1)
        self.assertEqual(slider.value, 220)
        self.assertTrue(label.text.endswith('220%'))

    def test_failed_save_preserves_zoom_and_preferences(self):
        from unittest.mock import patch
        pdf = magnifier.bind(self.host, PDFCanvas())
        with patch.object(self.preferences,'save',side_effect=OSError('synthetic save failure')):
            self.assertFalse(pdf.change_magnifier_zoom(1))
        self.assertEqual(pdf.magnifier_zoom,190)
        self.assertEqual(self.preferences.values['magnifier_zoom'],'190')

    def test_previously_valid_levels_load_without_normalization(self):
        for value in range(150, 251, 20):
            self.preferences.path.write_text(f'[Mobile]\nmagnifier_zoom = {value}\n')
            self.assertEqual(self.preferences.reload()['magnifier_zoom'], str(value))
            self.assertFalse(self.preferences.error)

    def test_invalid_preference_levels_are_rejected(self):
        for value in ('100', '149', '151', '251', '301', '310'):
            with self.assertRaises(ValueError):self.preferences.save(magnifier_zoom=value)
