"""Import reviewed portable owners with presentation dependencies actively blocked."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from collections import defaultdict
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from Scripts.architecture import ROOT, portable_sources


IMPORT_PROBE = '''
import importlib
import importlib.abc
import json
import sys
attempted = []
class BlockPresentation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.split('.')[0] in {'PySide6', 'toga', 'desktop', 'mobile'}
                or fullname == 'commonUtils.ui' or fullname.startswith('commonUtils.ui.')):
            attempted.append(fullname)
            raise ImportError('Portable owner attempted presentation import: ' + fullname)
sys.meta_path.insert(0, BlockPresentation())
for module in json.loads(sys.argv[1]):
    importlib.import_module(module)
if attempted:
    raise RuntimeError('Presentation imports were attempted, even if caught: ' + repr(attempted))
'''


class PortableImportTests(unittest.TestCase):
    def test_reviewed_owners_import_without_presentation(self):
        policy = json.loads((ROOT / 'Scripts/architecture.json').read_text())
        owners = defaultdict(list)
        for module in portable_sources(ROOT, policy):
            owners['.'.join(module.split('.')[:2])].append(module)
        for owner, modules in sorted(owners.items()):
            with self.subTest(owner=owner), TemporaryDirectory() as temporary:
                environment = dict(os.environ, PYTHONPATH=str(ROOT / 'Python'),
                                   XDG_CONFIG_HOME=temporary, XDG_CACHE_HOME=temporary,
                                   XDG_DATA_HOME=temporary)
                result = subprocess.run([sys.executable, '-c', IMPORT_PROBE, json.dumps(modules)],
                                        cwd=ROOT, env=environment, text=True,
                                        capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_probe_rejects_caught_transitive_presentation_imports(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'helper.py').write_text('try:\n import toga\nexcept ImportError:\n pass\n')
            (root / 'owner.py').write_text('import helper\n')
            result = subprocess.run([sys.executable, '-c', IMPORT_PROBE, '["owner"]'],
                                    cwd=root, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Presentation imports were attempted, even if caught', result.stderr)
