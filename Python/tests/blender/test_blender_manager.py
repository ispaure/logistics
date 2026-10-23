"""Blender package/preset boundaries, verified downloads and addon inventory."""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import plistlib
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import zipfile

from commonUtils.runtime.operations import OperationCancelled
from features.blender.addons import scanning as addons
from features.blender.installation.install import (MARKER, extract_dmg, extract_tar, install_release,
                                     installed, installation_lock, remove_installation)
from features.blender.presets.manager import BlenderManager, preset_name
from features.blender.installation.releases import Release, load_releases


def release(version='4.5.1', format='zip', digest='0' * 64):
    return Release(version, 'windows-x64', 'https://download.blender.org/test.zip', digest,
                   format, 'blender-package', 'blender.exe')


class BlenderManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manager = BlenderManager(self.root)
        self.release = release()

    def _mark_installed(self, release=None):
        release = release or self.release
        destination = self.manager.installation(release)
        destination.mkdir(parents=True)
        (destination / release.executable).write_bytes(b'executable')
        (destination / MARKER).write_text(json.dumps({'version': release.version, 'platform': release.platform,
                                                     'sha256': release.sha256, 'executable': release.executable}))
        return destination

    def _zip(self, members=None):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            for name, content in (members or {'blender-package/blender.exe': b'blender',
                                            'blender-package/scripts/startup.py': b'script'}).items():
                archive.writestr(name, content)
        return out.getvalue()

    def _response(self, payload):
        response = io.BytesIO(payload)
        response.headers = {'Content-Length': str(len(payload))}
        response.geturl = lambda: self.release.url
        return response

    def test_catalog_has_exact_releases_and_platform_specific_hashes(self):
        hashes = set()
        for platform in ('windows-x64', 'windows-arm64', 'linux-x64', 'macos-arm64'):
            builds = load_releases(platform=platform)
            self.assertEqual([build.version for build in builds], ['5.2.2', '4.5.1'])
            hashes.update(build.sha256 for build in builds)
        self.assertEqual(len(hashes), 8)
        self.assertEqual([build.version for build in load_releases(platform='macos-x64')], ['4.5.1'])
        self.assertEqual(load_releases(platform='linux-arm64'), [])

    def test_release_rejects_insecure_urls_bad_hashes_and_escaping_paths(self):
        for values in ({'url': 'http://example.test/blender.zip'}, {'sha256': 'bad'},
                       {'bundle': '../escape'}, {'executable': 'C:/blender.exe'},
                       {'executable': '\\outside\\blender.exe'}, {'version': 'latest'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                replace(self.release, **values)

    def test_verifies_archive_installs_whole_bundle_and_cleans_staging(self):
        payload = self._zip()
        build = replace(self.release, sha256=hashlib.sha256(payload).hexdigest())
        destination = self.manager.installation(build)
        with patch('commonUtils.runtime.streams.downloads.urlopen', return_value=self._response(payload)):
            install_release(build, destination)
        self.assertTrue(installed(build, destination))
        self.assertEqual((destination / 'scripts/startup.py').read_bytes(), b'script')
        self.assertEqual(list(destination.parent.iterdir()), [destination])
        with patch('commonUtils.runtime.streams.downloads.urlopen') as download:
            install_release(build, destination)
            download.assert_not_called()

    def test_install_refuses_destination_created_during_extraction(self):
        from features.blender.installation import install
        payload = self._zip()
        build = replace(self.release, sha256=hashlib.sha256(payload).hexdigest())
        destination = self.manager.installation(build)
        extract = install.extract_zip
        def extract_and_race(*args):
            extract(*args)
            destination.mkdir()
        with patch('commonUtils.runtime.streams.downloads.urlopen', return_value=self._response(payload)), \
                patch.object(install, 'extract_zip', side_effect=extract_and_race):
            with self.assertRaises(FileExistsError):
                install_release(build, destination)
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(list(destination.parent.iterdir()), [destination])

    def test_preset_publication_refuses_a_racing_empty_directory(self):
        original = self.manager.create_preset(self.release, 'Original')
        (original / 'config/userpref.blend').write_bytes(b'preferences')
        exists = Path.exists
        for operation in ('duplicate_preset', 'rename_preset'):
            with self.subTest(operation=operation):
                destination = self.manager.preset(self.release, operation)
                def exists_and_race(candidate):
                    present = exists(candidate)
                    if candidate == destination and not present:
                        destination.mkdir()
                    return present
                with patch.object(Path, 'exists', exists_and_race):
                    with self.assertRaises(FileExistsError):
                        getattr(self.manager, operation)(self.release, 'Original', operation)
                self.assertEqual(list(destination.iterdir()), [])
                self.assertEqual((original / 'config/userpref.blend').read_bytes(), b'preferences')
                self.assertFalse(any(p.name.startswith('.preset-') for p in destination.parent.iterdir()))

    def test_hash_failure_never_publishes_or_leaves_archive(self):
        destination = self.manager.installation(self.release)
        with patch('commonUtils.runtime.streams.downloads.urlopen', return_value=self._response(self._zip())):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                install_release(self.release, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list(destination.parent.iterdir()), [])

    def test_cancel_during_download_cleans_staging(self):
        destination = self.manager.installation(self.release)
        state = {'cancelled': False}
        with patch('commonUtils.runtime.streams.downloads.urlopen', return_value=self._response(self._zip())):
            with self.assertRaises(OperationCancelled):
                install_release(self.release, destination,
                                report=lambda *args: state.update(cancelled=True),
                                cancelled=lambda: state['cancelled'])
        self.assertEqual(list(destination.parent.iterdir()), [])

    def test_zip_traversal_is_rejected_without_publication(self):
        payload = self._zip({'../escape': b'bad', 'blender-package/blender.exe': b'blender'})
        build = replace(self.release, sha256=hashlib.sha256(payload).hexdigest())
        destination = self.manager.installation(build)
        with patch('commonUtils.runtime.streams.downloads.urlopen', return_value=self._response(payload)):
            with self.assertRaises(ValueError):
                install_release(build, destination)
        self.assertFalse(destination.exists())
        self.assertFalse((destination.parent / 'escape').exists())

    def test_existing_unknown_installation_is_preserved(self):
        destination = self.manager.installation(self.release)
        destination.mkdir(parents=True)
        (destination / 'keep').write_text('mine')
        with self.assertRaises(ValueError):
            install_release(self.release, destination)
        self.assertEqual((destination / 'keep').read_text(), 'mine')
        with self.assertRaises(ValueError):
            remove_installation(self.release, destination)

    def test_install_lock_refuses_concurrent_operation(self):
        destination = self.manager.installation(self.release)
        with installation_lock(destination), self.assertRaisesRegex(ValueError, 'Another operation'):
            install_release(self.release, destination)

    def test_tar_retains_internal_links_and_rejects_external_links(self):
        package = self.root / 'package.tar.xz'
        with tarfile.open(package, 'w:xz') as archive:
            info = tarfile.TarInfo('bundle/blender')
            info.size, info.mode = 3, 0o755
            archive.addfile(info, io.BytesIO(b'bin'))
            link = tarfile.TarInfo('bundle/alias')
            link.type, link.linkname = tarfile.SYMTYPE, 'blender'
            archive.addfile(link)
        output = self.root / 'extracted'
        output.mkdir()
        extract_tar(package, output, lambda: False)
        self.assertTrue((output / 'bundle/alias').is_symlink())
        self.assertEqual((output / 'bundle/alias').read_bytes(), b'bin')
        with tarfile.open(package, 'w:xz') as archive:
            link.linkname = '../../outside'
            archive.addfile(link)
        with self.assertRaises(tarfile.FilterError):
            extract_tar(package, output, lambda: False)

    def test_dmg_detaches_on_copy_error_and_uses_metadata_preserving_copy(self):
        mount = self.root / 'mounted'
        (mount / 'Blender.app').mkdir(parents=True)
        attach = Mock(stdout=plistlib.dumps({'system-entities': [{'mount-point': str(mount)}]}))
        with patch('features.blender.installation.install.subprocess.run', side_effect=[attach,
                   subprocess.CalledProcessError(1, 'ditto'), Mock()]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                extract_dmg(self.root / 'test.dmg', self.root / 'output', lambda: False)
        self.assertEqual(run.call_args_list[1].args[0][0], 'ditto')
        self.assertEqual(run.call_args_list[2].args[0], ['hdiutil', 'detach', str(mount)])

    def test_preset_create_copy_rename_and_delete_preserve_original(self):
        original = self.manager.create_preset(self.release, 'Default')
        (original / 'config/userpref.blend').write_bytes(b'prefs')
        duplicate = self.manager.duplicate_preset(self.release, 'Default', 'Studio')
        self.assertEqual((duplicate / 'config/userpref.blend').read_bytes(), b'prefs')
        renamed = self.manager.rename_preset(self.release, 'Studio', 'Work')
        self.assertTrue(renamed.exists())
        self.manager.remove_preset(self.release, 'Work')
        self.assertEqual(self.manager.presets(self.release), ['Default'])
        self.assertTrue((original / 'scripts/addons').is_dir())

    def test_copy_to_another_version_is_independent(self):
        source = self.manager.create_preset(self.release, 'Default')
        (source / 'config/userpref.blend').write_bytes(b'old')
        target = release('5.2.2')
        copy = self.manager.duplicate_preset(self.release, 'Default', 'Default', target_release=target)
        (copy / 'config/userpref.blend').write_bytes(b'new')
        self.assertEqual((source / 'config/userpref.blend').read_bytes(), b'old')

    def test_preset_names_and_symlinked_versions_cannot_escape(self):
        for name in ('../escape', 'folder/name', 'a\\b', 'CON', 'aux.txt', '.hidden', '', 'bad.'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                preset_name(name)
        self.manager.preferences.mkdir(parents=True)
        (self.manager.preferences / self.release.version).symlink_to(self.root / 'outside', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.manager.create_preset(self.release, 'Default')

    def test_duplicate_cancel_leaves_no_partial_preset(self):
        self.manager.create_preset(self.release, 'Default')
        with self.assertRaises(OperationCancelled):
            self.manager.duplicate_preset(self.release, 'Default', 'Cancelled', cancelled=lambda: True)
        self.assertEqual(self.manager.presets(self.release), ['Default'])

    def test_launch_environment_overrides_only_child_and_all_resource_paths(self):
        self.manager.create_preset(self.release, 'Default')
        destination = self._mark_installed()
        with patch.dict('os.environ', {'BLENDER_USER_CONFIG': '/external/preferences'}):
            with patch('features.blender.presets.manager.subprocess.Popen') as popen:
                self.manager.launch(self.release, 'Default')
            kwargs = popen.call_args.kwargs
            self.assertEqual(popen.call_args.args[0], [str(destination / 'blender.exe')])
            log = Path(kwargs['stdout'].name)
            self.assertEqual(log.parent, self.manager.preset(self.release, 'Default'))
            self.assertTrue(log.is_file())
            self.assertIs(kwargs['stdout'], kwargs['stderr'])
            for field in ('CONFIG', 'SCRIPTS', 'EXTENSIONS', 'DATAFILES', 'RESOURCES'):
                self.assertTrue(Path(kwargs['env'][f'BLENDER_USER_{field}']).is_relative_to(self.manager.preferences))
            import os
            self.assertEqual(os.environ['BLENDER_USER_CONFIG'], '/external/preferences')

    def test_running_blender_blocks_installation_and_preset_deletion(self):
        process = Mock()
        process.poll.return_value = None
        self.manager.processes = [(process, self.release.version, 'Default')]
        with self.assertRaisesRegex(ValueError, 'Close the Blender'):
            self.manager.remove(self.release)
        with self.assertRaises(ValueError):
            self.manager.remove_preset(self.release, 'Default')

    def test_removing_installation_keeps_presets(self):
        self.manager.create_preset(self.release, 'Default')
        self._mark_installed()
        self.manager.remove(self.release)
        self.assertFalse(self.manager.installation(self.release).exists())
        self.assertEqual(self.manager.presets(self.release), ['Default'])

    def test_scanner_reads_legacy_and_extension_without_executing_code(self):
        root = self.manager.create_preset(self.release, 'Default')
        addon = root / 'scripts/addons/example.py'
        addon.write_text("bl_info = {'name': 'Example', 'version': (1, 2, 3)}\nraise RuntimeError('must not execute')")
        extension = root / 'extensions/user_default/tool'
        extension.mkdir(parents=True)
        (extension / 'blender_manifest.toml').write_text('id="tool"\nname="Tool"\nversion="2.0.0"\ntype="add-on"')
        rows = addons.scan_preset(root)
        self.assertEqual([(row['name'], row['version']) for row in rows], [('Example', '1.2.3'), ('Tool', '2.0.0')])
        self.assertTrue(all(row['enabled'] is None for row in rows))
        rows, message = addons.inspect_addons(self.manager, self.release, 'Default')
        self.assertEqual(len(rows), 2)
        self.assertIn('Install Blender', message)

    def test_inventory_process_failure_returns_files_with_unknown_state(self):
        root = self.manager.create_preset(self.release, 'Default')
        (root / 'scripts/addons/example.py').write_text('bl_info = {"name": "Example"}')
        self._mark_installed()
        process = Mock(returncode=1)
        process.poll.return_value = 1
        with patch('features.blender.addons.scanning.subprocess.Popen', return_value=process):
            rows, message = addons.inspect_addons(self.manager, self.release, 'Default')
        self.assertEqual(rows[0]['name'], 'Example')
        self.assertIsNone(rows[0]['enabled'])
        self.assertIn('unknown', message)

    def test_inventory_timeout_kills_and_reaps_child(self):
        self.manager.create_preset(self.release, 'Default')
        self._mark_installed()
        process = Mock()
        process.poll.side_effect = [None, None]
        with patch('features.blender.addons.scanning.subprocess.Popen', return_value=process):
            rows, message = addons.inspect_addons(self.manager, self.release, 'Default', timeout=-1)
        process.kill.assert_called_once()
        process.wait.assert_called_once()
        self.assertEqual(rows, [])
        self.assertIn('timed out', message)


if __name__ == '__main__':
    unittest.main()
