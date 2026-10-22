"""Mobile payload selection and evidence checks, using isolated Git fixtures."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import os
from tempfile import TemporaryDirectory
import unittest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('mobile_tools', REPO / 'mobile_build/tools.py')
mobile_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile_tools)


class MobilePackagingTests(unittest.TestCase):
    def test_qt_proof_packages_the_feature_owned_bridge_without_the_app(self):
        spec = importlib.util.spec_from_file_location('qt_proof_prepare', REPO / 'mobile_build/qt_proof/prepare.py')
        prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prepare)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            payload = prepare.stage(root / 'payload')
            self.assertFalse((payload / 'mobile').exists())
            self.assertFalse((payload / 'features/rclone/api.py').exists())
            code = '''
import sys
from features.rclone.mobile.cloud import CloudClient
assert CloudClient.__module__ == 'features.rclone.mobile.cloud'
assert not any(name.startswith(('PySide', 'toga', 'mobile', 'config')) for name in sys.modules)
'''
            result = subprocess.run([sys.executable, '-c', code], cwd=root,
                env=dict(os.environ, PYTHONPATH=str(payload)), capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_feature_adapter_dependencies_are_checked_before_building(self):
        feature_modules = tuple(name for name in mobile_tools.DOCUMENT_MODULES
                                if name.startswith('features/rclone/') and not name.endswith('/credential_vault.py'))
        with self.assertRaisesRegex(ValueError, 'imports unstaged features.rclone.mobile.credential_vault'):
            mobile_tools.validate_app_modules(REPO / 'Python/mobile', feature_modules=feature_modules)

    def test_app_imports_are_all_in_the_packaged_payload(self):
        mobile_tools.validate_app_modules(REPO / 'Python/mobile')
        # This omission caused a black launch screen in signed iPhone builds.
        missing_recent = tuple(name for name in mobile_tools.APP_MODULES if name != 'recent_documents.py')
        with self.assertRaisesRegex(ValueError, 'imports unstaged mobile.recent_documents'):
            mobile_tools.validate_app_modules(REPO / 'Python/mobile', missing_recent)
        missing_discovery = tuple(name for name in mobile_tools.APP_MODULES if name != 'folder_discovery.py')
        with self.assertRaisesRegex(ValueError, 'imports unstaged mobile.folder_discovery'):
            mobile_tools.validate_app_modules(REPO / 'Python/mobile', missing_discovery)
        missing_listing = tuple(name for name in mobile_tools.APP_MODULES if name != 'folder_listing.py')
        with self.assertRaisesRegex(ValueError, 'imports unstaged mobile.folder_listing'):
            mobile_tools.validate_app_modules(REPO / 'Python/mobile', missing_listing)
        missing_operations = tuple(name for name in mobile_tools.APP_MODULES if name != 'file_operations.py')
        with self.assertRaisesRegex(ValueError, 'imports unstaged mobile.file_operations'):
            mobile_tools.validate_app_modules(REPO / 'Python/mobile', missing_operations)


        missing_markdown = tuple(name for name in mobile_tools.DOCUMENT_MODULES
                                 if name != 'features/text_editor/mobile/provider_markdown.py')
        with self.assertRaisesRegex(ValueError, 'imports unstaged features.text_editor.mobile.provider_markdown'):
            mobile_tools.validate_app_modules(REPO / 'Python/mobile', document_modules=missing_markdown)

    def test_payload_excludes_private_files_desktop_features_and_links(self):
        with TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            repo = base / 'checkout'
            shared = repo / 'Python/commonUtils'
            shared.mkdir(parents=True)
            def git(root, *args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git(shared, 'init')
            for name in ('__init__.py', 'tests/mobile_smoke.py', 'tools/mobile_ci.py', *mobile_tools.SHARED_REQUIRED_MODULES):
                target = shared / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((REPO / 'Python/commonUtils' / name).read_text())
            (shared / 'LICENSE.md').write_text('Shared license fixture')
            git(shared, 'add', '.')
            git(shared, '-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'fixture')
            (shared / 'private.py').write_text('must not ship')
            (shared / 'remoteConfig.ini').write_text('must not ship')
            app = repo / 'Python/mobile'
            app.mkdir()
            for name in mobile_tools.APP_MODULES:
                (app / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / 'Python/mobile' / name, app / name)
            for name in mobile_tools.DOCUMENT_MODULES:
                target = repo / 'Python' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / 'Python' / name, target)
            for owner in mobile_tools.SOURCE_OWNERS:
                target = repo / 'Python' / owner / 'mobile_sources.json'
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / 'Python' / owner / 'mobile_sources.json', target)
            (repo / 'LICENSE.md').write_text('Application license fixture')
            (repo / 'README.md').write_text('# Application fixture\n')
            git(repo, 'init')
            git(repo, 'add', 'Python/mobile', 'Python/features', 'Python/services', 'Python/configFile.ini', 'LICENSE.md', 'README.md')
            git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'fixture')
            payload = base / 'payload'
            manifest = mobile_tools.stage(repo, payload)
            self.assertFalse(manifest['dirty'])
            self.assertEqual(manifest['logistics_committed_at'],
                git(repo, 'show', '-s', '--format=%cI', 'HEAD').stdout.decode().strip())
            self.assertTrue((payload / 'services/build_version.py').is_file())
            self.assertTrue((payload / 'mobile/settings_ui.py').is_file())
            self.assertEqual(manifest['features'], ['text', 'markdown', 'epub', 'comics', 'lm', 'rclone'])
            self.assertTrue((payload / 'mobile/app.py').is_file())
            self.assertTrue((payload / 'logisticsmobile/__main__.py').is_file())
            self.assertFalse((payload / 'logisticsmobile/app.py').exists())
            self.assertTrue((payload / 'mobile/folder_discovery.py').is_file())
            self.assertTrue((payload / 'mobile/file_operations.py').is_file())
            self.assertTrue((payload / 'mobile/folder_listing.py').is_file())
            self.assertTrue((payload / 'mobile/recent_documents.py').is_file())
            self.assertFalse((payload / 'commonUtils/private.py').exists())
            self.assertFalse((payload / 'commonUtils/remoteConfig.ini').exists())
            self.assertFalse((payload / 'commonUtils/.git').exists())
            self.assertTrue((payload / 'features/books/epub.py').exists())
            self.assertTrue((payload / 'features/text_editor/mobile/provider_markdown.py').is_file())
            self.assertTrue((payload / 'commonUtils/ui/native/android/io/github/ispaure/commonutils/NavigationBack.java').exists())
            bridge = shared / 'ui/native/android/io/github/ispaure/commonutils/NavigationBack.java'
            bridge.write_text(bridge.read_text() + '\n// local fixture mutation\n')
            with self.assertRaises(ValueError):
                mobile_tools.stage(repo, base / 'dirty-native-release')
            local_manifest = mobile_tools.stage(repo, base / 'dirty-native-local', allow_dirty=True)
            self.assertTrue(local_manifest['commonUtils_dirty'])
            self.assertNotEqual(manifest['source_sha256'], local_manifest['source_sha256'])
            self.assertFalse((payload / 'features/books/ui/reader.py').exists())
            (app / 'documents.py').write_text('# uncommitted change')
            with self.assertRaises(ValueError):
                mobile_tools.stage(repo, base / 'dirty')

    def test_owner_manifests_reject_escaping_duplicate_and_invalid_paths(self):
        with TemporaryDirectory() as directory:
            repo = Path(directory)
            for owner in mobile_tools.SOURCE_OWNERS:
                target = repo / 'Python' / owner / 'mobile_sources.json'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(dict(schema=1, modules=[])))
            target = repo / 'Python/features/books/mobile_sources.json'
            for modules in (['../outside.py'], ['/outside.py'], ['C:/outside.py'], ['C:outside.py'], ['a.py', 'a.py'], ['a\\b.py'], ['a.txt']):
                target.write_text(json.dumps(dict(schema=1, modules=modules)))
                with self.subTest(modules=modules), self.assertRaises(ValueError):
                    mobile_tools.load_source_modules(repo)
            target.write_text(json.dumps(dict(schema=1, modules=['epub.py'])))
            _, sources = mobile_tools.load_source_modules(repo)
            self.assertIn('features/books/epub.py', sources)
            self.assertNotIn('features/books/ui/reader.py', sources)

    def test_service_dependencies_are_checked_as_well_as_feature_adapters(self):
        selected = tuple(name for name in mobile_tools.DOCUMENT_MODULES
                         if name != 'services/documents/readers.py')
        with self.assertRaisesRegex(ValueError, 'imports unstaged services.documents.readers'):
            mobile_tools.validate_app_modules(REPO / 'Python/mobile', document_modules=selected)

    def test_verifier_requires_complete_clean_mobile_evidence(self):
        spec = importlib.util.spec_from_file_location('smoke_contract', REPO / 'Python/mobile/smoke.py')
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        report = dict(schema=1, suite='logistics-mobile-documents', target='android',
                      sys_platform='android', environment='android-emulator', success=True,
                      tests_run=len(contract.EXPECTED_TESTS), expected_tests=list(contract.EXPECTED_TESTS),
                      failures=0, errors=0, skipped=0,
                      source=dict(dirty=False, logistics_commit='a' * 40, commonUtils_commit='b' * 40))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log, output = root / 'runtime.log', root / 'result.json'
            def write(data, copies=1):
                log.write_text((contract.PREFIX + json.dumps(data) + '\n') * copies)
            write(report)
            self.assertEqual(mobile_tools.verify(log, 'android', output), report)
            for field, value in (('environment', 'desktop-harness'), ('tests_run', 12),
                                 ('skipped', 1), ('success', False), ('sys_platform', 'darwin')):
                altered = dict(report, **{field: value})
                write(altered)
                with self.assertRaises(ValueError):
                    mobile_tools.verify(log, 'android', output)
            write(dict(report, source=dict(report['source'], dirty=True)))
            with self.assertRaises(ValueError):
                mobile_tools.verify(log, 'android', output)
            write(report, copies=2)
            with self.assertRaises(ValueError):
                mobile_tools.verify(log, 'android', output)
