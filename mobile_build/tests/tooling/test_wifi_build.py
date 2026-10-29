"""Wi-Fi platform declarations preserve identities, other entitlements and extensions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from mobile_build.build_support.wifi_build import configure_ios
from mobile_build.cloud_build import configure_android_appearance


class WifiBuildTests(unittest.TestCase):
    def test_ios_main_app_only_and_repeatable_configuration(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'App.xcodeproj').mkdir()
            (root / 'LogisticsMobile').mkdir()
            info = root / 'LogisticsMobile/LogisticsMobile-Info.plist'
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier': 'preserved'}))
            main, extension = root / 'main.entitlements', root / 'extension.entitlements'
            main.write_bytes(plistlib.dumps({'preserved': True}))
            extension.write_bytes(plistlib.dumps({'extension-only': True}))
            objects = dict(app=dict(productType='com.apple.product-type.application', buildConfigurationList='configs'),
                configs=dict(buildConfigurations=['debug', 'release']),
                debug=dict(buildSettings=dict(CODE_SIGN_ENTITLEMENTS='main.entitlements')),
                release=dict(buildSettings=dict(CODE_SIGN_ENTITLEMENTS='main.entitlements')),
                extension=dict(productType='com.apple.product-type.app-extension'))
            (root / 'App.xcodeproj/project.pbxproj').write_bytes(plistlib.dumps(dict(objects=objects)))
            configure_ios(root)
            first = main.read_bytes()
            configure_ios(root)
            self.assertEqual(first, main.read_bytes())
            self.assertEqual(plistlib.loads(main.read_bytes()),
                             {'preserved': True, 'com.apple.developer.networking.wifi-info': True})
            self.assertEqual(plistlib.loads(extension.read_bytes()), {'extension-only': True})
            self.assertEqual(plistlib.loads(info.read_bytes())['CFBundleIdentifier'], 'preserved')
            self.assertIn('NSLocationWhenInUseUsageDescription', plistlib.loads(info.read_bytes()))

    def test_android_removes_old_wifi_exclusion_and_keeps_foreground_permissions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            styles = root / 'app/src/main/res/values/styles.xml'
            styles.parent.mkdir(parents=True)
            styles.write_text('<resources/>')
            manifest = root / 'app/src/main/AndroidManifest.xml'
            manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                'xmlns:tools="http://schemas.android.com/tools"><uses-permission '
                'android:name="android.permission.ACCESS_WIFI_STATE" tools:node="remove"/><application/></manifest>')
            configure_android_appearance(root)
            configure_android_appearance(root)
            permissions = ET.parse(manifest).getroot().findall('uses-permission')
            wifi = [item for item in permissions if item.get('{http://schemas.android.com/apk/res/android}name')
                    == 'android.permission.ACCESS_WIFI_STATE']
            self.assertEqual(len(wifi), 1)
            self.assertIsNone(wifi[0].get('{http://schemas.android.com/tools}node'))
            names = {item.get('{http://schemas.android.com/apk/res/android}name') for item in permissions}
            self.assertIn('android.permission.ACCESS_FINE_LOCATION', names)
            self.assertNotIn('android.permission.ACCESS_BACKGROUND_LOCATION', names)
