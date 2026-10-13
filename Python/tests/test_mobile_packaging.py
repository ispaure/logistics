"""Mobile payload selection and evidence checks, using isolated Git fixtures."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('mobile_tools', REPO / 'Mobile/tools.py')
mobile_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile_tools)


class MobilePackagingTests(unittest.TestCase):
    def test_payload_excludes_private_files_desktop_features_and_links(self):
        with TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            repo = base / 'checkout'
            shared = repo / 'Python/commonUtils'
            shared.mkdir(parents=True)
            def git(root, *args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git(shared, 'init')
            for name in ('__init__.py', 'tests/mobile_smoke.py', 'tools/mobile_ci.py'):
                target = shared / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((REPO / 'Python/commonUtils' / name).read_text())
            (shared / 'LICENSE.md').write_text('Shared license fixture')
            git(shared, 'add', '.')
            git(shared, '-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'fixture')
            (shared / 'private.py').write_text('must not ship')
            (shared / 'remoteConfig.ini').write_text('must not ship')
            app = repo / 'Python/logisticsmobile'
            app.mkdir()
            for name in mobile_tools.APP_MODULES:
                shutil.copyfile(REPO / 'Python/logisticsmobile' / name, app / name)
            for name in mobile_tools.DOCUMENT_MODULES:
                target = repo / 'Python' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / 'Python' / name, target)
            (repo / 'LICENSE.md').write_text('Application license fixture')
            git(repo, 'init')
            git(repo, 'add', 'Python/logisticsmobile', 'Python/features', 'Python/services', 'LICENSE.md')
            git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'fixture')
            payload = base / 'payload'
            manifest = mobile_tools.stage(repo, payload)
            self.assertFalse(manifest['dirty'])
            self.assertEqual(manifest['features'], ['text', 'markdown', 'epub', 'comics', 'lm'])
            self.assertTrue((payload / 'logisticsmobile/app.py').is_file())
            self.assertFalse((payload / 'commonUtils/private.py').exists())
            self.assertFalse((payload / 'commonUtils/remoteConfig.ini').exists())
            self.assertFalse((payload / 'commonUtils/.git').exists())
            self.assertTrue((payload / 'features/books/epub.py').exists())
            self.assertFalse((payload / 'features/books/reader.py').exists())
            (app / 'documents.py').write_text('# uncommitted change')
            with self.assertRaises(ValueError):
                mobile_tools.stage(repo, base / 'dirty')

    def test_verifier_requires_complete_clean_mobile_evidence(self):
        spec = importlib.util.spec_from_file_location('smoke_contract', REPO / 'Python/logisticsmobile/smoke.py')
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
