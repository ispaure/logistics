"""Embedded Blender activation errors must survive callback and shutdown output."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from features.blender.addons.scanning import run_blender_script


class BlenderActivationTests(unittest.TestCase):
    def test_interactive_activation_preserves_original_exception(self):
        original = ModuleNotFoundError('Missing bundled dependency')

        def enable(module, **kwargs):
            kwargs['handle_error'](original)

        addon_utils = SimpleNamespace(disable=Mock(), enable=enable,
                                      check=Mock(return_value=(True, False)))
        with patch.dict('sys.modules', {'addon_utils': addon_utils}), \
                patch.dict(os.environ, {'LOGISTICS_BLENDER_ADDONS': '["broken"]'}):
            with self.assertRaisesRegex(RuntimeError, 'broken: Missing bundled dependency') as caught:
                runpy.run_module('features.blender.addons.launch_addons', run_name='__main__')
        self.assertIs(caught.exception.__cause__, original)

    def test_background_apply_records_selection_without_importing_gpu_addons(self):
        with TemporaryDirectory() as temp:
            request = Path(temp) / 'request.json'
            request.write_text(json.dumps({'enable': ['existing', 'gpu_addon'], 'disable': ['removed'], 'extensions': ''}))
            existing = SimpleNamespace(module='existing', artist_setting='keep me')
            new = SimpleNamespace(module='')
            addons = Mock()
            addons.get.side_effect = lambda name: existing if name == 'existing' else None
            addons.new.return_value = new
            save = Mock(return_value={'FINISHED'})
            addon_utils = SimpleNamespace(disable=Mock(), enable=Mock(), modules_refresh=Mock())
            original_enable = addon_utils.enable
            config = Path(temp) / 'config'
            config.mkdir()
            (config / 'userpref.blend').write_bytes(b'saved Deluxe preferences')

            def read_preferences():
                # Blender tries to activate saved selections while loading prefs.
                addon_utils.enable('gpu_addon')
                return {'FINISHED'}

            read = Mock(side_effect=read_preferences)
            bpy = SimpleNamespace(context=SimpleNamespace(preferences=SimpleNamespace(addons=addons)),
                                  utils=SimpleNamespace(refresh_script_paths=Mock()),
                                  ops=SimpleNamespace(wm=SimpleNamespace(save_userpref=save, read_userpref=read)))
            with patch.dict('sys.modules', {'addon_utils': addon_utils, 'bpy': bpy}), \
                    patch('sys.argv', ['blender', '--', str(request)]), \
                    patch.dict(os.environ, {'BLENDER_USER_CONFIG': str(Path(temp) / 'config')}):
                runpy.run_module('features.blender.addons.apply_addons', run_name='__main__')
            addon_utils.enable.assert_not_called()
            self.assertIs(addon_utils.enable, original_enable)
            read.assert_called_once()
            addon_utils.disable.assert_called_once_with('removed', default_set=True)
            addons.new.assert_called_once()
            self.assertEqual(new.module, 'gpu_addon')
            self.assertEqual(existing.artist_setting, 'keep me')
            save.assert_called_once()

    def test_failed_preference_reload_restores_activation_and_never_saves_defaults(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'userpref.blend').write_bytes(b'artist preferences')
            request = root / 'request.json'
            request.write_text('{}')
            original_enable = Mock()
            addon_utils = SimpleNamespace(enable=original_enable)
            save = Mock()
            bpy = SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(
                read_userpref=Mock(return_value={'CANCELLED'}), save_userpref=save)))
            with patch.dict('sys.modules', {'addon_utils': addon_utils, 'bpy': bpy}), \
                    patch('sys.argv', ['blender', '--', str(request)]), \
                    patch.dict(os.environ, {'BLENDER_USER_CONFIG': str(root)}):
                with self.assertRaisesRegex(RuntimeError, 'Could not load preset preferences'):
                    runpy.run_module('features.blender.addons.apply_addons', run_name='__main__')
            self.assertIs(addon_utils.enable, original_enable)
            save.assert_not_called()
            self.assertEqual((root / 'userpref.blend').read_bytes(), b'artist preferences')

    def test_failed_process_keeps_complete_log_and_traceback_before_shutdown_noise(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            log_text = ('startup chatter\n' + '\x1b[31mTraceback (most recent call last):\x1b[0m\n'
                        'ModuleNotFoundError: missing_windows_helper\n' + 'Unregistered Blue Hole\n' * 1000)
            process = Mock(returncode=1)
            process.poll.return_value = 1

            def popen(*args, **kwargs):
                self.assertIn('--factory-startup', args[0])
                kwargs['stdout'].write(log_text.encode())
                return process

            with patch('features.blender.addons.scanning.subprocess.Popen', side_effect=popen):
                with self.assertRaisesRegex(ValueError, 'missing_windows_helper') as caught:
                    run_blender_script('blender.exe', {'BLENDER_USER_CONFIG': str(root / 'config')},
                                       'apply_addons.py', 'request.json')
            logs = list(root.glob('blender-addons-error-*.log'))
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].read_text(), log_text)
            self.assertIn(str(logs[0]), str(caught.exception))
            self.assertIn('exit 1', str(caught.exception))
            self.assertNotIn('\x1b', str(caught.exception))
            self.assertLess(len(str(caught.exception)), 7000)
            process.wait.assert_called_once()

    def test_log_save_failure_keeps_actionable_exception(self):
        process = Mock(returncode=1)
        process.poll.return_value = 1

        def popen(*args, **kwargs):
            kwargs['stdout'].write(b'RuntimeError: addon registration failed')
            return process

        with patch('features.blender.addons.scanning.subprocess.Popen', side_effect=popen), \
                patch('features.blender.addons.scanning.NamedTemporaryFile', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(ValueError, 'addon registration failed') as caught:
                run_blender_script('blender.exe', {}, 'apply_addons.py', 'request.json')
        self.assertIn('Could not preserve the full Blender log: disk full', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
