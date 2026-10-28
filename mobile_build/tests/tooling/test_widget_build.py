"""Protect isolated extension packaging and the existing app's identity."""
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest

from mobile_build.build_support.widget_build import configure_ios, EXTENSIONS, GROUP
from mobile_build.deployment.device_tools import signing_settings, BUNDLE, EXTENSION_SUFFIXES
from mobile_build.deployment.testflight_tools import export_options
from mobile_build.tests.tooling.widget_project import make_project


class WidgetBuildTests(unittest.TestCase):
    def test_repeatable_embedding_keeps_python_out_of_both_extensions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbx = make_project(root)
            configure_ios(root)
            first = pbx.read_bytes()
            configure_ios(root)
            self.assertEqual(first, pbx.read_bytes())
            data = plistlib.loads(first)
            objects = data['objects']
            targets = [obj for obj in objects.values() if obj.get('isa') == 'PBXNativeTarget']
            self.assertEqual(len(targets), 3)
            app = next(obj for obj in targets if obj['productType'] == 'com.apple.product-type.application')
            self.assertEqual(len(app['dependencies']), 2)
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
            self.assertEqual(next(phase['dstPath'] for phase in embeds if phase['dstSubfolderSpec'] == '16'),
                             '$(EXTENSIONS_FOLDER_PATH)')

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
                                     widget_profile={'UUID': 'widget'}, widget_actions_profile={'UUID': 'actions'})
            self.assertEqual(options['provisioningProfiles'], {
                BUNDLE: 'main', BUNDLE + '.inbox': 'inbox', BUNDLE + '.widgets': 'widget', BUNDLE + '.widget-actions': 'actions'})
            self.assertEqual(set(EXTENSION_SUFFIXES), {'.inbox', '.widgets', '.widget-actions'})
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
