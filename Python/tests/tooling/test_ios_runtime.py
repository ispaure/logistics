"""Portable contracts for the generated iOS testbed; native execution is separate."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build import ios_runtime, ios_testbed
from logistics_build.ios_backend import bundle_digest


class SceneAdapterTests(unittest.TestCase):
    def fixture(self, root):
        app = root / 'iOSTestbed'
        app.mkdir()
        delegate = app / 'AppDelegate.m'
        delegate.write_text('#import "AppDelegate.h"\n@implementation AppDelegate\n@end\n')
        info = app / 'iOSTestbed-Info.plist'
        info.write_bytes(plistlib.dumps({'CFBundleIdentifier': 'org.python.iOSTestbed',
            'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': False, 'UISceneConfigurations': {}}}))
        project = root / 'iOSTestbed.xcodeproj'
        project.mkdir()
        (project / 'project.pbxproj').write_text('IPHONEOS_DEPLOYMENT_TARGET = 13.0;\n')
        return delegate, info

    def test_scene_adapter_preserves_upstream_app_and_changes_only_cloned_ui_lifecycle(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            delegate, info = self.fixture(root)
            original = delegate.read_text()
            tests = root / 'TestbedTests.m'
            tests.write_text('upstream XCTest Python setup remains unchanged')
            result = ios_testbed.modernize(root)
            self.assertTrue(delegate.read_text().startswith(original))
            self.assertIn('IPHONEOS_DEPLOYMENT_TARGET = 15.0;', (root/'iOSTestbed.xcodeproj/project.pbxproj').read_text())
            self.assertIn('initWithWindowScene:', delegate.read_text())
            self.assertIn('makeKeyAndVisible', delegate.read_text())
            config = plistlib.loads(info.read_bytes())['UIApplicationSceneManifest']['UISceneConfigurations']
            self.assertEqual(config['UIWindowSceneSessionRoleApplication'][0]['UISceneDelegateClassName'], ios_testbed.SCENE_CLASS)
            self.assertEqual(tests.read_text(), 'upstream XCTest Python setup remains unchanged')
            again = ios_testbed.modernize(root)
            self.assertEqual(result['after'], again['after'])

    def test_system_log_normalization_preserves_unicode_results_in_both_timezones(self):
        with TemporaryDirectory() as directory:
            raw, output = Path(directory)/'raw.log', Path(directory)/'result.log'
            report = 'LOGISTICS_MOBILE_RESULT={"note":"café 😀"}\n'
            raw.write_text('2026-10-25 16:46:49.1234-0400 iOSTestbed[123:abc] ' + report
                           + '2026-10-25 20:46:49.1234+0000 iOSTestbed[123:abc] ordinary log\n'
                           + 'Other process output stays visible\n')
            ios_testbed.normalize_log(raw, output)
            self.assertEqual(output.read_text(), report+'ordinary log\nOther process output stays visible\n')

    def test_unknown_upstream_scene_policy_fails_without_overwriting_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            delegate, info = self.fixture(root)
            data = plistlib.loads(info.read_bytes())
            data['UIApplicationSceneManifest']['UISceneConfigurations'] = {'unexpected': []}
            info.write_bytes(plistlib.dumps(data))
            before = delegate.read_bytes(), info.read_bytes()
            with self.assertRaisesRegex(ValueError, 'Unexpected upstream scene'):
                ios_testbed.modernize(root)
            self.assertEqual((delegate.read_bytes(), info.read_bytes()), before)


class CoreRuntimeTests(unittest.TestCase):
    def test_prepared_cache_rejects_modified_framework_and_toolchain(self):
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            framework = ios_runtime.framework(cache)
            framework.mkdir(parents=True)
            library = framework / 'Python'
            library.write_text('prepared interpreter')
            pin = ios_runtime.pins()
            saved = dict(revision=pin['revision'], archive_sha256=pin['sha256'],
                         toolchain={'sdk': 'fixture'}, framework_sha256=bundle_digest(framework))
            (cache / 'prepared-manager-ios.json').write_text(json.dumps(saved))
            with patch.object(ios_runtime, 'toolchain', return_value={'sdk': 'fixture'}):
                self.assertEqual(ios_runtime.validate_prepared(cache), saved)
                library.write_text('changed interpreter')
                with self.assertRaisesRegex(ValueError, 'runtime differs'):
                    ios_runtime.validate_prepared(cache)

    def test_cancelled_native_build_records_failure_and_removes_the_owned_simulator(self):
        from mobile_build import tools
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output, lease = root / 'result.json', root / 'lease.json'
            manifest = {'source_sha256': 'a' * 64}
            def stage(project, payload, **kwargs):
                payload.mkdir()
                return manifest
            def command(argv, cwd, timeout):
                if 'clone' in argv:
                    clone = Path(argv[-1])
                    clone.mkdir()
                    (clone / '__main__.py').write_text('def update_test_plan(*args): pass\n')
                if 'build-for-testing' in argv:
                    raise KeyboardInterrupt
            def cleanup(path):
                self.assertEqual(json.loads(path.read_text())['device'], 'owned-fixture-uuid')
                path.unlink()
            with patch.object(ios_runtime, 'source'), \
                    patch.object(ios_runtime, 'validate_prepared', return_value={}), \
                    patch.object(ios_runtime, 'runtime_wheels', return_value=root), \
                    patch.object(tools, 'stage', side_effect=stage), \
                    patch.object(ios_runtime, 'command', side_effect=command), \
                    patch.object(ios_runtime, 'modernize', return_value={}), \
                    patch.object(ios_runtime, 'AppleSimulators') as clients, \
                    patch.object(ios_runtime, 'cleanup', side_effect=cleanup) as remove:
                clients.return_value.create.return_value = 'owned-fixture-uuid'
                with self.assertRaises(KeyboardInterrupt):
                    ios_runtime.test(root, root / 'cache', 'fixture-model', 'fixture-runtime', lease, output)
            data = json.loads(output.read_text())
            self.assertEqual(data['status'], 'cancelled')
            self.assertFalse(data['success'])
            self.assertTrue(data['owned_simulator_removed'])
            self.assertFalse(lease.exists())
            remove.assert_called_once_with(lease)


if __name__ == '__main__':
    unittest.main()
