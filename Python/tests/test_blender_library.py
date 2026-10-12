"""Archive metadata, release resolution and preset publication/rollback contracts."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from features.blender.library import AddonLibrary, inspect_package
from features.blender.manager import BlenderManager
from features.blender.releases import load_releases


class BlenderLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manager = BlenderManager(self.root / 'managed')
        self.library = AddonLibrary(self.manager, provided_root=self.root / 'provided')
        self.release = load_releases(platform='windows-x64')[0]
        self.preset = self.manager.create_preset(self.release, 'Art')

    def package(self, filename, version=(1, 0, 0), minimum=(3, 2, 0), body='', module='tool'):
        path = self.root / filename
        with zipfile.ZipFile(path, 'w') as archive:
            info = {'name': 'Artist Tool', 'version': version}
            if minimum:
                info['blender'] = minimum
            archive.writestr(f'{module}/__init__.py', f'bl_info={info!r}\n' + body)
            archive.writestr(f'{module}/helper.py', '# companion module')
        return path

    def test_grouping_and_numeric_latest_compatible_resolution(self):
        self.library.add(self.package('old.zip', (1, 9, 0)))
        self.library.add(self.package('new.zip', (1, 10, 0)))
        self.library.add(self.package('future.zip', (2, 0, 0), (99, 0, 0)))
        entries = self.library.entries()
        self.assertEqual(len(entries), 3)
        self.assertEqual({entry.identity for entry in entries}, {'legacy:tool'})
        self.assertEqual(self.library.resolve('legacy:tool', self.release).version, '1.10.0')
        self.assertEqual(len(list(self.library.root.iterdir())), 1)

    def test_preset_packages_are_isolated_apply_and_follow_duplicate(self):
        other = self.manager.create_preset(self.release, 'Other')
        scoped = self.library.for_preset(self.preset)
        addon = scoped.add(self.package('private.zip'))
        self.assertEqual(addon.source, 'Preset')
        self.assertEqual(len(scoped.entries()), 1)
        self.assertEqual(self.library.for_preset(other).entries(), [])
        self.assertEqual(self.library.entries(shared_only=True), [])
        with patch.object(self.manager, 'executable', return_value=Path('/unused/blender')), patch('features.blender.addons.run_blender_script'):
            self.library.apply(self.release, 'Art', [addon.identity], bluehole={'enabled': False, 'branch': 'main'})
        self.assertTrue((self.preset / 'scripts/addons/tool/__init__.py').exists())
        copied = self.manager.duplicate_preset(self.release, 'Art', 'Copy')
        self.assertEqual(self.library.for_preset(copied).entries()[0].digest, addon.digest)

    def test_legacy_personal_packages_remain_visible_only_where_selected(self):
        import json
        self.library.add(self.package('legacy.zip'))
        other = self.manager.create_preset(self.release, 'Other')
        (self.preset / '.logistics-addons.json').write_text(json.dumps({'selected': ['legacy:tool'], 'installed': {}}))
        self.assertEqual(self.library.for_preset(self.preset).entries()[0].source, 'Personal')
        self.assertEqual(self.library.for_preset(other).entries(), [])

    def test_import_does_not_execute_code_unknown_is_not_auto_resolved_and_conflicts_refused(self):
        path = self.package('unknown.zip', minimum=None, body='raise RuntimeError("must never execute")')
        self.library.add(path)
        self.assertIsNone(self.library.resolve('legacy:tool', self.release))
        self.library.add(path)  # exact duplicate is idempotent
        with self.assertRaisesRegex(ValueError, 'different contents'):
            self.library.add(self.package('different.zip', minimum=None, body='different=True'))

    def test_dated_revisions_keep_same_version_and_choose_latest_compatible(self):
        early = self.package('Tool_1.0.0_2026_10_01.zip', body='revision="first"')
        later = self.package('Tool_1.0.0_2026_10_12.zip', body='revision="second"')
        self.library.add(early)
        imported = self.library.add(later)
        self.assertEqual(imported.published, '2026-10-12')
        self.assertEqual(len(self.library.entries()), 2)
        self.assertEqual(self.library.resolve('legacy:tool', self.release).published, '2026-10-12')
        self.assertEqual(self.library.resolve('legacy:tool', self.release).package_name, later.name)
        self.library.add(self.package('Tool_2.0.0_2026_10_13.zip', version=(2, 0, 0), minimum=(99, 0, 0)))
        self.assertEqual(self.library.resolve('legacy:tool', self.release).version, '1.0.0')

    def test_provided_dated_revisions_and_support_archives_are_discovered_separately(self):
        provided = self.root / 'provided'
        (provided / 'Tool').mkdir(parents=True)
        for day in ('01', '12'):
            path = self.package(f'Tool_1.0.0_2026_10_{day}.zip', body=f'revision={int(day)}')
            import shutil
            shutil.copy2(path, provided / 'Tool' / path.name)
        (provided / '_support').mkdir()
        (provided / '_support/backups.zip').write_bytes(b'not an addon')
        entries = self.library.entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(self.library.resolve('legacy:tool', self.release).published, '2026-10-12')

    def test_metadata_cache_invalidates_modified_zip_and_accepts_legacy_nickname(self):
        from features.blender import library
        path = self.package('named.zip', version=(1, 13, 2, 'DeusEx'))
        with patch.object(library, '_inspect_package', wraps=library._inspect_package) as inspect:
            first = inspect_package(path)
            self.assertEqual(first.version, '1.13.2')
            self.assertEqual(inspect_package(path), first)
            self.assertEqual(inspect.call_count, 1)
            self.package('named.zip', version=(2, 0, 0))
            self.assertEqual(inspect_package(path).version, '2.0.0')
            self.assertEqual(inspect.call_count, 2)

    def test_extension_minimum_exclusive_maximum_and_platform(self):
        path = self.root / 'extension.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('blender_manifest.toml', 'id="tool"\nname="Tool"\nversion="1.0.0"\ntype="add-on"\nblender_version_min="4.2.0"\nblender_version_max="5.0.0"\nplatforms=["windows-x64"]\n')
            archive.writestr('__init__.py', '# extension')
        addon = self.library.add(path)
        from dataclasses import replace
        self.assertTrue(addon.compatible(replace(self.release, version='4.5.1')))
        self.assertFalse(addon.compatible(replace(self.release, version='5.0.0')))
        self.assertFalse(addon.compatible(replace(self.release, version='4.5.1', platform='macos-arm64')))

    def test_unsafe_or_ambiguous_packages_are_rejected(self):
        for extra in ('../outside.py', 'C:/outside.py', 'tool/../outside.py', 'TOOL/__init__.py'):
            path = self.package('unsafe.zip')
            with zipfile.ZipFile(path, 'a') as archive:
                archive.writestr(extra, '# bad')
            with self.assertRaises(ValueError):
                inspect_package(path)
        path = self.package('ambiguous.zip')
        with zipfile.ZipFile(path, 'a') as archive:
            archive.writestr('other/__init__.py', 'bl_info={"version":(1,0)}')
        with self.assertRaises(ValueError):
            inspect_package(path)

    def test_apply_update_remove_and_independent_presets(self):
        self.library.add(self.package('old.zip'))
        other = self.manager.create_preset(self.release, 'Other')
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), patch('features.blender.addons.run_blender_script') as run:
            self.library.apply(self.release, 'Art', ['legacy:tool'])
            run.assert_called_once()
            self.assertTrue((self.preset / 'scripts/addons/tool/helper.py').exists())
            self.assertFalse((other / 'scripts/addons/tool').exists())
            self.library.add(self.package('new.zip', (2, 0, 0), body='updated=True'))
            self.library.apply(self.release, 'Art', ['legacy:tool'])
            self.assertIn('updated=True', (self.preset / 'scripts/addons/tool/__init__.py').read_text())
            self.library.apply(self.release, 'Art', [])
            self.assertFalse((self.preset / 'scripts/addons/tool').exists())
            self.assertEqual(self.library.selection(self.preset)['selected'], [])

    def test_unchanged_launch_preserves_addon_local_files_and_repairs_missing_package(self):
        self.library.add(self.package('tool.zip'))
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), patch('features.blender.addons.run_blender_script'):
            self.library.apply(self.release, 'Art', ['legacy:tool'], bluehole={'enabled': False, 'branch': 'main'})
            folder = self.preset / 'scripts/addons/tool'
            settings = folder / 'artist-settings.json'
            settings.write_text('{"artist":true}')
            helper = folder / 'helper.py'
            helper.write_text('# local edit')
            self.library.apply(self.release, 'Art', ['legacy:tool'], bluehole={'enabled': False, 'branch': 'main'})
            self.assertEqual(settings.read_text(), '{"artist":true}')
            self.assertEqual(helper.read_text(), '# local edit')
            (folder / '__init__.py').unlink()
            self.library.apply(self.release, 'Art', ['legacy:tool'], bluehole={'enabled': False, 'branch': 'main'})
            self.assertTrue((folder / '__init__.py').is_file())
            self.library.apply(self.release, 'Art', [], bluehole={'enabled': False, 'branch': 'main'})
            self.assertFalse(folder.exists())

    def test_failed_enable_restores_files_preferences_and_selection(self):
        self.library.add(self.package('old.zip'))
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), patch('features.blender.addons.run_blender_script'):
            self.library.apply(self.release, 'Art', ['legacy:tool'])
        prefs = self.preset / 'config/userpref.blend'
        prefs.write_bytes(b'original preferences')
        state = (self.preset / '.logistics-addons.json').read_bytes()
        self.library.add(self.package('new.zip', (2, 0, 0), body='updated=True'))
        def fail(*args, **kwargs):
            prefs.write_bytes(b'failed preferences')
            raise ValueError('enable failed')
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), patch('features.blender.addons.run_blender_script', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'enable failed'):
                self.library.apply(self.release, 'Art', ['legacy:tool'])
        self.assertEqual(prefs.read_bytes(), b'original preferences')
        self.assertEqual((self.preset / '.logistics-addons.json').read_bytes(), state)
        self.assertNotIn('updated=True', (self.preset / 'scripts/addons/tool/__init__.py').read_text())

    def test_apply_preserves_executable_permission_for_bundled_helpers(self):
        import os
        path = self.package('engine.zip')
        with zipfile.ZipFile(path, 'a') as archive:
            engine = zipfile.ZipInfo('tool/bin/engine')
            engine.create_system = 3
            engine.external_attr = 0o100755 << 16
            archive.writestr(engine, b'engine fixture')
        self.library.add(path)
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), \
                patch('features.blender.addons.run_blender_script'):
            self.library.apply(self.release, 'Art', ['legacy:tool'])
        installed = self.preset / 'scripts/addons/tool/bin/engine'
        self.assertEqual(installed.read_bytes(), b'engine fixture')
        if os.name != 'nt':
            self.assertEqual(installed.stat().st_mode & 0o777, 0o755)

    def test_bluehole_update_preserves_custom_environments_and_failed_apply_rolls_back(self):
        from features.blender import bluehole
        config = {'enabled': True, 'branch': 'main', 'deluxe': False}
        packages = []
        for index in (1, 2):
            path = self.package(f'bluehole-{index}.zip', module='BlueHole', body=f'revision={index}')
            with zipfile.ZipFile(path, 'a') as archive:
                archive.writestr('BlueHole/envFiles/default/settings.ini', f'default {index}')
                archive.writestr('BlueHole/envFiles/artist/settings.ini', f'example {index}')
            packages.append(inspect_package(path))
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), \
                patch.object(bluehole, 'update', return_value=(packages[0], 'a' * 40)), \
                patch('features.blender.addons.run_blender_script'):
            self.library.apply(self.release, 'Art', [], bluehole=config)
        addon = self.preset / 'scripts/addons/BlueHole'
        (addon / 'envFiles/artist/settings.ini').write_text('artist customization')
        before = (self.preset / '.logistics-addons.json').read_bytes()
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), \
                patch.object(bluehole, 'update', return_value=(packages[1], 'b' * 40)), \
                patch('features.blender.addons.run_blender_script', side_effect=OSError('enable failed')):
            with self.assertRaises(OSError):
                self.library.apply(self.release, 'Art', [], bluehole=config)
        self.assertEqual((self.preset / '.logistics-addons.json').read_bytes(), before)
        self.assertEqual((addon / 'envFiles/default/settings.ini').read_text(), 'default 1')
        self.assertEqual((addon / 'envFiles/artist/settings.ini').read_text(), 'artist customization')
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), \
                patch.object(bluehole, 'update', return_value=(packages[1], 'b' * 40)), \
                patch('features.blender.addons.run_blender_script'):
            self.library.apply(self.release, 'Art', [], bluehole=config)
        self.assertEqual((addon / 'envFiles/default/settings.ini').read_text(), 'default 2')
        self.assertEqual((addon / 'envFiles/artist/settings.ini').read_text(), 'artist customization')
        self.assertEqual(self.library.selection(self.preset)['installed_bluehole']['commit'], 'b' * 40)

    def test_bluehole_disable_reenable_preserves_environments_and_failed_disable_rolls_back(self):
        from features.blender import bluehole
        enabled = {'enabled': True, 'branch': 'main', 'deluxe': False}
        path = self.package('bluehole.zip', module='BlueHole')
        with zipfile.ZipFile(path, 'a') as archive:
            archive.writestr('BlueHole/envFiles/default/settings.ini', 'publisher default')
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), \
                patch.object(bluehole, 'update', return_value=(inspect_package(path), 'a' * 40)), \
                patch('features.blender.addons.run_blender_script') as run:
            self.library.apply(self.release, 'Art', [], bluehole=enabled)
            addon = self.preset / 'scripts/addons/BlueHole'
            artist = addon / 'envFiles/artist/settings.ini'
            artist.parent.mkdir(); artist.write_text('artist preferences')
            disabled = {**enabled, 'enabled': False}
            run.side_effect = OSError('enable failed')
            with self.assertRaises(OSError):
                self.library.apply(self.release, 'Art', [], bluehole=disabled)
            self.assertEqual(artist.read_text(), 'artist preferences')
            self.assertFalse((self.preset / 'addon-data').exists())
            run.side_effect = None
            self.library.apply(self.release, 'Art', [], bluehole=disabled)
            self.assertFalse(addon.exists())
            saved = self.preset / 'addon-data/bluehole/envFiles'
            self.assertEqual((saved / 'artist/settings.ini').read_text(), 'artist preferences')
            self.assertFalse((saved / 'default').exists())
            copied = self.manager.duplicate_preset(self.release, 'Art', 'Copy')
            self.assertTrue((copied / 'addon-data/bluehole/envFiles/artist/settings.ini').exists())
            self.library.apply(self.release, 'Art', [], bluehole=enabled)
            self.assertEqual(artist.read_text(), 'artist preferences')
            self.assertEqual((addon / 'envFiles/default/settings.ini').read_text(), 'publisher default')

    def test_provided_and_personal_layers_choose_latest_with_personal_tie_priority(self):
        import shutil
        provided = self.root / 'provided'
        provided.mkdir()
        shared = provided / 'tool.zip'
        shutil.copyfile(self.package('shared.zip', (2, 0, 0)), shared)
        original = shared.read_bytes()
        library = AddonLibrary(self.manager, provided_root=provided)
        self.assertEqual(library.resolve('legacy:tool', self.release).source, 'Provided')
        library.add(self.package('personal-old.zip', (1, 0, 0)))
        self.assertEqual(library.resolve('legacy:tool', self.release).source, 'Provided')
        library.add(self.package('personal-same.zip', (2, 0, 0), body='personal=True'))
        resolved = library.resolve('legacy:tool', self.release)
        self.assertEqual(resolved.source, 'Personal')
        self.assertEqual(len(library.entries()), 2)
        self.assertEqual(shared.read_bytes(), original)
        self.assertEqual(list(provided.iterdir()), [shared])

    def test_provided_zip_discovery_requires_no_manifest_and_does_not_create_missing_root(self):
        library = AddonLibrary(self.manager, provided_root=self.root / 'absent')
        self.assertEqual(library.entries(), [])
        self.assertFalse(library.provided_root.exists())
        library.add(self.package('artist.zip'))
        self.assertFalse(library.provided_root.exists())
        self.assertEqual(library.entries()[0].source, 'Personal')

    def test_apply_enables_by_display_name_not_identity_or_extension_prefix(self):
        import json
        legacy = self.package('z-module.zip', module='z_module')
        self.library.add(legacy)
        extension = self.root / 'a-extension.zip'
        with zipfile.ZipFile(extension, 'w') as archive:
            archive.writestr('blender_manifest.toml', 'id="a_extension"\nname="Zebra Tool"\nversion="1.0.0"\ntype="add-on"\nblender_version_min="4.2.0"\n')
            archive.writestr('__init__.py', '# extension')
        self.library.add(extension)
        def check(executable, env, script, request, **kwargs):
            value = json.loads(request.read_text())
            self.assertEqual(value['enable'], ['z_module', 'bl_ext.logistics.a_extension'])
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), patch('features.blender.addons.run_blender_script', side_effect=check):
            self.library.apply(self.release, 'Art', ['extension:a_extension', 'legacy:z_module'])

    def test_launch_command_passes_alphabetical_modules_and_controlled_startup(self):
        import json
        state = {'selected': ['legacy:z_module', 'extension:a_extension'], 'installed': {
            'extension:a_extension': {'module': 'bl_ext.logistics.a_extension', 'name': 'Zebra', 'path': 'extensions/logistics/a_extension', 'digest': 'fixture'},
            'legacy:z_module': {'module': 'z_module', 'name': 'Artist', 'path': 'scripts/addons/z_module', 'digest': 'fixture'}}}
        (self.preset / '.logistics-addons.json').write_text(json.dumps(state))
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), patch('features.blender.manager.subprocess.Popen') as popen:
            self.manager.launch(self.release, 'Art')
        args, kwargs = popen.call_args
        self.assertEqual(args[0][:3], [str(Path('/fixture/blender')), '--addons', 'z_module,bl_ext.logistics.a_extension'])
        self.assertEqual(args[0][3], '--python')
        self.assertTrue(args[0][4].endswith('launch_addons.py'))
        self.assertEqual(json.loads(kwargs['env']['LOGISTICS_BLENDER_ADDONS']), ['z_module', 'bl_ext.logistics.a_extension'])

    def test_startup_reenables_in_requested_order_without_removing_saved_preferences(self):
        import json
        import os
        import runpy
        from types import SimpleNamespace
        calls = []
        addon_utils = SimpleNamespace(
            disable=lambda module, **kwargs: calls.append(('disable', module, kwargs)),
            enable=lambda module, **kwargs: calls.append(('enable', module, kwargs)),
            check=lambda module: (True, True))
        with patch.dict('sys.modules', {'addon_utils': addon_utils}), patch.dict(os.environ, {'LOGISTICS_BLENDER_ADDONS': json.dumps(['z_module', 'a_module'])}):
            runpy.run_module('features.blender.launch_addons', run_name='__main__')
        self.assertEqual([(op, module) for op, module, kwargs in calls],
                         [('disable', 'a_module'), ('disable', 'z_module'), ('enable', 'z_module'), ('enable', 'a_module')])
        self.assertTrue(all(not kwargs['default_set'] for op, module, kwargs in calls))

    def test_running_and_unmanaged_addons_are_not_overwritten(self):
        self.library.add(self.package('addon.zip'))
        existing = self.preset / 'scripts/addons/tool'
        existing.mkdir()
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')):
            with self.assertRaisesRegex(ValueError, 'outside the addon library'):
                self.library.apply(self.release, 'Art', ['legacy:tool'])
        with patch.object(self.manager, 'running', return_value=True):
            with self.assertRaisesRegex(ValueError, 'Close the Blender instance'):
                self.library.apply(self.release, 'Art', ['legacy:tool'])


if __name__ == '__main__':
    unittest.main()
