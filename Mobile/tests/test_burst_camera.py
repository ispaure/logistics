"""Camera launch placement and generated-project permissions survive refreshes."""
import plistlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from Mobile.camera_build import configure
import test_hub_documents as home_fixture
from test_hub_documents import widgets


class CameraHomeTests(unittest.TestCase):
    setUp = home_fixture.HubDocumentTests.setUp
    tearDown = home_fixture.HubDocumentTests.tearDown

    def test_camera_at_bottom_and_action_presents(self):
        from features.images.mobile import burst_camera
        with patch.object(burst_camera, 'available', return_value=True), patch.object(burst_camera, 'present') as present:
            self.app.build_home()
            button = self.app.home_content.children[-1]
            self.assertEqual(button.text, 'Burst camera')
            self.assertEqual(self.app.home_sections.before.text, 'Camera')
            button.on_press()
            present.assert_called_once_with(self.app)

    def test_other_platform_has_no_camera_action(self):
        from features.images.mobile import burst_camera
        with patch.object(burst_camera, 'available', return_value=False):
            home = self.app.build_home()
        self.assertNotIn('Burst camera', [getattr(widget, 'text', '') for widget in widgets(home)])


class CameraPreferencesTests(unittest.TestCase):
    def test_preferences_validate_and_survive_restart(self):
        from logisticsmobile.preferences import Preferences
        with TemporaryDirectory() as directory:
            preferences = Preferences(directory)
            self.assertEqual(preferences.values['burst_camera'], 'rear_wide')
            self.assertEqual(preferences.values['burst_photos_per_second'], '8')
            for camera in ('rear_wide', 'rear_ultra_wide', 'rear_telephoto', 'front'):
                preferences.save(burst_camera=camera, burst_photos_per_second='3')
                reopened = Preferences(directory)
                self.assertEqual(reopened.values['burst_camera'], camera)
                self.assertEqual(reopened.values['burst_photos_per_second'], '3')
            before = preferences.path.read_bytes()
            for key, value in (('burst_camera', 'missing'), ('burst_photos_per_second', '0'),
                               ('burst_photos_per_second', '31'), ('burst_photos_per_second', 'nan')):
                with self.assertRaises(ValueError):
                    preferences.save(**{key: value})
                self.assertEqual(preferences.path.read_bytes(), before)

    def test_controls_autosave_and_restore_saved_choices(self):
        from types import SimpleNamespace
        from logisticsmobile.preferences import Preferences
        from features.images.mobile.burst_camera import settings_controls
        import toga
        with TemporaryDirectory() as directory, patch('features.images.mobile.burst_camera.available_cameras',
                return_value=['rear_wide', 'rear_ultra_wide', 'rear_telephoto', 'front']):
            app = SimpleNamespace(preferences=Preferences(directory))
            camera, rate, status = settings_controls(app, toga.Box())
            camera.value = 'Rear telephoto'
            rate.value = '3'
            rate.on_change()
            self.assertIn('saved', status.text)
            app.preferences = Preferences(directory)
            camera, rate, status = settings_controls(app, toga.Box())
            self.assertEqual(camera.value, 'Rear telephoto')
            self.assertEqual(rate.value, '3')
            from features.images.mobile.burst_camera import save_camera_preferences
            save_camera_preferences(app, 'front', '12')
            self.assertEqual(camera.value, 'Front')
            self.assertEqual(rate.value, '12')
            reopened = Preferences(directory)
            self.assertEqual(reopened.values['burst_camera'], 'front')
            self.assertEqual(reopened.values['burst_photos_per_second'], '12')
        with TemporaryDirectory() as directory, patch('features.images.mobile.burst_camera.available_cameras', return_value=['rear_wide']):
            app = SimpleNamespace(preferences=Preferences(directory))
            app.preferences.save(burst_camera='front')
            camera, rate, status = settings_controls(app, toga.Box())
            self.assertEqual(camera.value, 'Front (unavailable)')
            self.assertEqual(app.preferences.values['burst_camera'], 'front')


class CameraBuildTests(unittest.TestCase):
    def test_repeat_refresh_preserves_launcher_and_installs_permissions(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            app = project / 'LogisticsMobile'
            app.mkdir()
            launcher = app / 'main.m'
            launcher.write_text('#import <UIKit/UIKit.h>\nint main() {}\n')
            info = app / 'LogisticsMobile-Info.plist'
            info.write_bytes(plistlib.dumps({'ExistingKey': True}))
            configure(project)
            configure(project)
            self.assertEqual(launcher.read_text().count('#import "../Support/BurstCamera.m"'), 1)
            self.assertIn('int main() {}', launcher.read_text())
            settings = plistlib.loads(info.read_bytes())
            self.assertTrue(settings['ExistingKey'])
            self.assertIn('NSCameraUsageDescription', settings)
            self.assertIn('NSPhotoLibraryAddUsageDescription', settings)
            self.assertNotIn('NSPhotoLibraryUsageDescription', settings)
            self.assertTrue((project / 'Support/BurstCamera.m').is_file())
