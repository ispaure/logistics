"""Blue Hole branch/commit cache and safe GitHub archive normalization."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zipfile

from features.blender import bluehole
from features.blender.manager import BlenderManager
from features.blender.releases import load_releases


class BlueHoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = BlenderManager(Path(self.temp.name))
        self.release = load_releases(platform='windows-x64')[0]

    def download(self, commit, destination, cancelled):
        with zipfile.ZipFile(destination, 'w') as archive:
            archive.writestr(f'BlueHole-{commit}/__init__.py', 'bl_info={"name":"Blue Hole","version":(1,0,0),"blender":(4,2,0)}\n')
            archive.writestr(f'BlueHole-{commit}/Lib/module.py', commit)

    def test_rechecks_head_but_downloads_same_commit_only_once(self):
        with patch.object(bluehole, 'branch_commit', return_value='a' * 40) as head, patch.object(bluehole, 'download', side_effect=self.download) as download:
            first, commit = bluehole.update(self.manager, self.release, 'main')
            second, _ = bluehole.update(self.manager, self.release, 'main')
        self.assertEqual(head.call_count, 2)
        self.assertEqual(download.call_count, 1)
        self.assertEqual(first.identity, bluehole.IDENTITY)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(commit, 'a' * 40)
        with zipfile.ZipFile(first.package) as archive:
            self.assertIn('BlueHole/Lib/module.py', archive.namelist())

    def test_new_commits_with_same_addon_version_get_independent_cache_entries(self):
        with patch.object(bluehole, 'branch_commit', side_effect=['a' * 40, 'b' * 40]), patch.object(bluehole, 'download', side_effect=self.download):
            first, _ = bluehole.update(self.manager, self.release, 'beta')
            second, _ = bluehole.update(self.manager, self.release, 'beta')
        self.assertEqual(first.version, second.version)
        self.assertNotEqual(first.package, second.package)
        self.assertNotEqual(first.digest, second.digest)
        self.assertTrue(first.package.exists())

    def test_incompatible_or_unsafe_downloads_are_not_applied(self):
        def unsafe(commit, path, cancelled):
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('../escape.py', 'bad')
        with patch.object(bluehole, 'branch_commit', return_value='a' * 40), patch.object(bluehole, 'download', side_effect=unsafe):
            with self.assertRaises(ValueError):
                bluehole.update(self.manager, self.release, 'alpha')
        self.assertFalse((self.manager.root / 'escape.py').exists())

    def test_environment_preservation_replaces_only_default_and_keeps_custom_exactly(self):
        previous = self.manager.root / 'previous'; current = self.manager.root / 'current'
        for root in (previous, current):
            (root / 'envFiles/default').mkdir(parents=True)
            (root / 'envFiles/artist').mkdir()
        (previous / 'envFiles/default/old.ini').write_text('old default')
        (previous / 'envFiles/artist/preferences.ini').write_text('artist settings')
        (current / 'envFiles/default/new.ini').write_text('new default')
        (current / 'envFiles/artist/preferences.ini').write_text('publisher example')
        (current / 'envFiles/artist/extra.ini').write_text('must not be merged')
        bluehole.preserve_environments(previous, current)
        self.assertEqual((current / 'envFiles/artist/preferences.ini').read_text(), 'artist settings')
        self.assertFalse((current / 'envFiles/artist/extra.ini').exists())
        self.assertTrue((current / 'envFiles/default/new.ini').exists())
        self.assertFalse((current / 'envFiles/default/old.ini').exists())
        self.assertTrue((previous / 'envFiles/default/old.ini').exists())

    def test_deluxe_stamps_once_preserves_backup_and_rejects_symlink_escape(self):
        from dataclasses import replace
        from features.blender.library import inspect_package
        root = self.manager.create_preset(self.release, 'Deluxe')
        prefs = root / 'config/userpref.blend'
        prefs.write_bytes(b'original artist preferences')
        package = self.manager.root / 'deluxe.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('BlueHole/__init__.py', 'bl_info={"name":"Blue Hole","version":(1,0,0),"blender":(4,2,0)}')
            archive.writestr('BlueHole/overlays/deluxe/payload/userpref.blend', b'Deluxe payload')
            archive.writestr('BlueHole/overlays/deluxe/payload/keyconfig/BH_Keymaps.py', '# keymaps')
        addon = replace(inspect_package(package), source='GitHub')
        stamp = bluehole.apply_deluxe(addon, root, None)
        self.assertEqual(prefs.read_bytes(), b'Deluxe payload')
        self.assertEqual((root / 'config/userpref.before-bluehole-deluxe.blend').read_bytes(), b'original artist preferences')
        prefs.write_bytes(b'customized after stamp')
        self.assertEqual(bluehole.apply_deluxe(addon, root, stamp), stamp)
        self.assertEqual(prefs.read_bytes(), b'customized after stamp')
        target = root / 'scripts/presets/keyconfig/BH_Keymaps.py'
        target.unlink()
        outside = self.manager.root / 'outside.py'
        outside.write_text('outside')
        target.symlink_to(outside)
        with self.assertRaises(ValueError):
            bluehole.apply_deluxe(addon, root, None)
        self.assertEqual(outside.read_text(), 'outside')

    def test_invalid_branch_is_rejected_before_network(self):
        with self.assertRaises(ValueError):
            bluehole.branch_commit('../unsafe')
        with self.assertRaises(ValueError):
            bluehole.validate({'enabled': True, 'branch': 'development'})


if __name__ == '__main__':
    unittest.main()
