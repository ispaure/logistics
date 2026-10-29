"""Snow preferences persist and high contrast removes the native decoration."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from mobile.preferences import Preferences
from mobile.snow import SeasonalSnow


class SeasonalSnowTests(unittest.TestCase):
    def test_native_overlay_only_attaches_during_holiday_window(self):
        app = NS(_impl=NS(), preferences=NS(values={'seasonal_snow': 'true', 'android_eink': 'false'}),
                 main_window=NS(_impl=NS(native=NS(traitCollection=NS(accessibilityContrast=0)))))
        snow = SeasonalSnow(app)
        snow.backend = 'toga_iOS.app'
        for day, active in ((date(2026, 12, 14), False), (date(2026, 12, 15), True),
                            (date(2027, 1, 2), True), (date(2027, 1, 3), False)):
            with self.subTest(day=day), patch('services.seasonal.date') as calendar, \
                    patch.object(snow, 'refresh_ios') as attach:
                calendar.today.return_value = day
                snow.refresh()
                self.assertEqual(attach.called, active)

    def test_appearance_switch_saves_and_failed_save_restores_choice(self):
        from mobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            with patch.object(LogisticsMobile, 'storage_root', Path(directory)):
                app = LogisticsMobile('Snow settings test', 'io.github.ispaure.snowtest')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_settings()
            app.settings_navigation.choose('Appearance')
            self.assertTrue(app.snow_choice.value)
            app.snow_choice.value = False
            self.assertEqual(Preferences(app.private_root).values['seasonal_snow'], 'false')
            with patch.object(app.preferences, 'save', side_effect=OSError('Save failed')):
                app.snow_choice.value = True
            self.assertFalse(app.snow_choice.value)
            self.assertIn('Save failed', app.settings_status.text)

    def test_default_persistence_and_validation(self):
        with TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory))
            self.assertEqual(preferences.values['seasonal_snow'], 'true')
            preferences.save(seasonal_snow='false')
            self.assertEqual(Preferences(Path(directory)).values['seasonal_snow'], 'false')
            with self.assertRaises(ValueError):
                preferences.save(seasonal_snow='yes')

    def test_high_contrast_removes_overlay_without_changing_preference(self):
        app = NS(_impl=NS(), preferences=NS(values={'seasonal_snow': 'true', 'android_eink': 'true'}))
        snow = SeasonalSnow(app)
        snow.backend = 'toga_iOS.app'
        view = snow.view = Mock()
        snow.refresh()
        view.removeFromSuperview.assert_called_once()
        self.assertIsNone(snow.view)
        self.assertEqual(app.preferences.values['seasonal_snow'], 'true')

    def test_native_contrast_and_out_of_season_do_not_attach(self):
        app = NS(_impl=NS(), preferences=NS(values={'seasonal_snow': 'true', 'android_eink': 'false'}),
                 main_window=NS(_impl=NS(native=NS(traitCollection=NS(accessibilityContrast=1)))))
        snow = SeasonalSnow(app)
        snow.backend = 'toga_iOS.app'
        with patch.object(snow, 'refresh_ios') as attach:
            snow.refresh()
            attach.assert_not_called()
            app.main_window._impl.native.traitCollection.accessibilityContrast = 0
            with patch('mobile.snow.snow_enabled', return_value=False):
                snow.refresh()
                attach.assert_not_called()


if __name__ == '__main__':
    unittest.main()
