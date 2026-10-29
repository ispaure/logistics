"""Exact reviewed manager transfer excludes checkout-local private/uncommitted inputs."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
import zipfile
from logistics_build.guest_manager import archive, verify


class GuestManagerTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.manager = self.root/'manager'
        self.shared = self.manager/'Python/commonUtils'
        self.shared.mkdir(parents=True)
        self.project = self.root/'project'
        self.project.mkdir()
        self.command(self.shared, 'init', '--quiet')
        (self.shared/'library.py').write_text('SHARED = True')
        self.command(self.shared, 'add', 'library.py')
        self.commit(self.shared)
        shared = self.command(self.shared, 'rev-parse', 'HEAD')
        self.command(self.manager, 'init', '--quiet')
        (self.manager/'public.py').write_text('PUBLIC = True')
        self.command(self.manager, 'add', 'public.py')
        self.command(self.manager, 'update-index', '--add', '--cacheinfo', '160000,'+shared+',Python/commonUtils')
        self.commit(self.manager)
        self.pin = self.command(self.manager, 'rev-parse', 'HEAD')
        (self.project/'build-manager-dependency.json').write_text(json.dumps(dict(revision=self.pin)))

    def command(self, root, *args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.PIPE).strip()

    def commit(self, root):
        self.command(root, '-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','fixture')

    def test_archives_preserve_pinned_git_sources_without_private_checkout_files(self):
        (self.manager/'private-credential').write_text('synthetic-private-input')
        for kind in ('zip','tar'):
            with self.subTest(kind=kind):
                payload = archive(self.manager,self.project,kind)
                if kind=='zip':
                    with zipfile.ZipFile(io.BytesIO(payload)) as data: names=data.namelist()
                else:
                    with tarfile.open(fileobj=io.BytesIO(payload)) as data: names=data.getnames()
                self.assertIn('public.py',names)
                self.assertIn('Python/commonUtils/library.py',names)
                self.assertIn('.git/HEAD',names)
                self.assertIn('.git/refs/' if kind=='zip' else '.git/refs',names)
                self.assertNotIn('private-credential',names)
        self.assertEqual(list((self.project/'test-results/build-scratch').glob('run-*')),[])

    def test_wrong_pin_and_modified_tracked_source_are_rejected(self):
        (self.project/'build-manager-dependency.json').write_text(json.dumps(dict(revision='0'*40)))
        with self.assertRaisesRegex(ValueError,'dependency pin'): verify(self.manager,self.project)
        (self.project/'build-manager-dependency.json').write_text(json.dumps(dict(revision=self.pin)))
        (self.manager/'public.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Commit manager'): verify(self.manager,self.project)

    def test_linux_transport_keeps_binary_archive_out_of_guest_stdin_protocol(self):
        import base64
        from unittest.mock import Mock, patch
        from logistics_build.guest_manager import stage_linux
        client = Mock()
        payload = bytes(range(256))
        with patch('logistics_build.guest_manager.archive',return_value=payload):
            stage_linux(client,'vm','/var/tmp/owned','owned',1000,1000,self.manager,self.project)
        self.assertEqual(base64.b64decode(client.execute_idempotent.call_args.kwargs['data']),payload)
        self.assertTrue(client.execute_idempotent.call_args.kwargs['data'].isascii())

    def test_newer_host_checkout_transfers_declared_pin_without_resetting_it(self):
        (self.manager/'public.py').write_text('LATER = True')
        self.command(self.manager,'add','public.py')
        self.commit(self.manager)
        later = self.command(self.manager,'rev-parse','HEAD')
        payload = archive(self.manager,self.project,'zip')
        with zipfile.ZipFile(io.BytesIO(payload)) as data:
            self.assertEqual(data.read('public.py'),b'PUBLIC = True')
        self.assertEqual(self.command(self.manager,'rev-parse','HEAD'),later)
        self.assertEqual((self.manager/'public.py').read_text(),'LATER = True')

    def test_guest_verifies_explicit_pin_without_an_installed_manager(self):
        import os
        import venv
        from build_manager import dependency_sources
        package = self.manager / 'Python/build_manager'
        package.mkdir()
        (package / '__init__.py').write_text('')
        (package / 'dependency_sources.py').write_text(Path(dependency_sources.__file__).read_text())
        self.command(self.manager, 'add', 'Python/build_manager')
        self.commit(self.manager)
        pin = self.command(self.manager, 'rev-parse', 'HEAD')
        (self.project / 'build-manager-dependency.json').write_text(json.dumps(dict(revision=pin)))
        environment = self.root / 'environment'
        # Relocatable Linux Python keeps its shared library beside the original
        # executable; copying only that binary breaks the interpreter itself.
        venv.EnvBuilder(with_pip=False, symlinks=os.name != 'nt').create(environment)
        from build_manager.retention import remove_tree
        # This interpreter is owned by the fixture; retire it before the outer
        # TemporaryDirectory, including bounded Windows executable-release waits.
        self.addCleanup(remove_tree, environment)
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        repository = Path(__file__).resolve().parents[3]
        command = [str(python), '-c',
            'import sys; from logistics_build.guest_manager import verify; verify(sys.argv[1], sys.argv[2])',
            str(self.manager), str(self.project)]
        env = dict(os.environ, PYTHONPATH=str(repository))
        result = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.project / 'build-manager-dependency.json').write_text(json.dumps(dict(revision='0' * 40)))
        denied = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn('dependency pin', denied.stderr)


class FocusedGuestCommandTests(unittest.TestCase):
    def test_manager_focus_uses_explicit_pinned_checkout_not_project_tests(self):
        from logistics_build.guest_manager import focused_command
        command = focused_command('guest-python', 'manager:test_ui.py', 'C:/owned/manager')
        self.assertEqual(command, ('guest-python', '-m', 'unittest', 'discover', '-s',
                                  'C:/owned/manager/Python/tests', '-p', 'test_ui.py', '-v'))
        for invalid in ('manager:', 'manager:../test_ui.py', 'manager:folder/test_ui.py', 'manager:folder\\test_ui.py'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                focused_command('python', invalid, '/owned/manager')

    def test_existing_shared_and_desktop_patterns_keep_routing(self):
        from logistics_build.guest_manager import focused_command
        for pattern, suite, selected in (('shared:test_styling.py', 'shared', 'test_styling.py'),
                                         ('test_documents.py', 'desktop', 'test_documents.py')):
            self.assertEqual(focused_command('python', pattern, '/owned/manager'),
                             ('python', 'dev.py', 'test', suite, selected, '--python', 'python'))
