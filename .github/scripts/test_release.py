"""Release layout, submodule validation and safe publishing regressions."""
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_release as packaging
import publish_release as publishing


class PackageTests(unittest.TestCase):
    def test_layout_nested_contents_exclusions_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['Launch.command', 'Python/shared/nested/module.py', 'Python/uv.lock',
                     '.git/config', 'Python/shared/.git', '.github/workflows/release.yml',
                     '.venv/bin/python', 'Python/__pycache__/a.pyc', '.DS_Store']
            for name in names:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(name)
            (root / 'Launch.command').chmod(0o755)
            packaging.package(root, root / 'release.zip', names, required=set())
            with zipfile.ZipFile(root / 'release.zip') as archive:
                self.assertEqual(set(archive.namelist()), {
                    'Logistics/Launch.command', 'Logistics/Python/shared/nested/module.py',
                    'Logistics/Python/uv.lock'})
                self.assertEqual(archive.read('Logistics/Python/shared/nested/module.py'),
                                 b'Python/shared/nested/module.py')
                self.assertTrue(archive.getinfo('Logistics/Launch.command').external_attr >> 16 & stat.S_IXUSR)

    def test_required_files_must_exist(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, 'Missing required'):
                packaging.package(root, Path(root) / 'release.zip', [], required={'launcher'})

    def test_recursive_inventory(self):
        with patch('package_release.subprocess.check_output', side_effect=[
                ' abc shared\n def shared/nested\n', b'a.py\0shared/nested/b.py\0']) as git:
            self.assertEqual(packaging.tracked_files('.'), ['a.py', 'shared/nested/b.py'])
            self.assertIn('--recursive', git.call_args_list[0].args[0])
            self.assertIn('--recurse-submodules', git.call_args_list[1].args[0])

    def test_missing_or_wrong_submodule_aborts(self):
        for prefix in '-+U':
            with self.subTest(prefix=prefix), patch('package_release.subprocess.check_output',
                    return_value=prefix + 'abc shared\n'):
                with self.assertRaisesRegex(RuntimeError, 'Submodule'):
                    packaging.tracked_files('.')


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'release.zip'
        self.archive.write_bytes(b'fixture')

    def response(self, status=200, assets=()):
        return subprocess.CompletedProcess([], 0 if status == 200 else 1,
            f'HTTP/2.0 {status} Status\n\n' + json.dumps({'assets': list(assets)}), 'error')

    def test_missing_release_creates_with_notes_and_tag_verification(self):
        with patch('publish_release.subprocess.run', side_effect=[self.response(404), None]) as gh:
            publishing.publish('owner/repo', 'v1.0', self.archive)
            args = gh.call_args.args[0]
            self.assertEqual(args[:3], ['gh', 'release', 'create'])
            self.assertIn('--verify-tag', args)
            self.assertIn('--generate-notes', args)

    def test_existing_release_uploads_without_clobber(self):
        with patch('publish_release.subprocess.run', side_effect=[self.response(), None]) as gh:
            publishing.publish('owner/repo', 'v1.0', self.archive)
            self.assertEqual(gh.call_args.args[0][:3], ['gh', 'release', 'upload'])
            self.assertNotIn('--clobber', gh.call_args.args[0])

    def test_duplicate_asset_aborts(self):
        with patch('publish_release.subprocess.run', return_value=self.response(
                assets=[{'name': 'release.zip'}])) as gh:
            with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
                publishing.publish('owner/repo', 'v1.0', self.archive)
            self.assertEqual(gh.call_count, 1)

    def test_auth_and_network_errors_never_create_release(self):
        for response in [self.response(403), subprocess.CompletedProcess([], 1, '', 'network error')]:
            with self.subTest(response=response), patch('publish_release.subprocess.run',
                    return_value=response) as gh:
                with self.assertRaisesRegex(RuntimeError, 'Cannot check'):
                    publishing.publish('owner/repo', 'v1.0', self.archive)
                self.assertEqual(gh.call_count, 1)


if __name__ == '__main__':
    unittest.main()
