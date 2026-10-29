
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import hashlib
import json
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest

from mobile_build.build_support import privacy_build
from mobile_build.deployment.testflight_tools import BUNDLE, inspect_app


class PrivacyBuildTests(unittest.TestCase):
    def project(self, root):
        project = root / 'Logistics Mobile.xcodeproj'
        project.mkdir()
        (project / 'project.pbxproj').write_bytes(plistlib.dumps({'objects': {
            'app': {'productType': 'com.apple.product-type.application', 'buildPhases': ['resources']},
            'group': {'isa': 'PBXGroup', 'path': 'LogisticsMobile', 'children': []},
            'resources': {'isa': 'PBXResourcesBuildPhase', 'files': []}}}))
        framework = root / 'Support/Python.xcframework'
        (framework / 'build').mkdir(parents=True)
        (framework / 'build/utils.sh').write_text(
            'mv "$MODULE_PATH/$MODULE_NAME.xcprivacy" "$XCPRIVACY_FILE"\n/usr/bin/codesign --force\n')
        for slice_name, arch in [('ios-arm64', 'arm64'), ('ios-arm64_x86_64-simulator', 'arm64'),
                                 ('ios-arm64_x86_64-simulator', 'x86_64')]:
            folder = framework / slice_name / ('lib-' + arch) / 'python3.12/lib-dynload'
            folder.mkdir(parents=True)
            for module in privacy_build.MODULES:
                (folder / (module + '.cpython-312-iphoneos.so')).touch()
        return framework

    def test_provider_manifest_matches_recorded_source_fingerprint(self):
        source = json.loads((privacy_build.MANIFEST.parent / 'source.json').read_text())
        self.assertEqual(hashlib.sha256(privacy_build.MANIFEST.read_bytes()).hexdigest(), source['sha256'])
        self.assertIn('/c012e5d4309b3a6767bcc5787f9cd57cfbcd48e9/', source['source_url'])

    def test_device_and_both_simulator_architectures_get_manifests_idempotently(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); framework = self.project(root)
            privacy_build.configure(root)
            privacy_build.configure(root)
            files = list(framework.glob('ios-*/lib*/python*/lib-dynload/*.xcprivacy'))
            self.assertEqual(len(files), 6)
            for p in files:
                self.assertEqual(p.read_bytes(), privacy_build.MANIFEST.read_bytes())
            data = plistlib.loads((root / 'Logistics Mobile.xcodeproj/project.pbxproj').read_bytes())
            self.assertEqual(len(data['objects']['resources']['files']), 1)
            self.assertEqual((root / 'LogisticsMobile/PrivacyInfo.xcprivacy').read_bytes(), privacy_build.APP_MANIFEST.read_bytes())

    def test_existing_different_declaration_is_not_silently_replaced(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); framework = self.project(root)
            path = next(framework.glob('ios-*/lib*/python*/lib-dynload')) / '_ssl.xcprivacy'
            path.write_bytes(plistlib.dumps({'NSPrivacyTracking': True}))
            with self.assertRaisesRegex(ValueError, 'differs'):
                privacy_build.configure(root)
            self.assertTrue(plistlib.loads(path.read_bytes())['NSPrivacyTracking'])

    def test_script_without_pre_sign_embedding_or_missing_extensions_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); framework = self.project(root)
            script = framework / 'build/utils.sh'; original = script.read_text()
            for bad in ['echo old support script', '\n'.join(reversed(original.splitlines()))]:
                script.write_text(bad)
                with self.assertRaisesRegex(ValueError, 'before signing'):
                    privacy_build.configure(root)
            script.write_text(original)
            next(framework.glob('ios-arm64/lib*/python*/lib-dynload/_ssl.*.so')).unlink()
            with self.assertRaisesRegex(ValueError, 'Missing Python OpenSSL extension'):
                privacy_build.configure(root)

    def test_release_inspection_rejects_missing_manifest_and_accepts_provider_copy(self):
        with TemporaryDirectory() as directory:
            app = Path(directory)
            (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': BUNDLE,
                'MainModule': 'logisticsmobile', 'CFBundleVersion': '145', 'CFBundleShortVersionString': '0.1.5'}))
            with self.assertRaisesRegex(ValueError, 'Missing OpenSSL privacy manifest'):
                inspect_app(app, {}, '145', signed=False)
            for module in privacy_build.MODULES:
                path = app / 'Frameworks' / (module + '.framework') / 'PrivacyInfo.xcprivacy'
                path.parent.mkdir(parents=True)
                path.write_bytes(privacy_build.MANIFEST.read_bytes())
            with self.assertRaisesRegex(ValueError, 'app privacy manifest'):
                inspect_app(app, {}, '145', signed=False)
            (app / 'PrivacyInfo.xcprivacy').write_bytes(privacy_build.APP_MANIFEST.read_bytes())
            self.assertEqual(inspect_app(app, {}, '145', signed=False)['build_number'], '145')
