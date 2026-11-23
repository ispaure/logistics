"""Shared live magnifier settings survive new readers and process preferences."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
        self.assertEqual((comic.magnifier_zoom, pdf.magnifier_zoom), (200, 200))
        comic.change_magnifier_zoom(1)
        self.assertEqual(pdf.magnifier_zoom, 225)
        reloaded = Preferences(Path(self.directory.name))
        self.assertEqual(reloaded.values['magnifier_zoom'], '225')
        next_reader = magnifier.bind(Host(reloaded), PDFCanvas())
        next_reader.change_magnifier_zoom(-1)
        self.assertEqual(comic.magnifier_zoom, 200)
        self.assertEqual(pdf.magnifier_zoom, 200)
        self.assertEqual(self.preferences.values['magnifier_zoom'], '200')
        for _ in range(20):pdf.change_magnifier_zoom(1)
        self.assertEqual(comic.magnifier_zoom,300)
        for _ in range(20):comic.change_magnifier_zoom(-1)
        self.assertEqual(pdf.magnifier_zoom,150)

    def test_settings_and_other_window_update_without_overwriting_other_preferences(self):
        pdf = magnifier.bind(self.host, PDFCanvas())
        setting = magnifier.setting(self.host)
        label, slider = setting.children
        self.assertEqual((slider.min, slider.max, slider.tick_count), (150, 300, 7))
        self.assertTrue(label.text.endswith('200%'))
        second = Preferences(Path(self.directory.name))
        comic = magnifier.bind(Host(second), ImageCanvas())
        second.save(reading_margin='24')
        slider.value = 250
        self.assertEqual((pdf.magnifier_zoom, comic.magnifier_zoom), (250, 250))
        self.assertEqual(second.values['reading_margin'],'24')
        self.assertEqual(second.values['magnifier_zoom'], '250')
        self.assertEqual(Preferences(Path(self.directory.name)).values['reading_margin'],'24')
        comic.change_magnifier_zoom(-1)
        self.assertEqual(slider.value, 225)
        self.assertTrue(label.text.endswith('225%'))

    def test_failed_save_preserves_zoom_and_preferences(self):
        from unittest.mock import patch
        pdf = magnifier.bind(self.host, PDFCanvas())
        with patch.object(self.preferences,'save',side_effect=OSError('synthetic save failure')):
            self.assertFalse(pdf.change_magnifier_zoom(1))
        self.assertEqual(pdf.magnifier_zoom, 200)
        self.assertEqual(self.preferences.values['magnifier_zoom'], '200')

    def test_previously_valid_levels_load_at_nearest_new_level(self):
        for old, current in ((150, 150), (160, 150), (170, 175), (190, 200), (230, 225), (290, 300)):
            with self.subTest(old=old):
                self.preferences.path.write_text(f'[Mobile]\nmagnifier_zoom = {old}\nreading_margin = 24\n')
                values = self.preferences.reload()
                self.assertEqual(values['magnifier_zoom'], str(current))
                self.assertEqual(values['reading_margin'], '24')
                self.assertFalse(self.preferences.error)

    def test_invalid_preference_levels_are_rejected(self):
        for value in ('100', '149', '151', '251', '301', '310'):
            with self.assertRaises(ValueError):self.preferences.save(magnifier_zoom=value)
