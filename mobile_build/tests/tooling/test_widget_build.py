"""Protect isolated extension packaging and the existing app's identity."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest

from mobile_build.build_support.widget_build import configure_ios, EXTENSIONS, GROUP
from mobile_build.deployment.device_tools import signing_settings, BUNDLE, EXTENSION_SUFFIXES
from mobile_build.deployment.testflight_tools import export_options
from mobile_build.tests.tooling.widget_project import make_project


class WidgetBuildTests(unittest.TestCase):
    def test_default_packaging_omits_watch_without_changing_phone_widgets(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbx = make_project(root)
            configure_ios(root)
            data = plistlib.loads(pbx.read_bytes())
            targets = [obj for obj in data['objects'].values() if obj.get('isa') == 'PBXNativeTarget']
            self.assertFalse(any(obj['name'].startswith('LogisticsWatch') for obj in targets))
            self.assertTrue(all(any(obj['name'] == name for obj in targets) for name, *_ in EXTENSIONS))
            self.assertFalse((root / 'LogisticsWatch').exists())

    def test_repeatable_embedding_keeps_python_out_of_both_extensions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbx = make_project(root)
            configure_ios(root, include_watch=True)
            first = pbx.read_bytes()
            configure_ios(root, include_watch=True)
            self.assertEqual(first, pbx.read_bytes())
            data = plistlib.loads(first)
            objects = data['objects']
            targets = [obj for obj in objects.values() if obj.get('isa') == 'PBXNativeTarget']
            self.assertEqual(len(targets), 5)
            app = next(obj for obj in targets if obj['productType'] == 'com.apple.product-type.application')
            self.assertEqual(len(app['dependencies']), 3)
            self.assertEqual((root / 'LogisticsMobile/main.m').read_text().count('Python'), 0)
            for name, suffix, point, local, shared in EXTENSIONS:
                target = next(obj for obj in targets if obj['name'] == name)
                sources = objects[target['buildPhases'][0]]['files']
                paths = [objects[objects[key]['fileRef']]['path'] for key in sources]
                self.assertEqual({Path(path).name for path in paths}, set(local + shared))
                for key in objects[target['buildConfigurationList']]['buildConfigurations']:
                    settings = objects[key]['buildSettings']
                    self.assertEqual(settings['PRODUCT_BUNDLE_IDENTIFIER'], BUNDLE + suffix)
                    self.assertNotIn('OTHER_LDFLAGS', settings)
                    self.assertNotIn('FRAMEWORK_SEARCH_PATHS', settings)
                    self.assertEqual(settings['APPLICATION_EXTENSION_API_ONLY'], 'YES')
                info = plistlib.loads((root / name / 'Info.plist').read_bytes())
                registration = info.get('NSExtension') or info['EXAppExtensionAttributes']
                self.assertIn(point, registration.values())
                self.assertEqual(info['CFBundleVersion'], '123')
                self.assertEqual(plistlib.loads((root / name / 'Extension.entitlements').read_bytes()),
                                 {'com.apple.security.application-groups': [GROUP]})
            entitlements = plistlib.loads((root / 'Main.entitlements').read_bytes())
            self.assertTrue(entitlements['preserve-me'])
            self.assertEqual(entitlements['com.apple.security.application-groups'], [GROUP])
            embeds = [objects[key] for key in app['buildPhases'] if objects[key]['isa'] == 'PBXCopyFilesBuildPhase']
            self.assertEqual({phase['dstSubfolderSpec'] for phase in embeds}, {'13', '16'})
            self.assertEqual(next(phase['dstPath'] for phase in embeds if phase['name'] == 'Embed LogisticsWidgetActions'),
                             '$(EXTENSIONS_FOLDER_PATH)')
            watch = next(obj for obj in targets if obj['name'] == 'LogisticsWatch')
            self.assertEqual(len(watch['dependencies']), 1)
            self.assertEqual(next(phase['dstPath'] for phase in embeds if phase['name'] == 'Embed LogisticsWatch'),
                             '$(CONTENTS_FOLDER_PATH)/Watch')
            for name, suffix in (('LogisticsWatch', '.watchkitapp'), ('LogisticsWatchWidget', '.watchkitapp.widgets')):
                target = next(obj for obj in targets if obj['name'] == name)
                for key in objects[target['buildConfigurationList']]['buildConfigurations']:
                    settings = objects[key]['buildSettings']
                    self.assertEqual(settings['SDKROOT'], 'watchos')
                    self.assertEqual(settings['WATCHOS_DEPLOYMENT_TARGET'], '10.0')
                    self.assertEqual(settings['PRODUCT_BUNDLE_IDENTIFIER'], BUNDLE + suffix)
                    self.assertNotIn('OTHER_LDFLAGS', settings)
                info = plistlib.loads((root / name / 'Info.plist').read_bytes())
                self.assertEqual(info['CFBundleVersion'], '123')
            info = plistlib.loads((root / 'LogisticsWatch/Info.plist').read_bytes())
            self.assertTrue(info['WKApplication'])
            self.assertFalse(info['WKRunsIndependentlyOfCompanionApp'])
            self.assertEqual(info['WKCompanionAppBundleIdentifier'], BUNDLE)

    def test_both_widget_extensions_receive_existing_team_and_manual_profiles(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbx = make_project(root)
            configure_ios(root)
            data = signing_settings(plistlib.loads(pbx.read_bytes()), 'ABCDEFGHIJ')
            for obj in data['objects'].values():
                settings = obj.get('buildSettings', {})
                if 'PRODUCT_BUNDLE_IDENTIFIER' in settings:
                    self.assertEqual(settings['DEVELOPMENT_TEAM'], 'ABCDEFGHIJ')
            options = export_options('ABCDEFGHIJ', {'UUID': 'main'}, inbox_profile={'UUID': 'inbox'},
                                     widget_profile={'UUID': 'widget'}, widget_actions_profile={'UUID': 'actions'}, watch_profile={'UUID': 'watch'},
                                     watch_widget_profile={'UUID': 'watch-widget'})
            self.assertEqual(options['provisioningProfiles'], {
                BUNDLE: 'main', BUNDLE + '.inbox': 'inbox', BUNDLE + '.widgets': 'widget', BUNDLE + '.widget-actions': 'actions',
                BUNDLE + '.watchkitapp': 'watch', BUNDLE + '.watchkitapp.widgets': 'watch-widget'})
            self.assertEqual(set(EXTENSION_SUFFIXES), {'.inbox', '.widgets', '.widget-actions', '.watchkitapp', '.watchkitapp.widgets'})
            with self.assertRaises(ValueError):
                export_options('ABCDEFGHIJ', widget_profile={'UUID': 'widget'})

    def test_unowned_entitlement_paths_are_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbx = make_project(root)
            data = plistlib.loads(pbx.read_bytes())
            for obj in data['objects'].values():
                if 'CODE_SIGN_ENTITLEMENTS' in obj.get('buildSettings', {}):
                    obj['buildSettings']['CODE_SIGN_ENTITLEMENTS'] = '../personal.entitlements'
            pbx.write_bytes(plistlib.dumps(data))
            with self.assertRaises(ValueError):
                configure_ios(root)
