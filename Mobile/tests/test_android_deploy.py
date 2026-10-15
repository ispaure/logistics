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
            apk.parent.mkdir(parents=True); apk.touch()
            (root / 'pyproject.toml').write_text('[tool.briefcase]\nbundle="io.github.ispaure"\n')
            calls = []
            def run(command, env, **kwargs):
                calls.append(command)
                return 'phone\tdevice\n' if command[-1] == 'devices' else 'Success'
            with patch.object(deploy, 'ROOT', root), patch.object(deploy, 'PROJECT', project), \
                    patch.object(deploy, 'refresh_sources') as refresh, \
                    patch.object(deploy, 'tools_environment', return_value=({}, Path('/sdk/adb'))), \
                    patch.object(deploy, 'run', side_effect=run):
                deploy.deploy()
            refresh.assert_called_once()
            install = next(command for command in calls if 'install' in command)
            self.assertEqual(install[3:5], ['install', '-r'])
            self.assertFalse(any('uninstall' in command for command in calls))
            self.assertIn(deploy.BUNDLE + '/org.beeware.android.MainActivity', calls[-1])
            self.assertIn(['android'], [command[-1:] for command in calls])

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
            self.assertNotIn('--test', run.call_args.args[0])
