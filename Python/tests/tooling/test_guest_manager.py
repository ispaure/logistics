"""Exact reviewed manager transfer excludes checkout-local private/uncommitted inputs."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
import zipfile
from Scripts.guest_manager import archive, verify


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
        from Scripts.guest_manager import stage_linux
        client = Mock()
        payload = bytes(range(256))
        with patch('Scripts.guest_manager.archive',return_value=payload):
            stage_linux(client,'vm','/var/tmp/owned','owned',1000,1000,self.manager,self.project)
        self.assertEqual(base64.b64decode(client.execute.call_args.kwargs['data']),payload)
        self.assertTrue(client.execute.call_args.kwargs['data'].isascii())
