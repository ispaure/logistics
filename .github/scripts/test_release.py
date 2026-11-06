"""Release layout, submodule validation and safe publishing regressions."""

# TEST_STAGE = TestStage.REGRESSION
import hashlib
import json
import os
from pathlib import Path
import stat
import shutil
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
                   'docs/development/mobile-evidence/screenshot.png',
                   'docs/development/mobile-evidence/old-report.json',
                   'Python/features/books/docs/mobile-evidence/report.json',
                   'docs/features/books/mobile-evidence/report.json']
        for folder in ('Mobile', 'mobile_build'):
            private.extend(folder + '/' + name for name in (
                'payload/mobile/app.py', 'build/generated.py', 'logs/deploy.log',
                '.venv/bin/python', '.device.json', '.testflight-auth.json',
                '.testflight-keys/upload.p8', '.tools/test-devices.json',
                '.android-beta/signing.json', '.deploy-workspaces/ios/pyproject.toml'))
        public = ['mobile_build/pyproject.toml', 'mobile_build/resources/logistics.png',
                  'Python/mobile/mobile_sources.json', 'Python/desktop/main_window.py']
        # Test tracked ignore policy independently of private runtime symlinks
        # in captured manager checkouts. Git refuses pathspecs below symlinks.
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            subprocess.run(['git', 'init', '-q', str(fixture)], check=True, capture_output=True)
            shutil.copyfile(root / '.gitignore', fixture / '.gitignore')
            result = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'],
                                    cwd=fixture, input=os.fsencode('\0'.join(private + public) + '\0'),
                                    capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertEqual({os.fsdecode(name) for name in result.stdout.split(b'\0') if name},
                         set(private))

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
                         'docs/development/mobile-evidence/old-report.json',
                         'docs/development/mobile-evidence/nested/screenshot.png',
                         'Python/commonUtils/docs/development/mobile-evidence/report.json',
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
                     'Python/commonUtils/docs/development/mobile-evidence/report.json',
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
                    patch('package_release.subprocess.check_output', side_effect=['a'*40, '160000 commit '+'b'*40+'\tPython/commonUtils']), \
                    patch('package_release.build_identity', return_value=dict(schema=1,
                        tag='v0.1.1-alpha.30', revision='a' * 40, committed_at='2026-10-13T22:00:00Z')):
                packaging.package(root, root / 'release.zip', required=set())
            with zipfile.ZipFile(root / 'release.zip') as archive:
                data = archive.read('Logistics/.app-version.json')
                self.assertEqual(json.loads(data)['tag'], 'v0.1.1-alpha.30')
                manifest = json.loads(archive.read('Logistics/.app-install.json'))
                self.assertEqual(manifest['files']['.app-version.json'], hashlib.sha256(data).hexdigest())
                self.assertEqual(manifest['commonUtils_revision'], 'b'*40)

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
            from commonUtils.integrations.wrappers.cmdShellWrapper.process import (
                ProcessSupervisor, get_process_group_kwargs,
            )

            launch_temp = root / 'launch-temp'
            launch_temp.mkdir()
            env = dict(os.environ, APPDATA=str(root / 'appdata'), USERPROFILE=str(root / 'user'),
                       TEMP=str(launch_temp), TMP=str(launch_temp))
            env.pop('COMMONUTILS_ROOT', None)
            log = root / 'launcher.log'
            timed_out = False
            with log.open('wb') as stream:
                child = subprocess.Popen(['cmd.exe', '/d', '/c', 'LaunchLogistics_WIN.bat'],
                    cwd=root / 'extracted/Logistics', env=env, stdin=subprocess.DEVNULL,
                    stdout=stream, stderr=subprocess.STDOUT, **get_process_group_kwargs())
                try:
                    with ProcessSupervisor(child):
                        child.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    timed_out = True
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 8192))
                output = stream.read(8192).decode('utf-8', errors='replace')
            if timed_out:
                staging = list(launch_temp.glob('commonutils_launch_*'))
                expected = ('SOURCE_DIR_VALUE', 'LAUNCH_FILE_VALUE', 'ENSURE_USER_DIR',
                            'ENVIRONMENT_SYNC_WRAPPER_VALUE')
                present = sorted(name for name in expected if any((path / name).is_file() for path in staging))
                self.fail(f'Packaged launcher exceeded 60 seconds. Config staging directories: {len(staging)}. '
                          f'Written config fields: {present}. Launcher output tail:\n{output}')
            self.assertEqual(child.returncode, 1, output)
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

    def test_default_required_inventory_includes_build_manager_bootstrap(self):
        bootstrap_files = {
            'build-project.json',
            'logistics_build/manager_bridge.py',
            'logistics_build/tooling_bootstrap.py',
        }
        names = packaging.REQUIRED | bootstrap_files
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in sorted(names):
                source = root / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(name, encoding='utf-8')

            output = root / 'release.zip'
            for missing in sorted(bootstrap_files):
                with self.subTest(missing=missing):
                    with self.assertRaises(RuntimeError) as error:
                        packaging.package(root, output, sorted(names - {missing}))
                    self.assertEqual(str(error.exception), f'Missing required release files: {[missing]}')
                    self.assertFalse(output.exists())

            packaging.package(root, output, sorted(names))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {'Logistics/.app-install.json'} | {'Logistics/' + name for name in names})

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

    def response(self, status=200, assets=(), **metadata):
        return subprocess.CompletedProcess([], 0 if status == 200 else 1,
            f'HTTP/2.0 {status} Status\n\n' + json.dumps(dict(assets=list(assets), **metadata)), 'error')

    def test_missing_release_creates_with_notes_and_tag_verification(self):
        with patch('publish_release.subprocess.run', side_effect=[self.response(404), None]) as gh:
            publishing.publish('owner/repo', 'v1.0', self.archive)
            args = gh.call_args.args[0]
            self.assertEqual(args[:3], ['gh', 'release', 'create'])
            self.assertIn('--verify-tag', args)
            self.assertIn('--generate-notes', args)

    def test_alpha_beta_tags_publish_as_prereleases(self):
        for tag in ('v1.0.0-alpha.2', 'v1.0.0-beta.1'):
            notes_dir = Path(self.temp.name)
            text = '# Reviewed title\n\nReviewed description.\n'
            (notes_dir / (tag + '.md')).write_text(text)
            with patch.object(publishing, 'NOTES_DIR', notes_dir), patch('publish_release.subprocess.run',
                    side_effect=[self.response(404), None, self.response(name='Reviewed title', body=text)]) as gh:
                publishing.publish('owner/repo', tag, self.archive)
            self.assertIn('--prerelease', gh.call_args_list[1].args[0])

    def test_tag_specific_notes_set_numbered_title_without_bypassing_verification(self):
        notes_dir = Path(self.temp.name)
        notes = notes_dir / 'v1.0.0-alpha.3.md'
        notes.write_text('# Phase 0 Part 4: Validated mobile foundation\n\nRelease description.\n')
        with patch.object(publishing, 'NOTES_DIR', notes_dir), patch(
                'publish_release.subprocess.run', side_effect=[self.response(404), None,
                    self.response(name='Phase 0 Part 4: Validated mobile foundation', body=notes.read_text())]) as gh:
            publishing.publish('owner/repo', 'v1.0.0-alpha.3', self.archive)
        args = gh.call_args_list[1].args[0]
        self.assertEqual(args[args.index('--title') + 1], 'Phase 0 Part 4: Validated mobile foundation')
        self.assertIn('--notes-file', args)
        self.assertEqual(notes.read_text(), '# Phase 0 Part 4: Validated mobile foundation\n\nRelease description.\n')
        self.assertIn('--verify-tag', args)
        self.assertIn('--prerelease', args)
        self.assertNotIn('--generate-notes', args)

    def test_numbered_main_tags_publish_as_stable(self):
        notes_dir = Path(self.temp.name)
        text = '# Stable reviewed title\n\nReviewed description.\n'
        (notes_dir / 'v0.1.0.md').write_text(text)
        expected = dict(name='Logistics 0.1.0-main.01', body=text.replace('Stable reviewed title', 'Logistics 0.1.0-main.01'))
        with patch.object(publishing, 'NOTES_DIR', notes_dir), patch('publish_release.subprocess.run',
                side_effect=[self.response(404), None, self.response(**expected)]) as gh:
            publishing.publish('owner/repo', 'v0.1.0-main.01', self.archive)
        self.assertNotIn('--prerelease', gh.call_args_list[1].args[0])

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

    def test_alpha6_inherits_only_latest_lower_alpha_reviewed_description(self):
        directory = Path(self.temp.name)
        for name, description in [('v0.2.0-alpha.2', 'older'), ('v0.2.0-alpha.5', 'Reviewed DataView disclosure'),
                                  ('v0.2.0-alpha.7', 'future'), ('v0.2.0-beta.5', 'other channel'),
                                  ('v0.3.0-alpha.5', 'other version')]:
            (directory / (name + '.md')).write_text('# ' + name + '\n\n' + description + '\n')
        expected = publishing.expected_metadata('v0.2.0-alpha.6', notes_dir=directory)
        self.assertEqual(expected, dict(name='Logistics 0.2.0-alpha.6',
            body='# Logistics 0.2.0-alpha.6\n\nReviewed DataView disclosure\n'))
        (directory / 'v0.2.0-alpha.6.md').write_text('# Exact reviewed title\n\nExact reviewed description\n')
        self.assertEqual(publishing.expected_metadata('v0.2.0-alpha.6', notes_dir=directory)['name'], 'Exact reviewed title')

    def test_reviewed_policy_never_crosses_version_channel_or_future_number(self):
        directory = Path(self.temp.name)
        (directory / 'v0.2.0-alpha.5.md').write_text('# Reviewed\n\nDescription\n')
        for tag in ('v0.3.0-alpha.6', 'v0.2.0-beta.6', 'v0.2.0-main.6', 'v0.2.0-alpha.4'):
            with self.subTest(tag=tag), self.assertRaisesRegex(RuntimeError, 'Missing reviewed'):
                publishing.expected_metadata(tag, notes_dir=directory)

    def test_stable_main_uses_same_version_base_and_retains_complete_description(self):
        directory = Path(self.temp.name)
        (directory / 'v0.2.0.md').write_text('# Stable title\n\nThe users own JSON runs only under reviewed conditions.\n')
        value = publishing.expected_metadata('v0.2.0-main.1', notes_dir=directory)
        self.assertEqual(value['name'], 'Logistics 0.2.0-main.1')
        self.assertIn('The users own JSON runs only under reviewed conditions.', value['body'])

    def test_actual_reviewed_alpha5_content_is_preserved_for_alpha6(self):
        source = publishing.NOTES_DIR / 'v0.2.0-alpha.5.md'
        original = source.read_text()
        expected = publishing.expected_metadata('v0.2.0-alpha.6')
        self.assertEqual(expected['body'].partition('\n')[2], original.partition('\n')[2])
        self.assertIn('dataviewjs', expected['body'])
        self.assertIn('JSON itself is not executable code.', expected['body'])
        self.assertEqual(source.read_text(), original)

    def test_malformed_newest_or_exact_notes_never_fall_back_silently(self):
        directory = Path(self.temp.name)
        (directory / 'v0.2.0-alpha.1.md').write_text('# Valid\n\nReviewed description\n')
        for text in ('', 'No markdown title\n\nDescription', '# Title only\n', '# Title\n\nBad\0description'):
            (directory / 'v0.2.0-alpha.5.md').write_text(text)
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                publishing.expected_metadata('v0.2.0-alpha.6', notes_dir=directory)

    def test_reviewed_line_endings_have_one_canonical_body(self):
        directory = Path(self.temp.name)
        source = directory / 'v0.2.0-alpha.5.md'
        canonical = '# Reviewed title\n\nUsers’ JSON is data.\nReviewed execution conditions remain intact.\n'
        for ending in ('\n', '\r\n', '\r'):
            raw = canonical.replace('\n', ending).encode('utf-8')
            source.write_bytes(raw)
            with self.subTest(ending=repr(ending)):
                exact = publishing.expected_metadata('v0.2.0-alpha.5', notes_dir=directory)
                later = publishing.expected_metadata('v0.2.0-alpha.6', notes_dir=directory)
                self.assertEqual(exact, dict(name='Reviewed title', body=canonical))
                self.assertEqual(later['body'], canonical.replace('Reviewed title', 'Logistics 0.2.0-alpha.6', 1))
                self.assertEqual(source.read_bytes(), raw)

    def test_creation_reads_normalized_reviewed_file_and_verifies_remote_body(self):
        directory = Path(self.temp.name)
        original = '# Previous title\n\nReviewed JSON disclosure.\n'
        (directory / 'v0.2.0-alpha.5.md').write_text(original)
        expected = dict(name='Logistics 0.2.0-alpha.6', body=original.replace('Previous title', 'Logistics 0.2.0-alpha.6'))
        observed = []
        def gh(args, **options):
            if args[:3] == ['gh', 'release', 'create']:
                path = Path(args[args.index('--notes-file') + 1])
                observed.append((path, path.read_bytes()))
                return None
            return self.response(**expected) if observed else self.response(404)
        with patch.object(publishing, 'NOTES_DIR', directory), patch('publish_release.subprocess.run', side_effect=gh):
            publishing.publish('owner/repo', 'v0.2.0-alpha.6', self.archive)
        self.assertEqual(observed[0][1], expected['body'].encode('utf-8'))
        self.assertNotIn(b'\r', observed[0][1])
        self.assertFalse(observed[0][0].exists())
        self.assertEqual((directory / 'v0.2.0-alpha.5.md').read_text(), original)

    def test_malformed_exact_file_cannot_use_valid_lower_notes(self):
        directory = Path(self.temp.name)
        (directory / 'v0.2.0-alpha.5.md').write_text('# Valid\n\nDescription\n')
        (directory / 'v0.2.0-alpha.6.md').write_text('')
        with self.assertRaisesRegex(RuntimeError, 'require a title'):
            publishing.expected_metadata('v0.2.0-alpha.6', notes_dir=directory)

    def test_metadata_reconciliation_state_change_blocks_asset_upload(self):
        directory = Path(self.temp.name)
        text = '# Reviewed\n\nReviewed disclosure.\n'
        (directory / 'v0.2.0-alpha.6.md').write_text(text)
        for changed in (dict(draft=False, assets=[]), dict(draft=True, assets=[{'name': 'foreign'}])):
            with self.subTest(changed=changed), patch.object(publishing, 'NOTES_DIR', directory), patch(
                    'publish_release.subprocess.run', side_effect=[self.response(id=4, draft=True, name='Wrong', body='wrong'),
                        None, self.response(id=4, name='Reviewed', body=text, **changed)]) as gh:
                with self.assertRaisesRegex(RuntimeError, 'state/assets changed'):
                    publishing.publish('owner/repo', 'v0.2.0-alpha.6', self.archive)
            self.assertEqual(gh.call_count, 3)

    def test_existing_wrong_body_is_reconciled_without_touching_assets_or_draft(self):
        directory = Path(self.temp.name)
        text = '# Reviewed\n\nUsers own reviewed JSON disclosure.\n'
        (directory / 'v0.2.0-alpha.6.md').write_text(text)
        unchanged = dict(id=41, draft=True, prerelease=True)
        assets = [{'name': 'release.zip', 'id': 77, 'size': 900}]
        with patch.object(publishing, 'NOTES_DIR', directory), patch('publish_release.subprocess.run',
                side_effect=[self.response(assets=assets, name='Wrong', body='Generated', **unchanged), None,
                             self.response(assets=assets, name='Reviewed', body=text, **unchanged)]) as gh:
            with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
                publishing.publish('owner/repo', 'v0.2.0-alpha.6', self.archive)
        self.assertEqual(gh.call_count, 3)
        self.assertEqual(gh.call_args_list[1].args[0],
            ['gh', 'api', '--method', 'PATCH', 'repos/owner/repo/releases/41', '--input', '-'])
        self.assertEqual(json.loads(gh.call_args_list[1].kwargs['input']), dict(name='Reviewed', body=text))
        self.assertFalse(any('upload' in call.args[0] or '--clobber' in call.args[0] for call in gh.call_args_list))

    def test_concurrent_download_counter_change_does_not_look_like_asset_replacement(self):
        directory = Path(self.temp.name)
        text = '# Reviewed\n\nReviewed disclosure.\n'
        (directory / 'v0.2.0-alpha.6.md').write_text(text)
        asset = dict(id=77, name='release.zip', size=900, digest='sha256:fixed')
        with patch.object(publishing, 'NOTES_DIR', directory), patch('publish_release.subprocess.run', side_effect=[
                self.response(id=4, name='Wrong', body='wrong', assets=[dict(asset, download_count=1)]), None,
                self.response(id=4, name='Reviewed', body=text, assets=[dict(asset, download_count=2)])]) as gh:
            with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
                publishing.publish('owner/repo', 'v0.2.0-alpha.6', self.archive)
        self.assertEqual(gh.call_count, 3)

    def test_metadata_readback_mismatch_blocks_upload(self):
        directory = Path(self.temp.name)
        text = '# Reviewed\n\nReviewed disclosure.\n'
        (directory / 'v0.2.0-alpha.6.md').write_text(text)
        with patch.object(publishing, 'NOTES_DIR', directory), patch('publish_release.subprocess.run',
                side_effect=[self.response(id=4, name='Wrong', body='wrong'), None,
                             self.response(id=4, name='Reviewed', body='still wrong')]) as gh:
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                publishing.publish('owner/repo', 'v0.2.0-alpha.6', self.archive)
        self.assertEqual(gh.call_count, 3)

    def test_matching_existing_notes_do_not_patch_or_replace_asset(self):
        directory = Path(self.temp.name)
        text = '# Reviewed\n\nReviewed disclosure.\n'
        (directory / 'v0.2.0-alpha.6.md').write_text(text)
        with patch.object(publishing, 'NOTES_DIR', directory), patch('publish_release.subprocess.run',
                return_value=self.response(assets=[{'name': 'release.zip'}], name='Reviewed', body=text)) as gh:
            with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
                publishing.publish('owner/repo', 'v0.2.0-alpha.6', self.archive)
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
