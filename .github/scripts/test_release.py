"""Release layout, submodule validation and safe publishing regressions."""
import hashlib
import json
import os
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
    def test_gitignore_protects_mobile_outputs_after_the_directory_rename(self):
        root = Path(__file__).resolve().parents[2]
        private = ['Credentials/rclone/private.zip', 'Python/__pycache__/launch.pyc',
                   '.env.local', 'local-signing.p12', 'profile.prof', 'debug.log',
                   'test-results/mobile-evidence/report.json',
                   'docs/development/mobile-evidence/screenshot.png']
        for folder in ('Mobile', 'mobile_build'):
            private.extend(folder + '/' + name for name in (
                'payload/mobile/app.py', 'build/generated.py', 'logs/deploy.log',
                '.venv/bin/python', '.device.json', '.testflight-auth.json',
                '.testflight-keys/upload.p8', '.tools/test-devices.json',
                '.android-beta/signing.json', '.deploy-workspaces/ios/pyproject.toml'))
        public = ['mobile_build/pyproject.toml', 'mobile_build/resources/logistics.png',
                  'Python/mobile/mobile_sources.json', 'Python/desktop/main_window.py']
        result = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin'],
                                cwd=root, input='\n'.join(private + public) + '\n',
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()), set(private))

    def test_private_material_and_generated_mobile_outputs_never_ship(self):
        excluded = ['nested/signing.key', 'certificate.pem', 'upload.p8', 'release.p12',
                    'app.jks', 'secrets.json', 'nested/.env.production', 'service-account-prod.json',
                    'mobile_build/payload/source.json', 'mobile_build/logs/device.json',
                    'Mobile/payload/source.json', 'Mobile/.testflight-auth.json',
                    'mobile_build/.deploy-workspaces/qa/pyproject.toml', 'mobile_build/.device.json',
                    'mobile_build/.testflight-auth.json', 'app.apk', 'app.ipa',
                    'node_modules/package/index.js', 'DerivedData/project/file',
                    'app.xcarchive/Info.plist', 'app.dSYM/file']
        excluded.extend(['docs/development/mobile-evidence/report.json',
                         'docs/development/mobile-evidence/nested/screenshot.png',
                         'Python/commonUtils/docs/developer/mobile-evidence/report.json',
                         'test-results/mobile-evidence/report.json'])
        for name in excluded:
            with self.subTest(name=name):
                self.assertFalse(packaging.included(name))
        for name in ['Python/uv.lock', 'mobile_build/rclone_bridge/go.sum',
                     'mobile_build/pyproject.toml', 'mobile_build/resources/logistics.png']:
            self.assertTrue(packaging.included(name))

    def test_release_omits_explicitly_supplied_local_evidence_and_preserves_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['docs/development/validation-artifacts.md',
                     'docs/development/mobile-evidence/nested/screenshot.png',
                     'Python/commonUtils/docs/developer/mobile-evidence/report.json',
                     'test-results/mobile-evidence/report.json']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'local artifact fixture')
            packaging.package(root, root / 'release.zip', names, required=set())
            with zipfile.ZipFile(root / 'release.zip') as archive:
                self.assertIn('Logistics/' + names[0], archive.namelist())
                self.assertFalse(any('mobile-evidence/' in name for name in archive.namelist()))
            for name in names:
                self.assertEqual((root / name).read_bytes(), b'local artifact fixture')

    def test_release_identity_is_stamped_and_managed_by_the_install_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.py').write_text('pass\n')
            with patch('package_release.tracked_files', return_value=['source.py']), \
                    patch('package_release.subprocess.check_output', return_value='a' * 40), \
                    patch('package_release.build_identity', return_value=dict(schema=1,
                        tag='v0.1.1-alpha.30', revision='a' * 40, committed_at='2026-10-13T22:00:00Z')):
                packaging.package(root, root / 'release.zip', required=set())
            with zipfile.ZipFile(root / 'release.zip') as archive:
                data = archive.read('Logistics/.app-version.json')
                self.assertEqual(json.loads(data)['tag'], 'v0.1.1-alpha.30')
                manifest = json.loads(archive.read('Logistics/.app-install.json'))
                self.assertEqual(manifest['files']['.app-version.json'], hashlib.sha256(data).hexdigest())

    def test_windows_scripts_have_crlf_and_manifest_hashes_shipped_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'@echo off\ncall :ReadLaunchConfig\r\nexit /b\n:ReadLaunchConfig\nexit /b\n'
            for name in ('Launch.bat', 'nested/helper.CMD', 'unchanged.sh'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
            packaging.package(root, root / 'release.zip',
                              ['Launch.bat', 'nested/helper.CMD', 'unchanged.sh'], required=set())
            with zipfile.ZipFile(root / 'release.zip') as archive:
                manifest = json.loads(archive.read('Logistics/.app-install.json'))
                for name in ('Launch.bat', 'nested/helper.CMD'):
                    data = archive.read('Logistics/' + name)
                    self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
                    self.assertNotIn(b'\r\r\n', data)
                    self.assertEqual(manifest['files'][name], hashlib.sha256(data).hexdigest())
                    self.assertEqual((root / name).read_bytes(), original)
                self.assertEqual(archive.read('Logistics/unchanged.sh'), original)

    @unittest.skipUnless(os.name == 'nt', 'Requires native Windows cmd.exe and PowerShell')
    def test_packaged_windows_launcher_reads_config_before_bootstrap(self):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='Logistics launch ') as directory:
            root = Path(directory)
            names = ['LaunchLogistics_WIN.bat',
                     'Python/commonUtils/launchers/LaunchPythonProject_WIN.bat', 'launch_config.ini']
            for name in names[:2]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                # Reproduce a Linux-built release, regardless of checkout policy.
                target.write_bytes((repository / name).read_bytes().replace(b'\r\n', b'\n'))
            (root / 'launch_config.ini').write_text(
                '[Launch]\ncommonutils_root = Python/commonUtils\n'
                'source_dir = missing-source\nlaunch_file = main\n'
                'ensure_user_dir =\npause_after_completed = false\n')
            packaging.package(root, root / 'release.zip', names, required=set())
            with zipfile.ZipFile(root / 'release.zip') as archive:
                archive.extractall(root / 'extracted')
            env = dict(os.environ, APPDATA=str(root / 'appdata'), USERPROFILE=str(root / 'user'))
            env.pop('COMMONUTILS_ROOT', None)
            result = subprocess.run(['cmd.exe', '/d', '/c', 'LaunchLogistics_WIN.bat'],
                cwd=root / 'extracted/Logistics', env=env, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, errors='replace', timeout=60)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn('Configured source_dir does not exist or is not a directory:', output)
            self.assertIn('missing-source', output)

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
                    'Logistics/.app-install.json', 'Logistics/Launch.command', 'Logistics/Python/shared/nested/module.py',
                    'Logistics/Python/uv.lock'})
                self.assertEqual(archive.read('Logistics/Python/shared/nested/module.py'),
                                 b'Python/shared/nested/module.py')
                self.assertEqual(stat.S_IMODE(archive.getinfo('Logistics/Launch.command').external_attr >> 16),
                                 stat.S_IMODE((root / 'Launch.command').stat().st_mode))
                if os.name != 'nt':
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

    def test_alpha_beta_tags_publish_as_prereleases(self):
        for tag in ('v1.0.0-alpha.2', 'v1.0.0-beta.1'):
            with patch('publish_release.subprocess.run', side_effect=[self.response(404), None]) as gh:
                publishing.publish('owner/repo', tag, self.archive)
            self.assertIn('--prerelease', gh.call_args.args[0])

    def test_tag_specific_notes_set_numbered_title_without_bypassing_verification(self):
        notes_dir = Path(self.temp.name)
        notes = notes_dir / 'v1.0.0-alpha.3.md'
        notes.write_text('# Phase 0 Part 4: Validated mobile foundation\n\nRelease description.\n')
        with patch.object(publishing, 'NOTES_DIR', notes_dir), patch(
                'publish_release.subprocess.run', side_effect=[self.response(404), None]) as gh:
            publishing.publish('owner/repo', 'v1.0.0-alpha.3', self.archive)
        args = gh.call_args.args[0]
        self.assertEqual(args[args.index('--title') + 1], 'Phase 0 Part 4: Validated mobile foundation')
        self.assertEqual(args[args.index('--notes-file') + 1], str(notes))
        self.assertIn('--verify-tag', args)
        self.assertIn('--prerelease', args)
        self.assertNotIn('--generate-notes', args)

    def test_numbered_main_tags_publish_as_stable(self):
        with patch('publish_release.subprocess.run', side_effect=[self.response(404), None]) as gh:
            publishing.publish('owner/repo', 'v0.1.0-main.01', self.archive)
        self.assertNotIn('--prerelease', gh.call_args.args[0])

    def test_empty_tag_notes_abort_before_creating_a_release(self):
        notes_dir = Path(self.temp.name)
        (notes_dir / 'v1.0.md').write_text('')
        with patch.object(publishing, 'NOTES_DIR', notes_dir), patch(
                'publish_release.subprocess.run', return_value=self.response(404)) as gh:
            with self.assertRaisesRegex(RuntimeError, 'require a title'):
                publishing.publish('owner/repo', 'v1.0', self.archive)
        self.assertEqual(gh.call_count, 1)

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
