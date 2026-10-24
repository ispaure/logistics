"""Native share registration, embedding and repeatable project updates."""
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from mobile_build.build_support.incoming_build import configure_android, configure_ios, GROUP, ACTIVITY


class IncomingBuildTests(unittest.TestCase):
    def test_android_granted_shares_are_exported_without_extra_permissions(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / 'app/src/main/AndroidManifest.xml'
            path.parent.mkdir(parents=True)
            path.write_text('<manifest><application><activity name="original"/></application></manifest>')
            configure_android(project)
            first = path.read_bytes()
            configure_android(project)
            self.assertEqual(path.read_bytes(), first)
            root = ET.parse(path).getroot()
            attr = lambda name: '{http://schemas.android.com/apk/res/android}' + name
            receiver = next(a for a in root.findall('application/activity') if a.get(attr('name')) == ACTIVITY)
            self.assertEqual(receiver.get(attr('exported')), 'true')
            self.assertEqual({a.get(attr('name')) for a in receiver.findall('intent-filter/action')},
                {'android.intent.action.SEND', 'android.intent.action.SEND_MULTIPLE'})
            self.assertEqual(root.findall('uses-permission'), [])

    def test_ios_extension_is_embedded_and_existing_entitlements_are_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'App.xcodeproj').mkdir()
            (root / 'LogisticsMobile').mkdir()
            (root / 'LogisticsMobile/main.m').write_text('#import <UIKit/UIKit.h>\n')
            info = root / 'LogisticsMobile/LogisticsMobile-Info.plist'
            info.write_bytes(plistlib.dumps({'CFBundleVersion':'123', 'CFBundleShortVersionString':'1.0'}))
            entitlements = root / 'existing.entitlements'
            entitlements.write_bytes(plistlib.dumps({'preserve-me':True}))
            data = dict(rootObject='project', objects=dict(
                project=dict(isa='PBXProject', targets=['app'], mainGroup='main', productRefGroup='products'),
                main=dict(isa='PBXGroup', children=[]), products=dict(isa='PBXGroup', children=[]),
                app=dict(isa='PBXNativeTarget', productType='com.apple.product-type.application',
                         buildConfigurationList='configs', buildPhases=[], dependencies=[]),
                configs=dict(isa='XCConfigurationList', buildConfigurations=['debug', 'release']),
                debug=dict(isa='XCBuildConfiguration', name='Debug', buildSettings=dict(
                    PRODUCT_BUNDLE_IDENTIFIER='io.github.ispaure.logisticsmobile', CODE_SIGN_ENTITLEMENTS='existing.entitlements')),
                release=dict(isa='XCBuildConfiguration', name='Release', buildSettings=dict(
                    PRODUCT_BUNDLE_IDENTIFIER='io.github.ispaure.logisticsmobile', CODE_SIGN_ENTITLEMENTS='existing.entitlements'))))
            pbx = root / 'App.xcodeproj/project.pbxproj'
            pbx.write_bytes(plistlib.dumps(data))
            configure_ios(root)
            first = pbx.read_bytes()
            configure_ios(root)
            self.assertEqual(pbx.read_bytes(), first)
            configured = plistlib.loads(pbx.read_bytes())['objects']
            targets = [o for o in configured.values() if o.get('productType') == 'com.apple.product-type.app-extension']
            self.assertEqual(len(targets), 1)
            self.assertTrue(configured['app']['dependencies'])
            self.assertTrue(any(configured[key]['isa'] == 'PBXCopyFilesBuildPhase' for key in configured['app']['buildPhases']))
            self.assertEqual(plistlib.loads(entitlements.read_bytes()),
                {'preserve-me':True, 'com.apple.security.application-groups':[GROUP]})
            self.assertEqual((root / 'LogisticsMobile/main.m').read_text().count('IncomingFiles.m'), 1)
            extension_info = plistlib.loads((root / 'IncomingShare/Info.plist').read_bytes())
            self.assertEqual(extension_info['NSExtension']['NSExtensionPointIdentifier'], 'com.apple.share-services')
            self.assertIn('CFBundleDocumentTypes', plistlib.loads(info.read_bytes()))
