"""Mutate editor fixtures to prove the architecture command rejects bypasses."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Scripts.architecture import ROOT, check, portable_sources, references
from Scripts.document_architecture import document_errors


class DocumentArchitectureTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'Python/features').mkdir(parents=True)
        (self.root / 'Scripts').mkdir()
        self.policy = dict(host_adapters=[], feature_dependencies=[],
                           document_packages=['features.editor'], document_storage_exceptions=[])
        self.module = 'features.editor.nested.new_editor'
        self.write('')

    def write(self, source, module=None):
        path = (self.root / 'Python' / Path(*(module or self.module).split('.'))).with_suffix('.py')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        return path

    def errors(self):
        return document_errors(self.root, self.policy, portable_sources, references)[0]

    def rejected(self, source, expected):
        self.write(source)
        self.assertTrue(any(expected in error for error in self.errors()), self.errors())

    def test_notebook_host_actions_have_no_dependency_waivers(self):
        policy = json.loads((ROOT / 'Scripts/architecture.json').read_text())
        self.assertFalse(any(source.startswith('Python/features/notebooks/') and target.startswith('mobile.')
                             for source, target in policy['host_adapters']))
        self.assertNotIn(['notebooks', 'text_editor'], policy['feature_dependencies'])

    def test_backend_imports_relative_lazy_and_dynamic_factories_are_rejected(self):
        for source in (
            'from features.rclone.localcrypt import copies as storage',
            'import features.rclone.remote_access as backend',
            'def edit():\n from ...rclone import service',
            "FACTORY = 'features.rclone.localcrypt.copies:Copies'",
            "import importlib\nbackend = importlib.import_module('features.rclone.localcrypt.copies')",
            'from commonUtils.runtime.resources.local import LocalFiles as Files',
            'from commonUtils.runtime.resources.mutations import save_resource_and_reopen',
        ):
            with self.subTest(source=source):
                self.rejected(source, 'backend:')

    def test_backend_policy_inspection_is_rejected(self):
        for expression in ('source.remote_storage', "getattr(source, 'remote_storage', False)",
                           "hasattr(provider, 'localcrypt')", 'provider.encrypted_path(path)',
                           'entry.remote_source', 'entry.storage_scope'):
            with self.subTest(expression=expression):
                self.rejected('def save(source, provider, path, entry):\n return ' + expression,
                              'backend-policy:')

    def test_raw_writers_and_aliases_are_rejected(self):
        sources = (
            "open(path, 'wb')",
            "from builtins import open as output\noutput(path, 'wb')",
            "import io as streams\nstreams.open(path, 'wb')",
            "from pathlib import Path as P\ntarget = P(path)\ntarget.write_bytes(data)",
            "from pathlib import Path\np = Path(path)\np.open('wb')",
            "target.write_text('new')",
            "target.open(mode=mode)",
            "import os as system\nsystem.replace(staged, path)",
            "from os import replace as replace_file\nwriter = replace_file\nwriter(staged, path)",
            "from commonUtils.persistence.atomic import atomic_write_bytes as write\nwrite(path, data)",
            "from commonUtils.persistence.text import write_text_file as write\nschedule(write)",
            "from commonUtils.persistence.publication import save_transaction\nsave_transaction()",
            "provider.replace_stream(path, writer, expected_revision=revision)",
            "provider.create_file(path, data)",
            "resource.provider.remove_empty(path, revision)",
            "target.unlink()",
            "writer = getattr(target, 'write_bytes')\nwriter(data)",
            "from pathlib import Path\nPath(path).replace(target)",
            "from zipfile import ZipFile as Archive\nArchive(path, 'w')",
            "from commonUtils.archives.zip_access import open_archive\nopen_archive(path, 'w')",
            "from commonUtils.persistence.atomic import *\natomic_write_bytes(path, data)",
            "import shutil\nshutil.copyfile(source, destination)",
        )
        for source in sources:
            with self.subTest(source=source):
                self.rejected(source, 'storage' if 'import *' in source else ('archive-write:' if 'ZipFile' in source or 'open_archive' in source else 'raw-'))

    def test_raw_local_reads_are_rejected(self):
        for source in ("open(path, 'rb')", "path.open('rb')", 'path.read_bytes()',
                       'path.read_text()', "from pathlib import Path\nPath(path).open()",
                       'from commonUtils.persistence.text import read_text_file\nread_text_file(path)'):
            with self.subTest(source=source):
                self.rejected(source, 'raw-')

    def test_archive_serialization_in_memory_is_allowed(self):
        self.write("from io import BytesIO\nfrom zipfile import ZipFile\noutput = BytesIO()\nwith ZipFile(output, 'w') as archive:\n archive.writestr('data', b'bytes')")
        self.assertEqual(self.errors(), [])

    def test_shared_policy_storage_and_generic_streams_are_allowed(self):
        self.write('''from services.documents.storage import DocumentResource, DocumentPolicy, document_writable, publish_document_stream, read_local_bytes

def edit(provider, path, source, output):
    if document_writable(provider) and DocumentPolicy.for_provider(provider).persistent:
        with DocumentResource(provider, path, max_bytes=100) as resource:
            resource.read()
            resource.save(b'updated')
    with source.open(path) as stream:
        output.write(stream.read())
    publish_document_stream(provider, path, writer, expected_revision=revision)
    return read_local_bytes(path, max_bytes=100)
''')
        self.assertEqual(self.errors(), [])

    def test_new_descendants_in_every_current_editor_package_inherit_contract(self):
        packages = json.loads((ROOT / 'Scripts/architecture.json').read_text())['document_packages']
        self.assertTrue({'features.text_editor', 'features.notebooks', 'features.books',
                         'features.comics', 'features.pdf'} <= set(packages))
        for package in packages:
            self.policy['document_packages'] = [package]
            with self.subTest(package=package):
                self.write("def export(path):\n path.write_bytes(b'bypass')", package + '.new.nested.editor')
                self.assertTrue(any('raw-method:write_bytes' in error for error in self.errors()))

    def test_new_launcher_or_editor_identity_requires_explicit_coverage(self):
        for source in ("from features.contributions import DocumentLauncherContribution as Launcher\nLauncher('new', 'New', launch)",
                       "class NewEditor:\n document_editor_id = 'new'",
                       "class NewEditor:\n document_editor_id: str = 'new'"):
            with self.subTest(source=source):
                self.write(source, 'features.new_owner.editor')
                self.assertTrue(any('Unclassified document launcher' in error for error in self.errors()))
                self.policy['document_packages'] = ['features.editor', 'features.new_owner']
                self.assertEqual(self.errors(), [])
                self.policy['document_packages'] = ['features.editor']

    def test_missing_or_linked_document_sources_fail_closed(self):
        self.policy['document_packages'] = ['features.missing']
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            self.errors()
        self.policy['document_packages'] = ['features.editor']
        target = self.root / 'outside.py'
        target.write_text('')
        (self.root / 'Python/features/editor/linked.py').symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'cannot traverse links'):
            self.errors()

    def exception(self, operation, **options):
        return dict(module=self.module, scope='recovery', operation=operation,
                    reason='Owned ordinary recovery record.', **options)

    def test_exceptions_are_scoped_to_one_function_and_operation(self):
        self.policy['document_storage_exceptions'] = [self.exception('raw-method:write_bytes')]
        self.write("def recovery(path):\n path.write_bytes(b'draft')")
        self.assertEqual(self.errors(), [])
        self.write("def recovery(path):\n path.write_bytes(b'draft')\n path.unlink()")
        self.assertTrue(any('raw-method:unlink' in error for error in self.errors()))
        self.write("def recovery(path):\n path.write_bytes(b'draft')\ndef export(path):\n path.write_bytes(b'copy')")
        self.assertTrue(any('export -> raw-method:write_bytes' in error for error in self.errors()))

    def test_exceptions_require_reasons_and_cannot_hide_backend_dependencies(self):
        self.policy['document_storage_exceptions'] = [self.exception('backend-policy:remote_storage')]
        self.rejected('def recovery(source):\n return source.remote_storage', 'backend-policy:')
        self.policy['document_storage_exceptions'] = [dict(self.exception('raw-method:write_bytes'), reason='')]
        self.rejected("def recovery(path):\n path.write_bytes(b'')", 'Invalid document storage exception')

    def test_external_codec_exclusion_cannot_exempt_an_entire_editor(self):
        self.policy['document_external_packages'] = {'features.editor': 'Skip ordinary editor code.'}
        self.assertTrue(any('Invalid external document codec exclusion' in error for error in self.errors()))

    def test_unused_exceptions_are_rejected(self):
        self.policy['document_storage_exceptions'] = [self.exception('raw-method:write_bytes')]
        self.rejected('def recovery():\n pass', 'Unused document storage exception')

    def test_transaction_callbacks_must_keep_the_shared_publication_entry(self):
        self.policy['document_storage_exceptions'] = [self.exception(
            'raw-call:os.replace', via='services.documents.storage.document_transaction')]
        self.write('''import os
from services.documents.storage import document_transaction as transaction

def recovery():
    def publish():
        os.replace(staged, destination)
    return transaction(publish=publish)
''')
        self.policy['document_storage_exceptions'][0]['scope'] = 'recovery.publish'
        self.assertEqual(self.errors(), [])
        self.rejected(self.write_source().replace('return transaction(publish=publish)', 'return publish()'), 'raw-call:os.replace')

    def write_source(self):
        return (self.root / 'Python/features/editor/nested/new_editor.py').read_text()

    def test_ordinary_architecture_command_includes_document_failures(self):
        self.write("def export(path):\n path.write_bytes(b'unsafe')")
        (self.root / 'Scripts/architecture.json').write_text(json.dumps(self.policy))
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(check(self.root), 1)
        self.assertIn('Document storage boundary:', output.getvalue())
        self.assertIn('1 document modules', output.getvalue())

    def test_standalone_architecture_script_reports_document_violations(self):
        import shutil
        import subprocess
        import sys
        for name in ('architecture.py', 'document_architecture.py'):
            shutil.copyfile(ROOT / 'Scripts' / name, self.root / 'Scripts' / name)
        self.write("def export(path):\n path.write_bytes(b'unsafe')")
        (self.root / 'Scripts/architecture.json').write_text(json.dumps(self.policy))
        result = subprocess.run([sys.executable, str(self.root / 'Scripts/architecture.py')],
                                cwd=self.root, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Document storage boundary:', result.stdout)
        self.assertNotIn('ModuleNotFoundError', result.stderr)

    def test_empty_package_policy_cannot_silently_hide_registered_editors(self):
        self.write("class Editor:\n document_editor_id = 'new'")
        self.policy['document_packages'] = []
        self.assertTrue(any('Unclassified' in error for error in self.errors()))
