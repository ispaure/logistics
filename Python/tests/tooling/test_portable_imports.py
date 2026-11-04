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


FEATURE_DECLARATIONS = ('commonUtils.ui', 'commonUtils.ui.features',
                        'commonUtils.ui.features.declarations')

IMPORT_PROBE = '''
import importlib
import importlib.abc
import json
import sys
attempted = []
forbidden = json.loads(sys.argv[2])
declarations = json.loads(sys.argv[3])
def blocked(fullname):
    root = fullname.split('.')[0]
    presentation = (root in {'desktop', 'mobile'} or root.startswith(('PySide', 'toga'))
                    or fullname == 'commonUtils.ui' or fullname.startswith('commonUtils.ui.'))
    return (presentation and fullname not in declarations
            or any(fullname == name or fullname.startswith(name + '.') for name in forbidden))
class BlockPresentation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if blocked(fullname):
            attempted.append(fullname)
            raise ImportError('Portable owner attempted presentation import: ' + fullname)
sys.meta_path.insert(0, BlockPresentation())
for module in json.loads(sys.argv[1]):
    importlib.import_module(module)
'''

VERIFY_PROBE = '''
loaded = [name for name in sys.modules if blocked(name)]
if attempted or loaded:
    raise RuntimeError('Forbidden imports were attempted, even if caught: '
                       + repr(sorted(set(attempted + loaded))))
'''


class PortableImportTests(unittest.TestCase):
    def probe(self, modules, *, cwd=ROOT, forbidden=(), checks='', allow_feature_declarations=False):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = dict(os.environ, PYTHONPATH=str(ROOT / 'Python'),
                               COMMONUTILS_STORAGE_ROOT=str(root / 'shared'),
                               XDG_CONFIG_HOME=str(root / 'config'), XDG_CACHE_HOME=str(root / 'cache'),
                               XDG_DATA_HOME=str(root / 'data'), APPDATA=str(root / 'roaming'),
                               LOCALAPPDATA=str(root / 'local'))
            # Verify after the behavioral checks as well as module imports:
            # registration can attempt (and catch) forbidden dependencies too.
            script = IMPORT_PROBE + '\n' + checks + '\n' + VERIFY_PROBE
            declarations = FEATURE_DECLARATIONS if allow_feature_declarations else ()
            return subprocess.run([sys.executable, '-c', script, json.dumps(modules),
                                   json.dumps(forbidden), json.dumps(declarations)],
                                  cwd=cwd, env=environment, text=True, capture_output=True, timeout=30)

    def test_reviewed_owners_import_without_presentation(self):
        policy = json.loads((ROOT / 'Scripts/architecture.json').read_text())
        owners = defaultdict(list)
        for module in portable_sources(ROOT, policy):
            owners['.'.join(module.split('.')[:2])].append(module)
        for owner, modules in sorted(owners.items()):
            with self.subTest(owner=owner):
                result = self.probe(modules)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_notes_library_registration_and_model_are_independent_of_editor_and_gui(self):
        result = self.probe(['features.notes_library', 'features.notes_library.notes'],
                            forbidden=('features.text_editor',), allow_feature_declarations=True, checks='''
from features.notes_library import register
from features.notes_library.notes import NotesLibrary
feature = register()
if feature.id != 'notes_library' or feature.requires:
    raise AssertionError('Notes Library must retain its identity without required features')
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_provider_adapters_import_without_presentation_and_read_private_text(self):
        result = self.probe([
            'services.documents.readers', 'services.documents.archive_access',
            'services.documents.preparation', 'features.images.validation',
            'features.books.mobile.content', 'features.rclone.localcrypt.mobile.copies'], checks='''
from services.documents.readers import PrivateReader
from services.documents.archive_access import NativeArchiveAccess
from services.documents.preparation import prepare_editor
from features.images.validation import image_dimensions
from features.books.mobile.content import chapter_html
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
reader = PrivateReader('hello.txt', b'hello')
if reader.page(0) != ('text', 'hello'):
    raise AssertionError('PrivateReader did not preserve plain-text content')
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_probe_rejects_caught_transitive_presentation_imports(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'helper.py').write_text('try:\n import toga\nexcept ImportError:\n pass\n')
            (root / 'owner.py').write_text('import helper\n')
            result = self.probe(['owner'], cwd=root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Forbidden imports were attempted, even if caught', result.stderr)
            self.assertIn('toga', result.stderr)

    def test_probe_rejects_caught_forbidden_dependencies_during_registration(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'owner.py').write_text('def register():\n    try:\n        import editor\n'
                                          '    except ImportError:\n        pass\n')
            result = self.probe(['owner'], cwd=root, forbidden=('editor',),
                                checks='import owner\nowner.register()\n')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Forbidden imports were attempted, even if caught', result.stderr)
            self.assertIn('editor', result.stderr)

    def test_feature_declarations_do_not_allow_ui_backends(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'owner.py').write_text('try:\n    from commonUtils.ui import pyside\n'
                                          'except ImportError:\n    pass\n')
            result = self.probe(['owner'], cwd=root, allow_feature_declarations=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Forbidden imports were attempted, even if caught', result.stderr)
            self.assertIn('commonUtils.ui.pyside', result.stderr)

    def test_probe_rejects_loaded_dependencies_that_bypass_import_hooks(self):
        for name, forbidden in (('PySide6.QtCore', ()), ('toga_dummy', ()),
                                ('features.text_editor', ('features.text_editor',)),
                                ('features.text_editor.resources', ('features.text_editor',))):
            with self.subTest(module=name):
                result = self.probe([], forbidden=forbidden, checks=(
                    'from types import ModuleType\n'
                    f'sys.modules[{name!r}] = ModuleType({name!r})\n'))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Forbidden imports were attempted, even if caught', result.stderr)
                self.assertIn(name, result.stderr)
