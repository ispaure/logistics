"""Opt-in Android presentation policy, persistence and settings boundaries."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from logisticsmobile import palette
from logisticsmobile.preferences import Preferences
from logisticsmobile.appearance import configure_android_eink, contrast_ratio
from logisticsmobile.app import LogisticsMobile


class AndroidEInkTests(unittest.TestCase):
    def tearDown(self):
        palette.set_eink_enabled(False)

    def test_default_persistence_validation_and_platform_boundary(self):
        with TemporaryDirectory() as folder:
            prefs = Preferences(Path(folder).resolve())
            self.assertEqual(prefs.values['android_eink'], 'false')
            prefs.save(android_eink='true')
            self.assertEqual(Preferences(Path(folder).resolve()).values['android_eink'], 'true')
            with self.assertRaises(ValueError):
                prefs.save(android_eink='yes')
            delegate = SimpleNamespace(getLocalNightMode=lambda: -1, setLocalNightMode=Mock())
            android = type('Android', (), {'__module__': 'toga_android.app'})()
            android.native = SimpleNamespace(getDelegate=lambda: delegate)
            app = SimpleNamespace(_impl=android, preferences=prefs)
            configure_android_eink(app)
            self.assertTrue(palette.eink_enabled())
            delegate.setLocalNightMode.assert_called_once_with(1)
            palette.set_eink_enabled(False)
            app._impl = SimpleNamespace()
            configure_android_eink(app)
            self.assertFalse(palette.eink_enabled())

    def test_palette_and_html_are_reversible_without_recoloring_images(self):
        original = '<html><head></head><body>Text<img src="page.png"></body></html>'
        self.assertIs(palette.android_palette(), palette.LIGHT)
        self.assertEqual(palette.eink_html(original), original)
        palette.set_eink_enabled(True)
        self.assertIs(palette.android_palette(dark=True), palette.EINK)
        self.assertEqual(contrast_ratio(palette.argb(palette.EINK['text']), palette.argb(palette.EINK['surface'])), 21)
        html = palette.eink_html(original)
        self.assertIn('id="logistics-eink"', html)
        self.assertIn('<img src="page.png">', html)
        self.assertNotIn('filter:', html)
        palette.set_eink_enabled(False)
        self.assertIs(palette.android_palette(dark=True), palette.DARK)
        self.assertEqual(palette.eink_html(original), original)
        self.assertIn('old.remove()', palette.eink_script())

    def test_toggle_saves_immediately_and_failed_save_reverts_the_switch(self):
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_settings()
            self.assertFalse(hasattr(app, 'android_eink_choice'))
            switch = SimpleNamespace(value=True, on_change=app.change_android_eink)
            with patch('logisticsmobile.appearance.configure_android_eink') as apply, patch.object(app, 'refresh_native_theme') as refresh:
                app.change_android_eink(switch)
                self.assertEqual(app.preferences.values['android_eink'], 'true')
                apply.assert_called_once_with(app)
                refresh.assert_called_once_with()
                with patch.object(app.preferences, 'save', side_effect=ValueError('Concurrent edit')):
                    switch.value = False
                    app.change_android_eink(switch)
                self.assertTrue(switch.value)
                self.assertIn('Concurrent edit', app.settings_status.text)
