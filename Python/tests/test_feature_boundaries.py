"""Dependency boundaries that keep feature adapters usable outside their host."""
import ast
from pathlib import Path
import subprocess
import sys
import os
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FeatureBoundaryTests(unittest.TestCase):
    def test_rclone_mobile_does_not_import_the_application_host(self):
        paths = [path for owner in ('rclone', 'lm', 'text_editor')
                 for path in (ROOT / 'Python/features' / owner).rglob('*.py')
                 if 'mobile' in path.parts]
        for path in paths:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                         [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                self.assertFalse(any(name == 'logisticsmobile' or name.startswith('logisticsmobile.')
                                     for name in names), str(path))

    def test_provider_adapters_import_without_ui_or_application_host(self):
        script = '''
import sys
from services.document_readers import PrivateReader
from services.archive_access import NativeArchiveAccess
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
assert not any(name.startswith(('PySide', 'toga', 'logisticsmobile')) for name in sys.modules)
reader = PrivateReader('hello.txt', b'hello')
assert reader.page(0) == ('text', 'hello')
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                env=dict(os.environ, PYTHONPATH=str(ROOT / 'Python')),
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
