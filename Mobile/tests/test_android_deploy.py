from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from Mobile import android_deploy as deploy


class AndroidDeployTests(unittest.TestCase):
    def test_device_selection_skips_unauthorized_and_requires_explicit_multi_choice(self):
        output = 'List of devices attached\nblocked\tunauthorized\nphone\tdevice\nold\toffline\n'
        self.assertEqual(deploy.select_device(output), 'phone')
        with self.assertRaises(ValueError):
            deploy.select_device(output, 'blocked')
        with self.assertRaises(ValueError):
            deploy.select_device('')
        self.assertEqual(deploy.select_device(output + 'emulator\tdevice\n', ask=lambda prompt: '2'), 'emulator')

    def test_managed_sdk_and_jdk_are_available_to_native_bridge(self):
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / 'tools/android_sdk/platform-tools').mkdir(parents=True)
            (cache / 'tools/android_sdk/platform-tools/adb').touch()
            (cache / 'tools/java17/Contents/Home/bin').mkdir(parents=True)
            (cache / 'tools/java17/Contents/Home/bin/javac').touch()
            with patch.object(deploy.platform, 'system', return_value='Darwin'):
                env, adb = deploy.tools_environment(dict(BRIEFCASE_HOME=directory))
            self.assertEqual(env['ANDROID_HOME'], str(cache / 'tools/android_sdk'))
            self.assertEqual(env['JAVA_HOME'], str(cache / 'tools/java17/Contents/Home'))
            self.assertEqual(adb.name, 'adb')

    def test_update_installs_in_place_and_launches_normal_app(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'project'
            apk = project / 'app/build/outputs/apk/debug/app-debug.apk'
            apk.parent.mkdir(parents=True)
            apk.touch()
            (root / 'pyproject.toml').write_text('[tool.briefcase]\nbundle="io.github.ispaure"\nversion="0.1.9"\n')
            calls = []
            def run(command, env, **kwargs):
                calls.append(command)
                return 'phone\tdevice\n' if command[-1] == 'devices' else 'Success'
            with patch.object(deploy, 'ROOT', root), patch.object(deploy, 'PROJECT', project), \
                    patch.object(deploy, 'refresh_sources') as refresh, \
                    patch.object(deploy, 'deployment_version', return_value=42), \
                    patch.object(deploy, 'compatible_apk', side_effect=lambda a, e, s, p: p), \
                    patch.object(deploy, 'tools_environment', return_value=({}, Path('/sdk/adb'))), \
                    patch.object(deploy, 'run', side_effect=run):
                deploy.deploy()
            refresh.assert_called_once()
            install = next(command for command in calls if 'install' in command)
            self.assertEqual(install[3:5], ['install', '-r'])
            self.assertFalse(any('uninstall' in command for command in calls))
            self.assertIn(deploy.BUNDLE + '/org.beeware.android.MainActivity', calls[-1])
            self.assertIn(['android'], [command[-1:] for command in calls])
            build = next(command for command in calls if ':app:assembleDebug' in command)
            self.assertEqual(build[build.index('-p') + 1], str(project))
            version = Path(build[build.index('-I') + 1]).read_text()
            self.assertIn('versionCode = 42', version)
            self.assertIn('versionName = "0.1.9"', version)

    def test_build_number_exceeds_installed_beta_and_previous_local_builds(self):
        import json
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.android-beta').mkdir()
            (root / '.android-beta/build.json').write_text(json.dumps(dict(last_build=400)))
            with patch.object(deploy, 'ROOT', root), \
                    patch.object(deploy, 'installed_version', side_effect=[500, 200, 500, 200]):
                self.assertEqual(deploy.deployment_version('/adb', {}, ['boox', 'phone'], 100), 501)
                self.assertEqual(deploy.deployment_version('/adb', {}, ['boox', 'phone'], 100), 502)

    def test_beta_installed_app_is_resigned_with_its_existing_key_before_install(self):
        import hashlib
        import json
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / '.android-beta'
            private.mkdir()
            (private / 'signing.p12').touch()
            (private / 'signing.json').write_text(json.dumps(dict(password='fixture-only')))
            certificate = hashlib.sha256(b'public certificate').hexdigest()
            calls = []
            def run(command, env):
                calls.append(command)
                return 'package:/data/app/logistics/base.apk\n' if 'path' in command else ''
            with patch.object(deploy, 'ROOT', root), patch.object(deploy, 'build_tools', return_value=Path('/tools')), \
                    patch.object(deploy, 'run', side_effect=run), \
                    patch.object(deploy, 'apk_certificate', side_effect=[certificate, 'debug', certificate]), \
                    patch.object(deploy.subprocess, 'check_output', return_value=b'public certificate'):
                result = deploy.compatible_apk('/adb', {'JAVA_HOME': '/jdk'}, 'boox', Path('/debug.apk'))
            self.assertEqual(result, root / 'build/compatible-boox.apk')
            sign = next(command for command in calls if 'sign' in command)
            self.assertIn(str(private / 'signing.p12'), sign)
            self.assertIn('env:LOGISTICS_BETA_STORE_PASSWORD', sign)
            self.assertNotIn('fixture-only', str(calls))
            self.assertFalse(any('install' in command or 'uninstall' in command for command in calls))

    def test_unknown_installed_signer_stops_before_install_without_replacing_key(self):
        with TemporaryDirectory() as directory, patch.object(deploy, 'ROOT', Path(directory)), \
                patch.object(deploy, 'build_tools', return_value=Path('/tools')), \
                patch.object(deploy, 'run', return_value='package:/data/app/logistics/base.apk\n') as run, \
                patch.object(deploy, 'apk_certificate', side_effect=['unknown', 'debug']):
            with self.assertRaisesRegex(ValueError, 'Restore Mobile/.android-beta'):
                deploy.install_apk('/adb', {}, 'boox', Path('/debug.apk'))
            self.assertFalse(any('install' in call.args[0] or 'uninstall' in call.args[0] for call in run.call_args_list))

    def test_staging_uses_current_sources_and_normal_briefcase_update(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'project').mkdir()
            (root / 'project/gradlew').touch()
            (root / 'payload').mkdir()
            def stage(repo, destination, **kwargs):
                self.assertTrue(kwargs['allow_dirty'])
                destination.mkdir()
                (destination / 'current-source').touch()
            with patch.object(deploy, 'ROOT', root), patch.object(deploy, 'PROJECT', root / 'project'), \
                    patch.object(deploy, 'stage', side_effect=stage) as staged, patch.object(deploy, 'run') as run:
                deploy.refresh_sources({})
            staged.assert_called_once()
            self.assertTrue((root / 'payload/current-source').exists())
            self.assertIn('update', run.call_args.args[0])
            self.assertIn('--update-requirements', run.call_args.args[0])
            self.assertNotIn('--test', run.call_args.args[0])

    def test_wireless_discovery_uses_connect_services_and_never_pairs(self):
        calls = []
        def run(command, env):
            calls.append(command)
            return ('List of discovered mdns services\n'
                    'paired\t_adb-tls-connect._tcp\t192.168.2.10:35001\n'
                    'pairing\t_adb-tls-pairing._tcp\t192.168.2.10:35002\n')
        with patch.object(deploy, 'run', side_effect=run):
            deploy.discover_wireless('/sdk/adb', {})
        self.assertEqual(calls, [['/sdk/adb', 'mdns', 'services'],
                                 ['/sdk/adb', 'connect', '192.168.2.10:35001']])

    def test_local_sdk_settings_fill_missing_environment_without_overriding_it(self):
        import json
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.tools').mkdir()
            (root / '.tools/android-sdk.json').write_text(json.dumps(dict(ANDROID_HOME=directory)))
            with patch.object(deploy, 'ROOT', root), patch.dict(deploy.os.environ, {}, clear=True):
                self.assertEqual(deploy.deployment_environment()['ANDROID_HOME'], directory)
            with patch.object(deploy, 'ROOT', root), patch.dict(deploy.os.environ, {'ANDROID_HOME': '/explicit'}, clear=True):
                self.assertEqual(deploy.deployment_environment()['ANDROID_HOME'], '/explicit')
