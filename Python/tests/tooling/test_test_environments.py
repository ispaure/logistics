"""Shared environment settings drive both local selectors and hosted jobs."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build.test_environments import DEFAULTS, android_image, load, outputs, runtime_id, save

ROOT = Path(__file__).resolve().parents[3]


class TestEnvironmentTests(unittest.TestCase):
    def test_save_is_tracked_configuration_and_drives_both_android_profiles(self):
        with TemporaryDirectory() as folder:
            save(folder, {'android_api': '37', 'android_model': 'pixel_9_pro'})
            values = load(folder)
            self.assertEqual(android_image(values), 'system-images;android-37;google_apis;arm64-v8a')
            hosted = json.loads(outputs(values)['android_device'])
            self.assertEqual(hosted['system_image'], 'system-images;android-37;google_apis;x86_64')
            self.assertEqual(hosted['device_type'], 'pixel_9_pro')
            self.assertEqual(runtime_id(values, 'duo'), 'com.apple.CoreSimulator.SimRuntime.iOS-27-1')

    def test_invalid_values_do_not_replace_valid_settings(self):
        with TemporaryDirectory() as folder:
            save(folder, {})
            before = (Path(folder) / 'test-environments.json').read_bytes()
            for changes in ({'macos_runner': 'macos-latest'}, {'fedora_image': 'ubuntu:24.04'},
                            {'ios_sdk': '27\nINJECT=true'}, {'android_api': 'bad'}, {'unknown': 'value'}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    save(folder, changes)
                self.assertEqual((Path(folder) / 'test-environments.json').read_bytes(), before)

    def test_project_settings_save_shared_fields_outside_private_profile(self):
        from mobile_build.deployment import manager_settings
        from mobile_build.deployment.settings_help import describe_settings
        with TemporaryDirectory() as folder:
            root = Path(folder); mobile = root / 'mobile_build'; mobile.mkdir()
            for name in ('testflight-distribution.json', 'firebase-distribution.json'):
                (mobile / name).write_bytes((ROOT / 'mobile_build' / name).read_bytes())
            profile = root / 'private.json'
            wheel = 'C:/Build tools/pyside6_webengine-6.12.0.140-1-cp310-abi3-win_arm64.whl'
            digest = 'a' * 64
            with patch.dict('os.environ', {'LOGISTICS_MANAGER_PROFILE': str(profile)}):
                manager_settings.save(mobile, {'testing.macos_runner': 'macos-26', 'testing.android_api': '37',
                                               'testing.windows_runner': 'windows-2025',
                                               'vm.windows_python_architecture': 'arm64',
                                               'vm.windows_python_version': '3.12.11',
                                               'vm.windows_webengine_wheel': wheel,
                                               'vm.windows_webengine_sha256': digest})
                values, sources = manager_settings.settings(mobile)
            self.assertEqual(values['testing.android_api'], '37')
            self.assertEqual(values['testing.windows_runner'], 'windows-2025')
            self.assertIn('android-37', values['android.image'])
            self.assertIn('tracked', sources['testing.macos_runner'])
            self.assertEqual(values['vm.windows_python_architecture'], 'arm64')
            self.assertEqual(values['vm.windows_python_version'], '3.12.11')
            self.assertEqual(values['vm.windows_webengine_wheel'], wheel)
            self.assertEqual(values['vm.windows_webengine_sha256'], digest)
            self.assertEqual(load(root)['python_version'], DEFAULTS['python_version'])
            self.assertFalse(any(key.startswith('testing.') for key in json.loads(profile.read_text())))
            rows = describe_settings({'testing.' + key: dict(value=value) for key, value in DEFAULTS.items()})
            self.assertTrue(all('test-environments.json' in row['description'] for row in rows.values()))

    def test_windows_vm_python_defaults_and_overrides(self):
        from logistics_build.test_environments import windows_python

        self.assertEqual(windows_python(DEFAULTS), DEFAULTS['python_version'])
        self.assertEqual(windows_python(DEFAULTS, 'arm64'), '3.12.11')
        self.assertEqual(windows_python(DEFAULTS, 'x86_64', '3.12.11'), '3.12.11')
        for architecture, version in (('arm64', '3.12.2'), ('x86_64', '3.12'), ('x86', '')):
            with self.subTest(architecture=architecture, version=version), self.assertRaises(ValueError):
                windows_python(DEFAULTS, architecture, version)

    def test_windows_webengine_requires_an_absolute_arm64_wheel_and_digest(self):
        from logistics_build.test_environments import windows_webengine

        wheel = 'C:/Build tools/pyside6_webengine-6.12.0.140-1-cp310-abi3-win_arm64.whl'
        digest = 'a' * 64
        self.assertIsNone(windows_webengine('', ''))
        self.assertEqual(windows_webengine(wheel, digest)['sha256'], digest)
        for path, sha in ((wheel, ''), ('', digest), (wheel[3:], digest),
                          (wheel.replace('arm64', 'amd64'), digest)):
            with self.subTest(path=path, sha=sha), self.assertRaises(ValueError):
                windows_webengine(path, sha)

    def test_windows_arm64_requires_webengine_for_full_desktop_validation(self):
        from logistics_build import local_desktop

        with (patch.object(local_desktop.sys, 'platform', 'win32'),
              patch.object(local_desktop.sysconfig, 'get_platform', return_value='win-arm64'),
              patch.dict(local_desktop.sys.modules, {'PySide6.QtWebEngineCore': None})):
            with self.assertRaisesRegex(RuntimeError, 'missing Qt WebEngine'):
                local_desktop.verify_qt()
            with patch.object(local_desktop.sys, 'stderr') as stderr:
                local_desktop.verify_qt(focused=True)
                stderr.write.assert_any_call('The pinned PySide6 wheel is missing Qt WebEngine on '
                                             'Windows ARM64. Tests that require it can still fail.')

    def test_matrix_has_one_entry_per_desktop_and_explicit_runners(self):
        values = load(ROOT)
        self.assertEqual([r['target'] for r in json.loads(outputs(values)['desktop_matrix'])['include']], ['macos', 'windows'])
        self.assertEqual(len(json.loads(outputs(values, 'windows')['desktop_matrix'])['include']), 1)
        workflows = ROOT / '.github/workflows'
        for name in ('archive-platform-checks.yml', 'mobile-build.yml', 'mobile-runtime.yml'):
            self.assertIn('uses: ./.github/workflows/test-environment.yml', (workflows / name).read_text())
        self.assertEqual((workflows / 'archive-platform-checks.yml').read_text().count('docker run --rm'), 1)

    def test_host_preflight_rejects_versions_and_windows_server(self):
        from logistics_build.test_environments import verify_host
        values = dict(DEFAULTS)
        verify_host(values, system='Darwin', python='3.12.2', os_version='26.6.2')
        verify_host(values, system='Windows', python='3.12.2', os_version='10.0.26200', windows_client=True)
        verify_host(values, system='Linux', python='3.12.2', os_version='ID=fedora\nVERSION_ID="44"')
        for overrides in (dict(system='Darwin', os_version='15.0'), dict(system='Darwin', os_version='26.0', python='3.12.3'),
                          dict(system='Windows', os_version='10.0.26200', windows_client=False),
                          dict(system='Linux', os_version='ID=ubuntu\nVERSION_ID="24.04"')):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                verify_host(values, **dict(dict(python='3.12.2'), **overrides))

    def test_hosted_windows_uses_native_x64_and_its_configured_os(self):
        from logistics_build.test_environments import verify_host

        values = dict(DEFAULTS)
        matrix = json.loads(outputs(values, 'windows')['desktop_matrix'])
        self.assertEqual(matrix['include'], [{'target': 'windows', 'runner': 'windows-2025'}])
        server = dict(system='Windows', python=values['python_version'], os_version='10.0.26100',
                      windows_client=False, hosted=True, runner_arch='X64', interpreter_platform='win-amd64')
        self.assertFalse(verify_host(values, **server)['windows_client'])
        for changes in ({'runner_arch': 'ARM64'}, {'interpreter_platform': 'win-arm64'},
                        {'windows_client': True}, {'os_version': '10.0.20348'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                verify_host(values, **dict(server, **changes))
        client = dict(server, windows_client=True, os_version='10.0.26200')
        self.assertTrue(verify_host(dict(values, windows_runner='windows-client-x64'), **client)['windows_client'])

    def test_runtime_android_matches_shared_api_and_unknown_recipe_stops(self):
        from logistics_build.test_environments import configure_android_testbed
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'build.gradle.kts'
            path.write_text('targetSdk = 35\ncreate("maxVersion") {\n systemImageSource = "aosp_atd"\n}')
            configure_android_testbed(path, dict(DEFAULTS, android_api='36'))
            self.assertIn('targetSdk = 36', path.read_text())
            self.assertIn('systemImageSource = "google_apis"', path.read_text())
            path.write_text('upstream recipe changed')
            with self.assertRaises(ValueError):
                configure_android_testbed(path, DEFAULTS)
            self.assertEqual(path.read_text(), 'upstream recipe changed')

    def test_project_adapter_bootstrap_binds_its_own_shared_dependency(self):
        import os
        import subprocess
        import sys
        environment = {key: value for key, value in os.environ.items() if key not in {'PYTHONPATH', 'PYTHONHOME'}}
        code = ('import logistics_build; import build_manager; import commonUtils; '
                'from pathlib import Path; import commonUtils.testing.stages; '
                'assert Path(commonUtils.__file__).parent == Path.cwd()/"Python/commonUtils", commonUtils.__file__')
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=environment,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
