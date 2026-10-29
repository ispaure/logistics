"""The native chat bridge belongs to the main app and preserves deployment targets."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from mobile_build.build_support.lm_build import configure_ios, configure_android
from mobile_build.tests.tooling.widget_project import make_project


class LMBuildTests(unittest.TestCase):
    def test_main_target_includes_bridge_once_and_weak_links_framework(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbx = make_project(root)
            configure_ios(root)
            first = pbx.read_bytes()
            configure_ios(root)
            self.assertEqual(pbx.read_bytes(), first)
            objects = plistlib.loads(first)['objects']
            app = next(obj for obj in objects.values() if obj.get('productType') == 'com.apple.product-type.application')
            sources = next(objects[key] for key in app['buildPhases'] if objects[key]['isa'] == 'PBXSourcesBuildPhase')
            paths = [objects[objects[key]['fileRef']]['path'] for key in sources['files']]
            self.assertEqual(paths.count('Support/FoundationChat.swift'), 1)
            self.assertTrue((root / 'Support/FoundationChat.swift').is_file())
            for key in objects[app['buildConfigurationList']]['buildConfigurations']:
                settings = objects[key]['buildSettings']
                self.assertEqual(settings['IPHONEOS_DEPLOYMENT_TARGET'], '17.0')
                self.assertIn('UIKit', settings['OTHER_LDFLAGS'])
                self.assertIn('-weak_framework', settings['OTHER_LDFLAGS'])
                self.assertIn('FoundationModels', settings['OTHER_LDFLAGS'])

    def test_android_preserves_host_minimum_and_existing_overrides(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'app/src/main/AndroidManifest.xml'
            path.parent.mkdir(parents=True)
            path.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                'xmlns:tools="http://schemas.android.com/tools"><uses-sdk android:minSdkVersion="24" '
                'tools:overrideLibrary="existing.library"/><application/></manifest>')
            configure_android(root)
            first = path.read_bytes()
            configure_android(root)
            self.assertEqual(path.read_bytes(), first)
            sdk = ET.parse(path).getroot().find('uses-sdk')
            self.assertEqual(sdk.get('{http://schemas.android.com/apk/res/android}minSdkVersion'), '24')
            self.assertEqual(sdk.get('{http://schemas.android.com/tools}overrideLibrary').split(','),
                ['existing.library', 'com.google.mlkit.genai.prompt', 'com.google.mlkit.genai.common'])
